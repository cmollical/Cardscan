from dataclasses import replace
from decimal import Decimal
from datetime import date
import unittest
from cardscan.ai.costs import Settings
from cardscan.ai.models import Candidate,claim_id
from cardscan.ai.valuation import value_research
from cardscan.ai.verification import ReviewedEvidence
from ai_fixtures import TARGET,TODAY,candidate,research,SyntheticVerifier,review


class AIEvidenceTests(unittest.TestCase):
    def value(self,candidates,verifier=None):
        return value_research(TARGET,research(candidates),Settings(),verifier or SyntheticVerifier())

    def test_exact_matches_integrate_with_existing_median_and_exclude_shipping(self):
        comps=[candidate(i,str(100+10*i),shipping=s) for i,s in enumerate((None,'0','999'))]
        result=self.value(comps)
        self.assertEqual(result['valuation']['value'],'110.00')
        self.assertEqual(result['evidence_quality']['qualified_sold_count'],3)
        self.assertIsNone(result['evidence_quality']['confidence_score'])

    def test_wrong_edition_language_condition_and_each_dimension_rejected(self):
        for key,bad in [('edition','first edition'),('language','japanese'),('condition','NM'),('finish','reverse holo'),
                        ('set_name','base set 2'),('number','4/130'),('name','Dark Charizard'),('game','magic')]:
            c=candidate();c['identity'][key]=bad
            result=self.value([c])
            self.assertIn(key+' mismatch or unknown',result['sold_candidates'][0]['rejections'])
            self.assertIsNone(result['valuation']['value'])

    def test_leading_zero_collector_number_normalization(self):
        comps=[candidate(i,str(100+i)) for i in range(3)]
        for c in comps:c['identity']['number']='004/102'
        self.assertIsNotNone(self.value(comps)['valuation']['value'])

    def test_graded_bundle_quantity_unknown_and_price_semantics_exclusions(self):
        for changes in ({'bundle':True},{'quantity':2},{'quantity':None},{'price_is_item_only':False},
                        {'currency':'JPY'},{'source_record_id':None},{'sold_on':None},{'item_price':'NaN'},
                        {'item_price':'-1'},{'sold_on':'2027-01-01'}):
            self.assertIsNone(self.value([candidate(**changes)])['valuation']['value'])
        c=candidate();c['identity']['graded']=True
        self.assertIn('graded or unknown',self.value([c])['sold_candidates'][0]['rejections'])

    def test_references_and_active_listings_are_never_mixed_into_sold_median(self):
        result=self.value([candidate(1),candidate(2,kind='market_reference'),candidate(3,kind='active_listing')])
        self.assertIsNone(result['valuation']['value'])
        self.assertEqual(len(result['market_references']),1)
        self.assertEqual(len(result['active_listings']),1)
        self.assertEqual(result['evidence_quality']['qualified_sold_count'],1)

    def test_duplicates_cannot_create_liquidity(self):
        result=self.value([candidate(1),candidate(1),candidate(2)])
        self.assertIsNone(result['valuation']['value'])
        self.assertIn('duplicate evidence URL or source transaction',result['sold_candidates'][1]['rejections'])

    def test_uncited_model_url_cannot_become_a_comp(self):
        r=research([candidate()]);r['sources']=[]
        result=value_research(TARGET,r,Settings(),SyntheticVerifier())
        self.assertIn('URL absent from API search sources/citations',result['sold_candidates'][0]['rejections'])

    def test_citations_do_not_confer_verification(self):
        result=value_research(TARGET,research(),Settings())
        self.assertIsNone(result['valuation']['value'])
        self.assertEqual(result['evidence_quality']['qualified_sold_count'],0)

    def test_review_is_bound_to_full_claim_not_just_url(self):
        c=candidate();verifier=ReviewedEvidence(review(c))
        self.assertTrue(verifier.verify(TARGET,Candidate.model_validate(c),TODAY).verified)
        self.assertFalse(verifier.verify(TARGET,Candidate.model_validate({**c,'item_price':'999'}),TODAY).verified)
        self.assertFalse(ReviewedEvidence({}).verify(TARGET,Candidate.model_validate(c),TODAY).verified)

    def test_outliers_trigger_review_without_issuing_a_trimmed_price(self):
        result=self.value([candidate(1),candidate(2,'110'),candidate(3,'10000')])
        self.assertIsNone(result['valuation']['value'])
        self.assertEqual(result['valuation']['status'],'review_required')
        self.assertEqual(len(result['valuation']['rejected']),1)

    def test_source_record_duplicates_and_tracking_aliases(self):
        a=candidate();b=candidate(2,url=a['url']+'?utm_source=tracking')
        result=self.value([a,b,candidate(3)])
        self.assertIn('duplicate evidence URL or source transaction',result['sold_candidates'][1]['rejections'])

    def test_error_result_and_invalid_reference_url_abstain(self):
        r=research([]);r['status']='timeout';r['evidence']=None
        self.assertIsNone(value_research(TARGET,r,Settings())['valuation']['value'])
        result=self.value([candidate(kind='market_reference',url='https://')])
        self.assertFalse(result['market_references'][0]['source_consulted'])


