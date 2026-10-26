"""Synthetic benchmark calculations only; never independent real market prices."""
from copy import deepcopy
from datetime import date
import json
import unittest

from cardscan.ai.benchmarks import BenchmarkDataset,score_replay
from cardscan.ai.market_replay import DEFAULT_BUNDLE,replay


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.replay=replay(json.loads(DEFAULT_BUNDLE.read_text()))
        self.case=next(c for c in self.replay['cases'] if c['case_id']=='modern-chase')

    def benchmark(self,case=None,value='300.00'):
        case=case or self.case
        return {'case_id':case['case_id'],'card_identity':deepcopy(case['target']),
                'requested_condition':case['target']['condition'],'reference_market_value':value,
                'reference_low':None,'reference_high':None,'currency':'USD','reference_date':case['as_of'],
                'reference_source':'SYNTHETIC independent reference only','reference_urls':[],
                'reference_methodology':'collector_assessment','condition_specificity':'explicit_condition',
                'verification_status':'independently_reviewed','reviewer':'SYNTHETIC independent reviewer',
                'reviewed_on':'2026-10-26','reviewer_notes':'Synthetic test-only benchmark, not real pricing evidence.',
                'independent_of_ai':True,'used_ai_proposal_as_ground_truth':False,
                'output_review':{'correct_card_printing':True,'correct_condition_handling':True,
                                 'unsupported_pricing_claims':False,'notes':'Synthetic fixture review'}}

    def dataset(self,benchmarks):return {'version':'independent-benchmarks-v1','benchmarks':benchmarks}

    def test_missing_benchmarks_leave_accuracy_unmeasured_but_report_coverage(self):
        r=score_replay(self.replay,self.dataset([]))
        self.assertIsNone(r['accuracy_by_status']['provisional_estimate']['median_absolute_percentage_error'])
        self.assertIsNone(r['accuracy_by_status']['usable_estimate']['percentage_within_10_percent'])
        self.assertEqual(r['coverage']['provisional_estimate_coverage'],0.6)
        self.assertEqual(r['coverage']['abstention_rate'],0.4)
        self.assertIsNone(r['matching']['human_reviewed_condition_failures'])

    def test_ape_twenty_percent_absolute_error_and_range_containment(self):
        r=score_replay(self.replay,self.dataset([self.benchmark()]))
        row=next(c for c in r['cases'] if c['case_id']=='modern-chase')
        self.assertEqual(row['absolute_dollar_error'],'45.00');self.assertEqual(row['absolute_percentage_error'],'15.00')
        self.assertFalse(row['within_10_percent']);self.assertTrue(row['within_20_percent'])
        self.assertFalse(row['estimated_range_contains_benchmark']);self.assertFalse(row['approved_valuation'])
        group=r['accuracy_by_status']['provisional_estimate']
        self.assertEqual(group['median_absolute_percentage_error'],'15.00')
        self.assertEqual(group['percentage_within_20_percent'],'100')

    def test_usable_and_provisional_statistics_are_never_combined(self):
        data=deepcopy(self.replay)
        other=next(c for c in data['cases'] if c['case_id']=='japanese-charizard')
        other['review']['result_status']='usable_estimate'  # Synthetic status, not real approval.
        r=score_replay(data,self.dataset([self.benchmark(),self.benchmark(other,'400')]))
        self.assertEqual(r['accuracy_by_status']['usable_estimate']['scored_estimates'],1)
        self.assertEqual(r['accuracy_by_status']['provisional_estimate']['scored_estimates'],1)
        self.assertEqual(r['accuracy_by_status']['usable_estimate']['median_absolute_percentage_error'],'2.500')

    def test_low_value_card_reports_dollar_error_as_well_as_percentage(self):
        data=deepcopy(self.replay);case=data['cases'][0]
        case['review']['result_status']='provisional_estimate'
        case['review']['display_estimate']={'value':'0.35','low':'0.25','high':'0.60','scope':'requested_condition_proposal'}
        r=score_replay(data,self.dataset([self.benchmark(case,'0.40')]))
        row=r['cases'][0]
        self.assertEqual(row['absolute_dollar_error'],'0.05');self.assertEqual(row['absolute_percentage_error'],'12.500')
        self.assertTrue(row['estimated_range_contains_benchmark'])

    def test_draft_self_reference_generic_or_wrong_identity_do_not_create_ground_truth(self):
        for key,value in [('verification_status','draft'),('independent_of_ai',False),
                          ('used_ai_proposal_as_ground_truth',True),('condition_specificity','generic_ungraded'),
                          ('reference_market_value',None),('currency','EUR'),('reference_source',None)]:
            b=self.benchmark();b[key]=value
            r=score_replay(self.replay,self.dataset([b]))
            self.assertEqual(r['accuracy_by_status']['provisional_estimate']['scored_estimates'],0)
        b=self.benchmark();b['card_identity']['edition']='first edition'
        self.assertEqual(score_replay(self.replay,self.dataset([b]))['accuracy_by_status']['provisional_estimate']['scored_estimates'],0)

    def test_benchmark_range_date_and_reviewer_are_validated(self):
        for mode in ('range','date','reviewer'):
            b=self.benchmark()
            if mode=='range':b.update(reference_low='350',reference_high='250')
            if mode=='date':b['reference_date']='2020-01-01'
            if mode=='reviewer':b['reviewer']='ChatGPT'
            self.assertEqual(score_replay(self.replay,self.dataset([b]))['accuracy_by_status']['provisional_estimate']['scored_estimates'],0)

    def test_wrong_or_unsupported_output_stays_in_error_denominator(self):
        b=self.benchmark();b['output_review'].update(correct_card_printing=False,correct_condition_handling=False,unsupported_pricing_claims=True)
        r=score_replay(self.replay,self.dataset([b]))
        self.assertEqual(r['accuracy_by_status']['provisional_estimate']['scored_estimates'],1)
        self.assertEqual(r['matching']['human_reviewed_printing_failures'],1)
        self.assertEqual(r['matching']['human_reviewed_condition_failures'],1)
        self.assertEqual(r['accuracy_by_status']['provisional_estimate']['validated_success_percentage'],'0')

    def test_duplicate_or_unknown_benchmark_case_rejected(self):
        b=self.benchmark()
        with self.assertRaises(ValueError):score_replay(self.replay,self.dataset([b,b]))
        b['case_id']='not-a-case'
        with self.assertRaises(ValueError):score_replay(self.replay,self.dataset([b]))
