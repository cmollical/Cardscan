"""Representation regressions from real pilot output; synthetic values labeled tests."""
from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import unittest

from cardscan.ai.models import digest
from cardscan.ai.normalization import normalize_money, normalize_attribute, normalize_identity, normalize_proposal,SetAliasRegistry
from cardscan.ai.market_provider import MARKET_INSTRUCTIONS
from cardscan.ai.market_replay import DEFAULT_BUNDLE,replay
from cardscan.ai.market_review import review_proposal
from market_fixtures import TARGET,AS_OF,estimate


class MonetaryNormalizationTests(unittest.TestCase):
    def test_unambiguous_usd_formats_and_original_text_preserved(self):
        for raw in ('365','365.00','$365','$365.00','USD 365.00','1,250.00','$1,250.00',365):
            n=normalize_money(raw,'USD')
            self.assertEqual(n.raw_value,raw);self.assertEqual(n.currency,'USD');self.assertEqual(n.errors,())
            self.assertEqual(Decimal(n.amount),Decimal('1250' if ',' in str(raw) else '365'))

    def test_decimal_precision_is_not_rounded_or_float_converted(self):
        raw='$0.3500000000000000000000000001'
        n=normalize_money(raw,'USD')
        self.assertEqual(n.amount,'0.3500000000000000000000000001');self.assertEqual(n.raw_value,raw)
        self.assertTrue(normalize_money(0.35,'USD').errors)

    def test_ambiguous_currency_locale_and_invalid_values_rejected(self):
        for raw in ('$365','365'):
            self.assertTrue(normalize_money(raw,None).errors)
        for raw in ('1.250,00','1,250','1,25','1 250.00','EUR 365','NaN','Infinity','1e3','-5','0','+$5',
                    '$365 + shipping','(365)','$ 365','1,23.00',True):
            self.assertTrue(normalize_money(raw,'USD').errors,raw)
        for currency in ('EUR','CAD','JPY'):
            self.assertTrue(normalize_money('$365',currency).errors)

    def test_explicit_usd_prefix_supplies_currency_but_no_missing_price_is_invented(self):
        n=normalize_money('USD 365.00',None);self.assertEqual(n.currency,'USD');self.assertEqual(n.errors,())
        self.assertIsNone(normalize_money(None,'USD').amount)
        self.assertTrue(normalize_money('USD 365.00','EUR').errors)


class AttributeNormalizationTests(unittest.TestCase):
    def test_reviewed_condition_finish_edition_and_language_aliases(self):
        pairs={'condition':{'Near Mint':'NM','Lightly Played':'LP','Moderately Played':'MP','Heavily Played':'HP','Damaged':'DMG'},
               'finish':{'Holofoil':'holo','Holo':'holo','Holo Rare':'holo'},
               'edition':{'1st Edition':'first edition','First Edition':'first edition'},
               'language':{'EN':'english','JA':'japanese','English':'english'}}
        for field,examples in pairs.items():
            for raw,wanted in examples.items():
                value,rule,error=normalize_attribute(field,raw)
                self.assertEqual(value,wanted);self.assertIsNotNone(rule);self.assertIsNone(error)

    def test_unknowns_missing_edition_and_raw_never_become_requested_facts(self):
        for field in ('condition','language','edition','finish','number'):
            self.assertIsNone(normalize_attribute(field,None)[0])
        for raw in ('RAW','ungraded','unknown'):
            self.assertIsNone(normalize_attribute('condition',raw)[0])
        for raw in ('great condition','excellent condition','near mint or better'):
            self.assertIsNone(normalize_attribute('condition',raw)[0])
        self.assertIsNone(normalize_attribute('finish','RAW')[0])

    def test_catalog_alias_resolution_is_explicit_and_never_fuzzy(self):
        r=SetAliasRegistry()
        self.assertEqual(r.resolve('SV: Scarlet & Violet 151','pokemon','english')[0],'151')
        self.assertEqual(r.resolve('Pokemon Obsidian Flames','pokemon','english')[0],'obsidian flames')
        self.assertIsNone(r.resolve('Scarlet Violet 151-ish','pokemon','english')[0])
        self.assertIsNone(r.resolve('SV: Scarlet & Violet 151','pokemon','japanese')[0])
        ambiguous=deepcopy(r.document);other=deepcopy(ambiguous['entries'][1]);other['catalog_source']='https://example.org/SYNTHETIC_OTHER';ambiguous['entries'].append(other)
        self.assertIsNone(SetAliasRegistry(ambiguous).resolve('151')[0])

    def test_number_zero_padding_only_and_no_denominator_inference(self):
        self.assertEqual(normalize_attribute('number','026/197')[0],'26/197')
        n,_,error=normalize_attribute('number','26');self.assertEqual(n,'26');self.assertIsNotNone(error)
        self.assertEqual(normalize_attribute('number','TG01/TG30')[0],'TG1/TG30')


