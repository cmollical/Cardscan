"""All prices and provenance in these tests are synthetic, never market comps."""
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path
from cardscan.identification import identify, IdentificationError
from cardscan.pricing import Card, evaluate
from cardscan.providers import ManualCompsProvider, IngestionError, parse_sale, read_json
from test_pricing import CARD, TODAY, sale


def record(i=1):
    result = asdict(sale(i))
    for key in ('item_price', 'shipping', 'sold_on', 'verified_on'):
        result[key] = str(result[key])
    return result


class EvidenceTests(unittest.TestCase):
    def test_each_printing_dimension_is_required(self):
        for field in ('game', 'set_name', 'number', 'language', 'edition', 'finish'):
            with self.subTest(field=field):
                wrong = replace(sale(1), card=replace(CARD, **{field: 'different'}))
                result = evaluate(CARD, [wrong], TODAY)
                self.assertIn(field + ' mismatch', result.rejected[0][1])

    def test_conditions_remain_separate(self):
        for condition in ('NM', 'LP', 'MP', 'HP', 'DMG'):
            target = replace(CARD, condition=condition)
            comps = [replace(sale(i), card=target) for i in range(3)]
            self.assertEqual(evaluate(target, comps, TODAY).value, Decimal('105.00'))

    def test_unknown_identity_and_condition(self):
        for field, value in [('finish', ''), ('edition', 'unknown'), ('condition', 'mint')]:
            with self.assertRaises(ValueError):
                replace(CARD, **{field: value})

    def test_exact_catalog_lookup_abstains(self):
        self.assertEqual(identify(asdict(CARD), [CARD]), CARD)
        with self.assertRaises(IdentificationError):
            identify(asdict(CARD), [replace(CARD, edition='first edition')])

    def test_unverified_legacy_sale_is_rejected(self):
        result = evaluate(CARD, [replace(sale(1), verified_by='', price_confirmed=False)], TODAY)
        self.assertIsNone(result.value)
        self.assertIn('actual paid price unconfirmed', result.rejected[0][1])

    def test_invalid_money_and_unknown_shipping(self):
        for price, shipping in [(Decimal('NaN'), Decimal(0)), (Decimal('Infinity'), Decimal(0)),
                                (Decimal('-1'), Decimal(0)), (Decimal(1), None),
                                (Decimal(1), Decimal('-1')), (Decimal(1), Decimal('NaN'))]:
            with self.subTest(price=price, shipping=shipping):
                result = evaluate(CARD, [replace(sale(1), item_price=price, shipping=shipping)], TODAY)
                self.assertIsNone(result.value)
                self.assertEqual(len(result.rejected), 1)

    def test_currency_and_unknown_flags(self):
        for changes in ({'currency': 'EUR'}, {'condition_confirmed': False}, {'price_confirmed': False},
                        {'refunded': True}, {'sold': 'true'}, {'bundle': None}, {'graded': None}):
            self.assertIsNone(evaluate(CARD, [replace(sale(1), **changes)], TODAY).value)

    def test_dates_and_boundaries(self):
        from datetime import timedelta
        for changes in ({'sold_on': TODAY + timedelta(days=1)},
                        {'verified_on': TODAY + timedelta(days=1)},
                        {'verified_on': TODAY - timedelta(days=1)}):
            self.assertEqual(len(evaluate(CARD, [replace(sale(1), **changes)], TODAY).rejected), 1)
        comps = [replace(sale(i), sold_on=TODAY - timedelta(days=90)) for i in range(3)]
        self.assertIsNotNone(evaluate(CARD, comps, TODAY).value)

    def test_duplicate_id_with_tracking_url(self):
        duplicate = replace(sale(1), url='https://example.com/test-1?tracking=other')
        result = evaluate(CARD, [sale(1), duplicate, sale(2)], TODAY)
        self.assertIsNone(result.value)
        self.assertEqual(len(result.rejected), 1)

    def test_duplicate_url_fragment(self):
        duplicate = replace(sale(2), url=sale(1).url + '/#fragment')
        self.assertEqual(len(evaluate(CARD, [sale(1), duplicate], TODAY).rejected), 1)

    def test_outlier_abstains_instead_of_silently_changing_price(self):
        result = evaluate(CARD, [sale(1), sale(2), sale(3), sale(4, '10000')], TODAY)
        self.assertIsNone(result.value)
        self.assertEqual(result.status, 'review_required')
        self.assertEqual(len(result.rejected), 1)

    def test_even_median_and_rounding(self):
        result = evaluate(CARD, [sale(1, '100'), sale(2, '100.01'), sale(3, '101'), sale(4, '102')], TODAY)
        self.assertEqual(result.value, Decimal('105.51'))

    def test_policy_configuration_cannot_force_one_comp_valuation(self):
        for changes in ({'minimum_sales': 0}, {'minimum_sales': 2}, {'minimum_sales': True},
                        {'max_age_days': -1}, {'outlier_factor': Decimal('NaN')}, {'currency': 'EUR'}):
            with self.assertRaises(ValueError):
                evaluate(CARD, [], TODAY, **changes)
        self.assertIsNone(evaluate(CARD, [sale(i) for i in range(3)], TODAY, minimum_sales=5).value)

    def test_structured_audit_json(self):
        result = evaluate(CARD, [sale(i) for i in range(3)], TODAY).to_dict()
        self.assertEqual(result['value'], '105.00')
        self.assertEqual(result['accepted'][0]['url'], sale(0).url)
        json.dumps(result, allow_nan=False)


class IngestionTests(unittest.TestCase):
    def test_strict_schema_and_permissions(self):
        valid = record()
        self.assertEqual(parse_sale(valid, {'synthetic': 'synthetic'}), sale(1))
        for mutation in ('missing', 'extra', 'float', 'bool', 'nan'):
            item = record()
            if mutation == 'missing': del item['price_confirmed']
            if mutation == 'extra': item['confidence'] = 99
            if mutation == 'float': item['item_price'] = 100.1
            if mutation == 'bool': item['sold'] = 'false'
            if mutation == 'nan': item['shipping'] = 'NaN'
            with self.assertRaises(IngestionError):
                parse_sale(item, {'synthetic': 'synthetic'})
        with self.assertRaises(IngestionError):
            parse_sale(valid, {})

    def test_duplicate_json_keys(self):
        with self.assertRaises(IngestionError):
            read_json('{"sold": true, "sold": false}')

    def test_offline_cli_integration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'target.json').write_text(json.dumps(asdict(CARD)))
            (root / 'permissions.json').write_text('{"synthetic": "synthetic"}')
            (root / 'comps.jsonl').write_text('\n'.join(json.dumps(record(i)) for i in range(3)))
            command = [sys.executable, '-m', 'cardscan.cli', str(root / 'target.json'),
                       str(root / 'comps.jsonl'), str(root / 'permissions.json'), '--as-of', str(TODAY)]
            run = subprocess.run(command, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(run.stdout)['value'], '105.00')
            (root / 'comps.jsonl').write_text(json.dumps(record()) + '\n{}')
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(run.stdout, '')
            self.assertIn(':2:', run.stderr)