class DeterministicSourceVerifierTests(unittest.TestCase):
    def test_source_checker_rejects_differing_prices_ids_and_unhandled_hosts(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock,patch
        from cardscan.public_web import Listing
        from cardscan.ai.verification import EbaySourceVerifier
        # Entirely synthetic primary-page facts, never a live market observation.
        url='https://www.ebay.com/itm/123456789012'
        listing=Listing(url,'123456789012','Charizard Base Set Unlimited 4/102 LP',Decimal('100.00'),'USD',
                        date(2026,10,20),True,False,
                        {'Game':'Pokemon TCG','Set':'Base Set','Card Number':'4/102','Language':'English',
                         'Finish':'Holo','Features':'Unlimited','Condition':'Lightly Played','Card Name':'Charizard'},
                        '',{'observed_at':'2026-10-24T12:00:00+00:00'},())
        client=MagicMock()
        client.get.return_value=SimpleNamespace(observed_at='2026-10-24T12:00:00+00:00',sha256='a'*64)
        verifier=EbaySourceVerifier(client)
        c=Candidate.model_validate(candidate(url=url,source_record_id='123456789012'))
        with patch('cardscan.ai.verification.parse_ebay',return_value=listing):
            self.assertTrue(verifier.verify(TARGET,c,TODAY).verified)
            self.assertFalse(verifier.verify(TARGET,c.model_copy(update={'item_price':'999'}),TODAY).verified)
            self.assertFalse(verifier.verify(TARGET,c.model_copy(update={'source_record_id':'other'}),TODAY).verified)
        client.get.reset_mock()
        self.assertFalse(verifier.verify(TARGET,c.model_copy(update={'url':'https://example.org'}),TODAY).verified)
        client.get.assert_not_called()


class HistoricalReviewTests(unittest.TestCase):
    def test_review_date_is_not_backdated_to_historical_sale_cutoff(self):
        comps=[candidate(i,str(100+i*10)) for i in range(3)]
        reviews={}
        for c in comps:reviews.update(review(c))
        original=research(comps)
        original['as_of']='2026-10-23'
        result=value_research(TARGET,original,Settings(),ReviewedEvidence(reviews))
        self.assertEqual(result['valuation']['value'],'110.00')
        self.assertEqual(result['valuation']['as_of'],'2026-10-23')
        self.assertEqual(result['valuation']['accepted'][0]['verified_on'],'2026-10-24')

    def test_legacy_engine_keeps_original_date_checks_by_default(self):
        from test_pricing import CARD,sale
        from cardscan.pricing import evaluate
        from dataclasses import replace
        comps=[replace(sale(i),sold_on=date(2026,10,20)) for i in range(3)]
        self.assertIsNone(evaluate(CARD,comps,date(2026,10,23)).value)
        self.assertEqual(evaluate(CARD,comps,date(2026,10,23),verification_as_of=TODAY).value,Decimal('100.00'))