class RowIdentityTests(unittest.TestCase):
    def test_same_page_rows_are_unique_stable_and_not_transactions(self):
        raw=estimate();raw['sources'].append(deepcopy(raw['sources'][0]));before=deepcopy(raw)
        n=normalize_proposal(raw,'resp_SYNTHETIC')
        self.assertEqual(raw,before)
        a,b=n['rows'];self.assertNotEqual(a['internal_row_id'],b['internal_row_id'])
        self.assertEqual(a['canonical_page_id'],b['canonical_page_id'])
        self.assertIsNone(a['marketplace_transaction']);self.assertIsNone(a['marketplace_listing_id'])
        self.assertEqual(n,normalize_proposal(raw,'resp_SYNTHETIC'))
        self.assertEqual(len(n['ambiguous_support_ids']),1)

    def test_duplicate_transactions_are_excluded_without_fabricating_ids(self):
        raw=estimate();s=raw['sources'][0];s['price_type']='completed_sale_report'
        other=deepcopy(s);other.update(id='s2',url='https://example.org/SYNTHETIC-other',reported_price='101.00')
        raw['sources'].append(other);raw['supporting_source_ids'].append('s2')
        txn={'source':'SYNTHETIC','id':'SYNTHETIC-observed-transaction','provenance':'Synthetic source adapter fixture'}
        result=review_proposal(TARGET,raw,[s['url'],other['url']],AS_OF,'resp_SYNTHETIC',transaction_records={0:txn,1:txn})
        self.assertEqual(result['known_distinct_transactions'],1)
        self.assertIn('duplicate_marketplace_transaction',result['normalization']['rows'][1]['issues'])
        self.assertEqual(result['normalization']['rows'][0]['marketplace_transaction'],txn)

    def test_ebay_listing_id_is_not_promoted_to_transaction_id(self):
        raw=estimate();raw['sources'][0]['url']='https://www.ebay.com/itm/327385385994'
        row=normalize_proposal(raw,'resp_SYNTHETIC')['rows'][0]
        self.assertEqual(row['marketplace_listing_id'],'327385385994');self.assertIsNone(row['marketplace_transaction'])


class ActualPilotReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle=json.loads(DEFAULT_BUNDLE.read_text());cls.result=replay(cls.bundle)
        cls.cases={c['case_id']:c['review'] for c in cls.result['cases']}

    def test_original_text_hashes_schema_and_offline_replay_are_reproducible(self):
        for r in self.bundle['records']:
            self.assertEqual(sha256(r['final_text'].encode()).hexdigest(),r['final_text_sha256'])
        self.assertEqual(self.result,replay(deepcopy(self.bundle)))
        mutated=deepcopy(self.bundle);mutated['records'][0]['final_text']+=' '
        with self.assertRaises(ValueError):replay(mutated)

    def test_measured_representation_improvement_is_not_accuracy(self):
        s=self.result['summary']
        self.assertEqual((s['complete_numeric_proposals_before'],s['complete_numeric_proposals_after']),(3,5))
        self.assertEqual((s['numeric_source_prices_before'],s['numeric_source_prices_after']),(6,20))
        self.assertEqual((s['evidence_rows_before'],s['evidence_rows_after']),(20,20))
        self.assertEqual((s['usable_estimates_after'],s['provisional_estimates_after'],s['insufficient_evidence_after']),(0,3,2))
        self.assertEqual(s['paid_api_calls'],0);self.assertIsNone(s['accuracy_metrics'])

    def test_charmander_generic_guide_and_bare_numbers_do_not_establish_nm(self):
        r=self.cases['modern-common'];self.assertEqual(r['result_status'],'insufficient_evidence')
        self.assertIsNone(r['display_estimate'])
        rows=r['normalization']['rows']
        self.assertIsNone(rows[0]['normalized_source']['observed_identity']['condition'])
        self.assertEqual(rows[1]['normalized_source']['observed_identity']['number'],'26')
        self.assertIn('collector_denominator_missing',rows[1]['warnings'])

    def test_english_charizard_missing_edition_and_language_stay_missing(self):
        r=self.cases['modern-chase'];self.assertEqual(r['result_status'],'provisional_estimate')
        self.assertEqual(r['display_estimate']['value'],'345');self.assertIsNone(r['accepted_valuation'])
        rows=r['normalization']['rows'];self.assertIsNone(rows[0]['normalized_source']['observed_identity']['edition'])
        self.assertIsNone(rows[2]['normalized_source']['observed_identity']['language'])

    def test_base_set_charizard_mp_and_shipping_uncertainty_are_excluded(self):
        r=self.cases['vintage-charizard-lp'];self.assertEqual(r['result_status'],'insufficient_evidence')
        rows=r['normalization']['rows']
        self.assertIn('condition_mismatch',rows[2]['issues'])
        self.assertIn('shipping_or_tax_basis_uncertain',rows[0]['issues'])
        self.assertFalse(rows[2]['contradictions'])  # Explicit MP is a mismatch, not an unknown condition.
        self.assertIsNone(r['display_estimate'])

    def test_gengar_conflicting_values_are_preserved_without_averaging(self):
        r=self.cases['first-edition-gengar'];self.assertEqual(r['result_status'],'provisional_estimate')
        self.assertEqual(r['display_estimate']['value'],'320')
        self.assertEqual(r['substantive_conflicts'][0]['prices'],['289.91','460.96'])
        self.assertIsNone(r['accepted_valuation'])

    def test_japanese_raw_and_contradictory_condition_are_not_nm_support(self):
        r=self.cases['japanese-charizard'];rows=r['normalization']['rows']
        self.assertEqual(r['result_status'],'provisional_estimate')
        self.assertIn('contradictory_condition_fields',rows[0]['issues'])
        self.assertIsNone(rows[2]['normalized_source']['observed_identity']['condition'])
        self.assertFalse(rows[0]['eligible_anchor']);self.assertFalse(rows[2]['eligible_anchor'])
        self.assertEqual(r['display_estimate']['value'],'390');self.assertIsNone(r['accepted_valuation'])

    def test_research_prompt_and_strict_validation_baseline_unchanged(self):
        self.assertEqual(sha256(MARKET_INSTRUCTIONS.encode()).hexdigest(),self.bundle['model_instructions_sha256'])
        self.assertEqual(sha256(MARKET_INSTRUCTIONS.encode()).hexdigest(),'a9caa72e0dd8b02a5615c84d51293db168f3da84485d16c02b982ac8ce05488f')
        root=Path(__file__).resolve().parents[1]
        for path,wanted in [('cardscan/pricing.py','b3dd17db7c52605d611322c02c41e7237d89eacdf65a78d9e0a4f602aef08d53'),
                            ('cardscan/ai/verification.py','24b5b26a0881fc258f3321fed1397bf9dfffb9b17cae5fd4c3cf3cf2c2a8f2e2')]:
            self.assertEqual(sha256((root/path).read_bytes()).hexdigest(),wanted)


