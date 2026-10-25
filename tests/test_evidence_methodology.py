"""Offline forensic replay and proposed design contracts. No API client or network."""
import copy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import unittest

from cardscan.ai.models import Candidate, ResearchTarget, claim_id
from cardscan.ai.provider import canonical_url
from cardscan.ai.valuation import qualify_reasons
from cardscan.ai.costs import Settings
from ai_fixtures import candidate, TARGET
from methodology_contract import condition_issues, reference_issues

ROOT = Path(__file__).resolve().parents[1]
AUDIT = json.loads((ROOT/'research/results/pilot-forensics-2026-10-24/evidence-analysis.json').read_text())


class PilotForensicTests(unittest.TestCase):
    def test_complete_retained_and_discarded_partition(self):
        rows = AUDIT['candidates']
        self.assertEqual(len(rows), 20)
        self.assertEqual(sum(r['retained_by_original_provider'] for r in rows), 13)
        self.assertEqual(sum(r['candidate']['kind']=='completed_sale' for r in rows), 18)
        self.assertEqual(sum(AUDIT['counts'].values()), 20)
        self.assertEqual(AUDIT['counts']['verified_completed_sales'], 0)
        self.assertEqual(AUDIT['counts']['verified_published_references'], 0)
        self.assertTrue(all(not r['price_independently_substantiated'] for r in rows))
        self.assertTrue(all(not r['source_document_retained'] for r in rows))

    def test_extracted_claim_hashes_and_existing_rejections_replay(self):
        requests = {r['case_id']:r for r in AUDIT['requests']}
        for row in AUDIT['candidates']:
            with self.subTest(row=row['id']):
                c = Candidate.model_validate(row['candidate'])
                self.assertEqual(claim_id(c), row['claim_id'])
                request = requests[row['case_id']]
                consulted = {canonical_url(s['url']) for a in request['actions'] if a['status']=='completed'
                             for s in a['action'].get('sources', [])}
                reasons = qualify_reasons(ResearchTarget(**request['target']), c, consulted, date(2026,10,24), 90)
                self.assertEqual(reasons, row['offline_qualification_replay'])
                if row['retained_by_original_provider']:
                    self.assertEqual(reasons, row['actual_candidate_rejections'])

    def test_unfinished_attempt_is_not_a_third_completed_action(self):
        for r in AUDIT['requests']:
            actions = r['actions']
            self.assertEqual(sum(a['status']=='completed' for a in actions), 2)
            searches = sum(a['status']=='completed' and a['action']['type']=='search' for a in actions)
            self.assertEqual(searches, r['reported_tool_usage']['web_search']['num_requests'])
            if r['provider_status']=='invalid_response':
                self.assertEqual(len(actions), 3)
                self.assertEqual(actions[-1]['status'], 'searching')
                self.assertEqual(actions[-1]['action'], {'type':'open_page', 'url':None})

    def test_cost_estimates_remain_separate_and_are_not_invoices(self):
        self.assertEqual(sum(Decimal(r['original_estimate_usd']) for r in AUDIT['requests']), Decimal('0.19245450'))
        self.assertEqual(sum(Decimal(r['search_action_estimate_usd']) for r in AUDIT['requests']), Decimal('0.14245450'))
        self.assertGreater(Settings().reservation(), Decimal('0.15'))

    def test_model_condition_contradictions_are_not_source_support(self):
        contradictory = [r for r in AUDIT['candidates'] if r['id'] in {'M2','M3','M4','M5','M6'}]
        self.assertEqual(len(contradictory), 5)
        for r in contradictory:
            self.assertEqual(r['candidate']['identity']['condition'], 'NM')
            self.assertTrue(condition_issues(r['candidate']))
            # Characterize the CURRENT gap; this test does not claim it is fixed.
            self.assertFalse(any('condition' in s for s in r['actual_candidate_rejections']))

    def test_reclassification_does_not_create_verified_benchmark(self):
        for row in AUDIT['candidates']:
            c = copy.deepcopy(row['candidate'])
            c['kind'] = 'published_reference'
            self.assertIn('independent verification required', reference_issues(TARGET.identity(), c))


class ProposedConditionContractTests(unittest.TestCase):
    def test_unknown_generic_descriptive_and_range_conditions_do_not_map_to_nm(self):
        for label in (None, 'ungraded', 'raw', 'great condition', 'Near mint or better'):
            c = candidate(); c['identity']['condition'] = label
            self.assertTrue(condition_issues(c))

    def test_conflicting_summary_is_quarantined(self):
        for summary in ('Condition unknown', 'condition is not specified', 'Only raw status is known'):
            c = candidate(evidence_summary=summary)
            self.assertTrue(condition_issues(c))

    def test_consistent_label_is_not_itself_verification(self):
        self.assertEqual(condition_issues(candidate()), [])
        self.assertFalse(AUDIT['candidates'][0]['condition_independently_substantiated'])


class ProposedReferenceContractTests(unittest.TestCase):
    def fixture(self):
        # Entirely synthetic contract. No invented market price is used.
        return dict(kind='published_reference', verification_state='verified', identity=TARGET.identity(),
                    condition_scope='explicit_condition', benchmark_type='sold_derived_market_estimate',
                    price_basis='card_only_excluding_shipping_and_tax', freshness_reviewed=True,
                    field_support={f:dict(state='explicit', verified=True, locator='synthetic:'+f)
                                   for f in ('identity','condition','price','currency','benchmark_definition','price_basis')})

    def test_explicit_verified_contract_is_eligible_without_transaction_fields(self):
        self.assertEqual(reference_issues(TARGET.identity(), self.fixture()), [])

    def test_ungraded_asking_opaque_stale_and_unverified_references_are_ineligible(self):
        for key,value in [('condition_scope','ungraded_generic'),('benchmark_type','asking_statistic'),
                          ('benchmark_type','unknown'),('freshness_reviewed',False),('verification_state','unverified')]:
            r=self.fixture();r[key]=value
            self.assertTrue(reference_issues(TARGET.identity(), r))

    def test_wrong_printing_condition_and_missing_field_support_are_ineligible(self):
        for field in ('edition','language','finish','condition','number'):
            r=self.fixture();r['identity'][field]='wrong'
            self.assertIn('printing or condition mismatch',reference_issues(TARGET.identity(), r))
        for state in ('unknown','inferred','contradictory'):
            r=self.fixture();r['field_support']['condition']['state']=state
            self.assertIn('condition source support required',reference_issues(TARGET.identity(), r))
        r=self.fixture();r['field_support']['price']['locator']=''
        self.assertIn('price source support required',reference_issues(TARGET.identity(), r))
