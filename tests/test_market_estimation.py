from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from cardscan.ai.costs import Settings
from cardscan.ai.market_models import MarketEstimate
from cardscan.ai.market_policy import validate_estimate
from cardscan.ai.market_provider import AIResearchValuationProvider
from cardscan.ai.market_budget import MarketExperimentStore
from cardscan.ai.market_experiment import run,plan,summarize
from cardscan.ai.market_score import score
from cardscan.ai.experiment import load_manifest,DEFAULT_MANIFEST
from cardscan.ai.models import ResearchTarget
from cardscan.ai.storage import BudgetError
from market_fixtures import TARGET,AS_OF,estimate,response


class MarketPolicyTests(unittest.TestCase):
    def check(self,data):
        return validate_estimate(TARGET,MarketEstimate.model_validate(data),
                                 ['https://example.org/synthetic/market'],AS_OF)

    def test_exact_single_reference_estimate_is_allowed_but_not_independently_verified(self):
        r,errors=self.check(estimate());self.assertEqual(errors,[])
        self.assertEqual(r['recommendation'],'usable_estimate')
        self.assertEqual(r['independent_transaction_count'],0)
        self.assertFalse(r['source_audit'][0]['independently_verified'])
        self.assertIsNone(r['confidence_percentage'])

    def test_wrong_printing_language_edition_finish_raw_condition_rejected_as_anchors(self):
        for field,value in [('number','198/165'),('set_name','other'),('language','japanese'),
                            ('edition','first edition'),('finish','reverse holo'),('graded',True),('condition','LP')]:
            d=estimate();d['sources'][0]['observed_identity'][field]=value
            self.assertTrue(self.check(d)[1],field)

    def test_requested_card_echo_must_match(self):
        d=estimate();d['card_identity']['number']='4/102'
        self.assertIn('Requested identity echo differs from exact target',self.check(d)[1])

    def test_generic_reference_is_allowed_only_with_explicit_non_condition_specific_label(self):
        d=estimate();s=d['sources'][0];s['observed_identity']['condition']=None
        s.update(condition_scope='generic_ungraded',condition_label='Ungraded')
        self.assertTrue(self.check(d)[1])
        d.update(valuation_type='generic_ungraded_reference',review_recommended=True,recommendation='review_recommended')
        r,e=self.check(d);self.assertEqual(e,[])
        self.assertIsNone(r['sources'][0]['observed_identity']['condition'])
        self.assertEqual(r['requested_condition'],'NM')

    def test_unknown_identity_needs_provisional_label_and_review(self):
        d=estimate();d['sources'][0]['observed_identity']['edition']=None
        self.assertTrue(self.check(d)[1])
        d.update(valuation_type='provisional_condition_estimate',review_recommended=True,recommendation='review_recommended')
        r,e=self.check(d);self.assertEqual(e,[]);self.assertTrue(r['review_recommended'])

    def test_contradictory_condition_labels_and_missing_information_cannot_support(self):
        for modification in ('missing','summary','label'):
            d=estimate();s=d['sources'][0]
            if modification=='missing':s['missing_information']=['precise raw condition']
            if modification=='summary':s['source_summary']='Condition unknown; only raw status known'
            if modification=='label':s['condition_label']='Lightly Played'
            self.assertTrue(self.check(d)[1])

    def test_descriptive_condition_and_near_mint_or_better_not_assumed_nm(self):
        for label in ('excellent condition','great condition','Near mint or better'):
            d=estimate();d['sources'][0]['condition_label']=label
            self.assertTrue(self.check(d)[1])

    def test_asks_and_shipping_totals_are_not_market_clearing_anchors(self):
        for field,value in [('price_type','active_asking_price'),('price_basis','includes_shipping'),
                            ('price_basis','unknown'),('reported_price',None),('currency','EUR')]:
            d=estimate();d['sources'][0][field]=value
            self.assertTrue(self.check(d)[1])

    def test_missing_information_preserved_and_unknown_date_forces_review(self):
        d=estimate();s=d['sources'][0];s['source_date']=None;s['date_meaning']='unknown'
        r,e=self.check(d);self.assertEqual(e,[]);self.assertEqual(r['recommendation'],'review_recommended')
        self.assertIsNone(r['sources'][0]['source_date'])

    def test_uncited_duplicate_unknown_support_ids_and_future_dates_rejected(self):
        for mode in ('uncited','duplicate','unknown','future'):
            d=estimate()
            if mode=='uncited':d['sources'][0]['url']='https://example.org/not-returned'
            if mode=='duplicate':d['sources'].append(deepcopy(d['sources'][0]))
            if mode=='unknown':d['supporting_source_ids']=['does-not-exist']
            if mode=='future':d['sources'][0]['source_date']='2099-01-01'
            self.assertTrue(self.check(d)[1])

    def test_price_ranges_and_non_finite_numbers_rejected(self):
        for value in ('NaN','Infinity','-5','0'):
            d=estimate();d['estimated_market_value']=value;self.assertTrue(self.check(d)[1])
        d=estimate();d['estimated_low']='120';self.assertTrue(self.check(d)[1])
        d=estimate();d['estimated_high']=None;self.assertTrue(self.check(d)[1])

    def test_explicit_abstention_has_no_price_and_no_supporting_ids(self):
        d=estimate();d.update(estimated_market_value=None,estimated_low=None,estimated_high=None,
            valuation_type='insufficient_evidence',recommendation='insufficient_evidence',insufficient_evidence=True,
            supporting_source_ids=[],review_recommended=True,evidence_quality='insufficient')
        self.assertEqual(self.check(d)[1],[])
        d['estimated_market_value']='100';self.assertTrue(self.check(d)[1])


class MarketProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.store=MarketExperimentStore(self.path/'ledger.sqlite','synthetic-market')
        self.client=Mock();self.client.responses.create.return_value=response()
        self.provider=AIResearchValuationProvider(self.store,client=self.client)

    def value(self,**kw):return self.provider.value(TARGET,AS_OF,case_id='modern-chase',**kw)

    def test_no_call_without_authorization_and_no_cache_or_background_job(self):
        self.assertEqual(self.value()['status'],'authorization_required');self.client.responses.create.assert_not_called()
        self.assertEqual(self.store.ledger(),[])

    def test_official_request_schema_usage_and_conservative_cost_accounting(self):
        r=self.value(authorize_paid=True);self.assertEqual(r['status'],'provisional_estimate')
        self.assertIsNone(r['accepted_valuation'])
        self.assertEqual(r['estimated_api_cost_usd'],'0.0265')
        req=self.client.responses.create.call_args.kwargs
        self.assertEqual(req['tools'][0]['type'],'web_search');self.assertTrue(req['text']['format']['strict'])
        self.assertEqual(req['max_tool_calls'],2);self.assertFalse(req['store'])
        self.assertEqual(len(self.store.ledger()),1)

    def test_extra_unfinished_page_open_is_not_extra_processed_call(self):
        r=response();r['output'].insert(1,{'id':'ws_open','type':'web_search_call','status':'completed','action':{'type':'open_page','url':'https://example.org/synthetic/market'}})
        r['output'].insert(2,{'id':'ws_ignored','type':'web_search_call','status':'searching','action':{'type':'open_page','url':None}})
        self.client.responses.create.return_value=r
        out=self.value(authorize_paid=True);self.assertEqual(out['status'],'provisional_estimate')
        self.assertEqual(out['api_usage']['search_calls'],3)
        self.assertEqual(out['search_action_audit']['completed_search_actions'],1)

    def test_invalid_structured_responses_preserve_cost_and_no_accepted_estimate(self):
        r=response();r['output'][-1]['content'][0]['text']='{"unexpected":true}'
        self.client.responses.create.return_value=r
        out=self.value(authorize_paid=True);self.assertEqual(out['status'],'invalid_response')
        self.assertIsNotNone(out['estimated_api_cost_usd']);self.assertIsNone(out['estimate'])

    def test_invalid_synthesis_is_quarantined_not_issued(self):
        d=estimate();d['sources'][0]['condition_label']='LP'
        self.client.responses.create.return_value=response(d)
        out=self.value(authorize_paid=True);self.assertEqual(out['status'],'insufficient_evidence')
        self.assertIsNone(out['estimate']);self.assertIn('quarantined_estimate',out)

    def test_timeout_api_errors_and_rate_limit_hold_reservation_and_stop(self):
        for index,error in enumerate((TimeoutError(),RuntimeError(),type('RateLimitError',(Exception,),{})())):
            self.client.responses.create.side_effect=error
            out=self.provider.value(TARGET,AS_OF,case_id='case-'+str(index),authorize_paid=True)
            self.assertTrue(out['stop_experiment']);self.assertIsNone(out['estimated_api_cost_usd'])
            self.assertIsNone(self.store.ledger()[-1]['charged_estimate_usd'])

    def test_usage_unknown_model_refusal_and_incomplete_response_fail_closed(self):
        for index,mode in enumerate(('usage','model','refusal','incomplete')):
            r=response()
            if mode=='usage':r['usage']=None
            if mode=='model':r['model']='unknown'
            if mode=='refusal':r['output'][-1]['content']=[{'type':'refusal','refusal':'No'}]
            if mode=='incomplete':r['status']='incomplete'
            self.client.responses.create.return_value=r
            out=self.provider.value(TARGET,AS_OF,case_id='case-'+str(index),authorize_paid=True)
            self.assertEqual(out['status'],'invalid_response');self.assertTrue(out['stop_experiment'])

    def test_raw_only_and_paid_retries_refused(self):
        self.assertEqual(self.provider.value(replace(TARGET,graded=True),AS_OF,case_id='graded',authorize_paid=True)['status'],'unsupported_target')
        self.value(authorize_paid=True)
        self.assertEqual(self.value(authorize_paid=True)['status'],'budget_blocked')
        self.assertEqual(self.client.responses.create.call_count,1)

    def test_experiment_budget_does_not_reset_at_midnight_or_on_reopen(self):
        settings=self.provider.settings
        store=MarketExperimentStore(self.path/'small.sqlite','small','0.40')
        i=store.reserve_case('first','2026-10-24',settings);store.settle(i,None,'timeout',{})
        reopened=MarketExperimentStore(self.path/'small.sqlite','small','0.40')
        with self.assertRaises(BudgetError):reopened.reserve_case('second','2026-10-25',settings)
        with self.assertRaises(BudgetError):MarketExperimentStore(self.path/'small.sqlite','small','2.00')

    def test_five_card_mock_run_plan_comparison_and_output_immutability(self):
        manifest=load_manifest(DEFAULT_MANIFEST)
        def answer(**kwargs):return response(target=ResearchTarget(**json.loads(kwargs['input'])['requested_card']))
        self.client.responses.create.side_effect=answer
        output=self.path/'run'
        summary=run(manifest,self.provider,AS_OF,output,authorize_paid=True)
        self.assertEqual(summary['paid_attempts'],5);self.assertEqual(summary['returned_estimates'],5)
        self.assertEqual(summary['strict_pilot_baseline']['valuations'],0)
        self.assertIsNone(summary['independent_accuracy'])
        with self.assertRaises(FileExistsError):run(manifest,self.provider,AS_OF,output,authorize_paid=True)
        offline=plan(manifest,self.provider.settings,AS_OF)
        self.assertEqual(offline['paid_api_calls'],0);self.assertEqual(len(offline['cases']),5)

    def test_harness_stops_after_unknown_cost_and_keeps_five_case_denominator(self):
        self.client.responses.create.side_effect=TimeoutError()
        summary=run(load_manifest(DEFAULT_MANIFEST),self.provider,AS_OF,self.path/'stopped',authorize_paid=True)
        self.assertEqual(summary['paid_attempts'],1);self.assertEqual(self.client.responses.create.call_count,1)
        self.assertIsNone(summary['estimated_total_api_cost_usd']);self.assertEqual(summary['planned_cards'],5)


