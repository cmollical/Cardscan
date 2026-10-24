"""Real minimized source fixture plus synthetic adversarial variants; no live CI calls."""
from dataclasses import replace
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cardscan.pricing import Card, evaluate
from cardscan.public_web import (Document, Snapshot, RetrievalError, PublicClient, parse_ebay,
                                 qualify, discover_pricecharting, research_quote, reported_sales_estimates)

FIXTURE = Path(__file__).parent / 'fixtures' / 'ebay-sold-128018251936.html'
URL = 'https://www.ebay.com/itm/128018251936'
TARGET = Card('pokemon', '151', '199/165', 'english', 'standard', 'holo', 'NM')
TODAY = date(2026, 10, 24)


def snapshot(html=None, final_url=URL):
    text = FIXTURE.read_text() if html is None else html
    return Snapshot(URL, final_url, '2026-10-24T15:00:00+00:00', hashlib.sha256(text.encode()).hexdigest(), text)


def qualify_listing(listing, target=TARGET):
    return qualify(target, listing, set_aliases=('SV: Scarlet & Violet 151',), standard_edition=True)


class PublicListingTests(unittest.TestCase):
    def test_actual_minimized_ebay_page(self):
        listing = parse_ebay(snapshot())
        self.assertTrue(listing.sold)
        self.assertEqual(listing.item_price, Decimal('260.0'))
        self.assertEqual(listing.sold_on, date(2026, 8, 9))
        sale, reasons = qualify_listing(listing)
        self.assertEqual(reasons, ())
        self.assertEqual(sale.verification_level, 'seller_reported')
        self.assertIsNone(sale.shipping)
        self.assertIsNone(evaluate(TARGET, [sale], TODAY).value)
        self.assertIn('seller-reported evidence requires research mode', evaluate(TARGET, [sale], TODAY).rejected[0][1])

    def test_product_redirect_not_current_price_substitution(self):
        with self.assertRaises(RetrievalError):
            parse_ebay(snapshot(final_url='https://www.ebay.com/p/17062924371'))

    def test_out_of_stock_and_sold_counter_do_not_prove_sale(self):
        html = FIXTURE.read_text().replace('This Buy It Now listing sold on Sun, Aug 9 at 3:21 PM.', 'Out of stock. 12 sold.')
        listing = parse_ebay(snapshot(html))
        self.assertFalse(listing.sold)
        self.assertIn('no explicit completed-sale confirmation', qualify_listing(listing)[1])

    def test_unavailable_date_not_guessed_from_current_year(self):
        html = FIXTURE.read_text().replace('"endDate":', '"irrelevantDate":')
        listing = parse_ebay(snapshot(html))
        self.assertIsNone(listing.sold_on)
        self.assertIsNone(qualify_listing(listing)[0])

    def test_hidden_best_offer_and_proxy_rejected(self):
        html = FIXTURE.read_text().replace('data-testid="x-price-section">', 'data-testid="x-price-section">Best offer accepted ')
        self.assertTrue(parse_ebay(snapshot(html)).best_offer)
        self.assertIsNone(qualify_listing(parse_ebay(snapshot(html)))[0])
        listing = replace(parse_ebay(snapshot()), title='Charizard 199/165 proxy card')
        self.assertIsNone(qualify_listing(listing)[0])

    def test_every_exact_dimension_and_condition_conflict(self):
        listing = parse_ebay(snapshot())
        for key, wrong in [('Set', 'Evolutions'), ('Language', 'Japanese'), ('Card Number', '6/165'),
                           ('Finish', 'Reverse Holo'), ('Condition', 'Lightly Played')]:
            candidate = replace(listing, specifics={**listing.specifics, key: wrong})
            self.assertIsNone(qualify_listing(candidate)[0], key)
        self.assertIsNone(qualify_listing(replace(listing, title=listing.title+' LP'))[0])
        self.assertIsNone(qualify_listing(listing, replace(TARGET, edition='unlimited'))[0])

    def test_primary_price_must_corroborate_structured_data(self):
        html = FIXTURE.read_text().replace('"price": "260.0"', '"price": "999.0"')
        listing = parse_ebay(snapshot(html))
        self.assertIn('structured price not corroborated by primary visible price', listing.parse_issues)

    def test_source_failure_stays_explicit(self):
        class Client:
            def get(self, url):
                raise RetrievalError('Access challenge; stopped')
        report = research_quote(TARGET, [URL], Client(), TODAY)
        self.assertEqual(report['valuation']['status'], 'insufficient_evidence')
        self.assertIn('Access challenge', report['observations'][0]['retrieval_error'])

    def test_no_automatic_network_retry_or_challenge_bypass(self):
        with tempfile.TemporaryDirectory() as directory:
            client = PublicClient(Path(directory))
            response = unittest.mock.MagicMock()
            response.__enter__.return_value = response
            response.read.return_value = b'<html><body>Please verify you are human</body></html>'
            response.headers = {'Content-Type': 'text/html'}
            response.geturl.return_value = URL
            with patch.object(client.opener, 'open', return_value=response) as request:
                with self.assertRaisesRegex(RetrievalError, 'challenge'):
                    client.get(URL)
                self.assertEqual(request.call_count, 1)
            with self.assertRaises(RetrievalError):
                client.get('http://127.0.0.1/private')