class ThreeOutcomeTests(unittest.TestCase):
    def test_requested_zero_padding_is_normalized_without_inventing_a_number(self):
        target=replace(TARGET,number='0199/0165')
        raw=estimate(target)
        r=review_proposal(target,raw,[raw['sources'][0]['url']],AS_OF,'resp_SYNTHETIC')
        self.assertEqual(r['result_status'],'provisional_estimate')
        self.assertEqual(r['requested_identity']['number'],'0199/0165')
        self.assertEqual(r['normalized_requested_identity']['number'],'199/165')

    def test_no_numeric_anchor_means_no_display_not_automatic_acceptance(self):
        raw=estimate();raw['sources'][0]['reported_price']=None
        r=review_proposal(TARGET,raw,[raw['sources'][0]['url']],AS_OF,'resp_SYNTHETIC')
        self.assertEqual(r['result_status'],'insufficient_evidence');self.assertIsNone(r['display_estimate'])

    def test_reviewed_benchmark_can_support_usable_without_three_transactions(self):
        raw=estimate();urls=[raw['sources'][0]['url']]
        n=normalize_proposal(raw,'resp_SYNTHETIC');row=n['rows'][0]
        reviews={row['internal_row_id']:{'raw_source_sha256':row['raw_source_sha256'],'reviewer':'SYNTHETIC independent reviewer',
                 'source_substantiates':True,'reviewed_on':'2026-10-26','artifact_sha256':'a'*64}}
        r=review_proposal(TARGET,raw,urls,AS_OF,'resp_SYNTHETIC',source_reviews=reviews)
        self.assertEqual(r['result_status'],'usable_estimate');self.assertEqual(r['known_distinct_transactions'],0)
        self.assertIsNotNone(r['accepted_valuation'])
        reviews[row['internal_row_id']]['raw_source_sha256']='bad'
        self.assertEqual(review_proposal(TARGET,raw,urls,AS_OF,'resp_SYNTHETIC',source_reviews=reviews)['result_status'],'provisional_estimate')

    def test_source_url_integrity_and_numeric_proposal_range_remain_enforced(self):
        raw=estimate();r=review_proposal(TARGET,raw,[],AS_OF,'resp_SYNTHETIC')
        self.assertIsNone(r['display_estimate'])
        raw['estimated_low']='200';raw['estimated_high']='250'
        r=review_proposal(TARGET,raw,[raw['sources'][0]['url']],AS_OF,'resp_SYNTHETIC')
        self.assertIn('invalid_estimate_range',r['remaining_validation_errors'])

    def test_explicit_model_abstention_and_unknowns_are_preserved(self):
        raw=estimate();raw.update(estimated_market_value=None,estimated_low=None,estimated_high=None,
                valuation_type='insufficient_evidence',insufficient_evidence=True,recommendation='insufficient_evidence',supporting_source_ids=[])
        r=review_proposal(TARGET,raw,[raw['sources'][0]['url']],AS_OF,'resp_SYNTHETIC')
        self.assertEqual(r['result_status'],'insufficient_evidence');self.assertIsNone(r['display_estimate'])