class MarketScoringTests(unittest.TestCase):
    def result(self):
        return dict(case_id='modern-chase',target=TARGET.identity(),as_of=str(AS_OF),estimate=estimate(),
                    estimated_api_cost_usd='0.03',latency_seconds=9,request_id='synthetic')

    def reference(self,price='105'):
        return {'modern-chase':dict(reference_price=price,currency='USD',condition='NM',target_identity=TARGET.identity(),
                as_of=str(AS_OF),reviewer='Synthetic independent collector',reviewed_on=str(AS_OF),
                independently_established=True,used_agent_estimate_as_reference=False,reference_origin='collector_assessment',
                evidence_notes='SYNTHETIC independent fixture only',
                output_review={'correct_printing':True,'correct_condition_handling':True,'unsupported_pricing_claims':False,
                               'source_relevance':{'s1':True}})}

    def test_missing_independent_reference_has_no_accuracy_metrics(self):
        r=score([self.result()],{});self.assertIsNone(r['pricing_metrics']['median_absolute_percentage_error'])

    def test_independent_reference_metrics_and_range(self):
        r=score([self.result()],self.reference())
        self.assertEqual(r['pricing_metrics']['scored_supported_estimates'],1)
        self.assertEqual(r['pricing_metrics']['within_10_percent'],1)
        self.assertTrue(r['cases'][0]['range_contains_reference'])

    def test_self_ground_truth_wrong_identity_generic_and_unsupported_not_accuracy_success(self):
        for mode in ('self','wrong','generic','unsupported'):
            result=self.result();refs=self.reference();ref=refs['modern-chase']
            if mode=='self':ref['used_agent_estimate_as_reference']=True
            if mode=='wrong':ref['target_identity']['edition']='first edition'
            if mode=='generic':result['estimate']['valuation_type']='generic_ungraded_reference'
            if mode=='unsupported':ref['output_review']['unsupported_pricing_claims']=True
            self.assertEqual(score([result],refs)['pricing_metrics']['scored_supported_estimates'],0)