def report_page():
    # Entirely synthetic report rows for independent parser/estimator checks.
    rows = []
    for index, amount in enumerate(('100.00', '110.00', '120.00')):
        rows.append(f'<tr id="tcgplayer-SYNTHETIC-{index}"><td class="date">2026-10-20</td>'
                    f'<td class="title">Charizard ex - 199/165 Near Mint English [TCGPlayer]</td>'
                    f'<td class="numeric">${amount}</td></tr>')
    return '<h1>Charizard ex #199 Pokemon Scarlet &amp; Violet 151</h1><div class="completed-auctions-used"><table>'+''.join(rows)+'</table></div>'


class SecondaryReportTests(unittest.TestCase):
    def report(self, html=None, **kwargs):
        s = snapshot(report_page() if html is None else html, final_url='https://www.pricecharting.com/game/example')
        return reported_sales_estimates(s, TARGET, 'Charizard ex', mapping_reviewed=True, as_of=TODAY, **kwargs)

    def test_actual_rows_not_guide_price_and_no_shipping(self):
        report = self.report()
        group = report['groups']['tcgplayer']
        self.assertEqual(group['value'], '110.00')
        self.assertEqual(group['count'], 3)
        self.assertEqual(group['status'], 'secondary_research_estimate')
        self.assertEqual(report['groups']['ebay']['count'], 0)
        self.assertIn('secondary_publisher_report', group['records'][0]['verification_level'])

    def test_missing_condition_language_and_future_dates_rejected(self):
        for before, after in [('Near Mint', 'Used'), ('English', 'Japanese'), ('2026-10-20', '2026-10-25')]:
            group = self.report(report_page().replace(before, after))['groups']['tcgplayer']
            self.assertIsNone(group['value'])
            self.assertEqual(group['count'], 0)

    def test_duplicates_cannot_reach_minimum(self):
        page = report_page().replace('SYNTHETIC-1', 'SYNTHETIC-0')
        self.assertIsNone(self.report(page)['groups']['tcgplayer']['value'])

    def test_no_automatic_page_mapping(self):
        report = reported_sales_estimates(snapshot(report_page()), TARGET, 'Charizard ex', as_of=TODAY)
        self.assertEqual(report['status'], 'product_page_mapping_requires_review')

    def test_outliers_abstain(self):
        report = self.report(report_page().replace('$120.00', '$10000.00'))
        self.assertEqual(report['groups']['tcgplayer']['status'], 'review_required')
        self.assertIsNone(report['groups']['tcgplayer']['value'])

    def test_only_ungraded_sold_table_is_discovered(self):
        html = ('<a href="https://www.ebay.com/itm/111111111111">active</a>'
                '<div class="completed-auctions-used"><table><tr id="ebay-222222222222">'
                '<td><a class="js-ebay-completed-sale" href="https://www.ebay.com/itm/222222222222?tracking=1">sold</a></td>'
                '</tr></table></div><div class="completed-auctions-graded">'
                '<a href="https://www.ebay.com/itm/333333333333">graded</a></div>')
        self.assertEqual(discover_pricecharting(snapshot(html, final_url='https://www.pricecharting.com/game/example')),
                         ('https://www.ebay.com/itm/222222222222',))


class OriginalLinkTests(unittest.TestCase):
    def test_source_original_listing_option_is_retained(self):
        html = ('<div class="completed-auctions-used"><table><tr id="ebay-222222222222">'
                '<td><a class="js-ebay-completed-sale" '
                'href="https://www.ebay.com/itm/222222222222?nordt=true&amp;rt=nc&amp;tracking=ignored">sold</a>'
                '</td></tr></table></div>')
        self.assertEqual(discover_pricecharting(snapshot(html, final_url='https://www.pricecharting.com/game/example')),
                         ('https://www.ebay.com/itm/222222222222?nordt=true&rt=nc',))
