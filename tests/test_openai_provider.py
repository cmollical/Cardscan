from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock

from cardscan.ai.costs import Settings, usage_cost
from cardscan.ai.provider import OpenAIWebSearchProvider
from cardscan.ai.storage import ResearchStore, BudgetError
from ai_fixtures import TARGET,TODAY,response,candidate


class OpenAIProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store=ResearchStore(Path(self.temp.name)/'cache.sqlite')
        self.client=MagicMock()
        self.client.responses.create.return_value=response()
        self.provider=OpenAIWebSearchProvider(self.store,client=self.client)

    def test_no_paid_calls_without_explicit_authorization(self):
        result=self.provider.retrieve(TARGET,TODAY)
        self.assertEqual(result['status'],'authorization_required')
        self.client.responses.create.assert_not_called()
        self.assertEqual(self.store.ledger(),[])

    def test_official_responses_contract_and_structured_evidence(self):
        result=self.provider.retrieve(TARGET,TODAY,authorize_paid=True)
        self.assertEqual(result['status'],'researched')
        args=self.client.responses.create.call_args.kwargs
        self.assertEqual(args['model'],'gpt-5.4-mini')
        self.assertEqual(args['tools'][0]['type'],'web_search')
        self.assertEqual(args['max_tool_calls'],2)
        self.assertEqual(args['include'],['web_search_call.action.sources'])
        self.assertEqual(args['text']['format']['type'],'json_schema')
        self.assertTrue(args['text']['format']['strict'])
        self.assertFalse(args['store'])
        self.assertIn('site:tcgplayer.com',args['input'])
        self.assertEqual(len(result['sources']),3)
        self.assertEqual(len(self.store.ledger()),1)

    def test_usage_cached_tokens_reasoning_and_tool_costs(self):
        cost=usage_cost(response())
        self.assertEqual(Decimal(cost['estimated_total_usd']),Decimal('0.0229'))
        self.assertEqual(cost['reasoning_tokens'],300)
        self.assertEqual(cost['search_calls'],1)
        self.assertEqual(cost['cached_input_tokens'],2000)

    def test_cache_hit_requires_no_authorization_or_new_charge(self):
        first=self.provider.retrieve(TARGET,TODAY,authorize_paid=True)
        cached=self.provider.retrieve(TARGET,TODAY)
        self.assertTrue(cached['cache_hit'])
        self.assertEqual(cached['incremental_cost_usd'],'0')
        self.assertEqual(cached['usage'],first['usage'])
        self.assertEqual(self.client.responses.create.call_count,1)

    def test_every_identity_dimension_changes_cache(self):
        key=self.provider.cache_key(TARGET,TODAY)
        for field,value in [('name','Blastoise'),('set_name','base set 2'),('number','2/102'),('language','japanese'),
                            ('edition','first edition'),('finish','reverse holo'),('condition','MP'),('graded',True)]:
            self.assertNotEqual(key,self.provider.cache_key(replace(TARGET,**{field:value}),TODAY),field)

    def test_condition_change_and_expiration_miss(self):
        self.provider.retrieve(TARGET,TODAY,authorize_paid=True)
        self.assertEqual(self.provider.retrieve(replace(TARGET,condition='MP'),TODAY)['status'],'authorization_required')
        self.store.put(self.provider.cache_key(TARGET,TODAY),{},now=time.time()-7200)
        self.assertEqual(self.provider.retrieve(TARGET,TODAY)['status'],'authorization_required')

    def test_spending_safeguards_precede_api_call(self):
        provider=OpenAIWebSearchProvider(self.store,Settings(per_request_limit_usd='0.01'),self.client)
        self.assertEqual(provider.retrieve(TARGET,TODAY,authorize_paid=True)['status'],'budget_blocked')
        self.client.responses.create.assert_not_called()

    def test_daily_budget_is_persistent_across_provider_instances(self):
        settings=Settings(daily_limit_usd='0.34')
        first=OpenAIWebSearchProvider(self.store,settings,self.client)
        self.assertEqual(first.retrieve(TARGET,TODAY,authorize_paid=True)['status'],'researched')
        second=OpenAIWebSearchProvider(ResearchStore(self.store.path),settings,self.client)
        result=second.retrieve(replace(TARGET,condition='MP'),TODAY,authorize_paid=True)
        self.assertEqual(result['status'],'budget_blocked')
        self.assertEqual(self.client.responses.create.call_count,1)

    def test_timeout_retains_reservation_and_does_not_retry(self):
        self.client.responses.create.side_effect=TimeoutError('synthetic timeout')
        result=self.provider.retrieve(TARGET,TODAY,authorize_paid=True)
        self.assertEqual(result['status'],'timeout')
        self.assertIsNone(result['incremental_cost_usd'])
        self.assertIsNone(self.store.ledger()[0]['charged_estimate_usd'])
        self.assertEqual(self.client.responses.create.call_count,1)

    def test_rate_limit_and_provider_error(self):
        for error,status in [(type('RateLimitError',(Exception,),{})(),'rate_limited'),(RuntimeError('synthetic'),'provider_error')]:
            self.client.responses.create.side_effect=error
            self.assertEqual(self.provider.retrieve(TARGET,TODAY,authorize_paid=True)['status'],status)
        self.assertEqual(self.client.responses.create.call_count,2)

    def test_incomplete_and_malformed_output_still_account_usage(self):
        for mutation in ('incomplete','malformed','refusal'):
            raw=response()
            if mutation=='incomplete':raw['status']='incomplete'
            if mutation=='malformed':raw['output'][1]['content'][0]['text']='{}'
            if mutation=='refusal':raw['output'][1]['content']=[{'type':'refusal','refusal':'synthetic'}]
            self.client.responses.create.return_value=raw
            result=self.provider.retrieve(TARGET,TODAY,authorize_paid=True)
            self.assertEqual(result['status'],'invalid_response')
            self.assertEqual(Decimal(result['incremental_cost_usd']),Decimal('0.0229'))
        self.assertEqual(len(self.store.ledger()),3)

    def test_missing_usage_or_unknown_model_keeps_conservative_hold(self):
        for mutation in ('usage','model'):
            raw=response()
            raw.pop('usage') if mutation=='usage' else raw.update(model='unknown-expensive-model')
            self.client.responses.create.return_value=raw
            result=self.provider.retrieve(TARGET,TODAY,authorize_paid=True)
            self.assertEqual(result['status'],'invalid_response')
            self.assertIsNone(result['incremental_cost_usd'])

    def test_failed_search_or_tool_limit_violation_is_not_research(self):
        raw=response();raw['output'][0]['status']='failed';raw['output'][0]['action']['sources']=[]
        self.client.responses.create.return_value=raw
        result=self.provider.retrieve(TARGET,TODAY,authorize_paid=True)
        self.assertEqual(result['sources'],[])
        # A completed message without any successful source cannot substantiate a comp.
        self.assertEqual(result['status'],'invalid_response')
        raw=response();raw['output']=[raw['output'][0]]*3+[raw['output'][1]]
        self.client.responses.create.return_value=raw
        # Clear cache so this intentionally bad response is actually evaluated.
        result=self.provider.retrieve(replace(TARGET,condition='MP'),TODAY,authorize_paid=True)
        self.assertEqual(result['status'],'invalid_response')

    def test_atomic_reservations_do_not_overspend(self):
        from concurrent.futures import ThreadPoolExecutor
        def reserve(_):
            try:
                return self.store.reserve('2026-10-24',Decimal('0.3335'),per_request='0.35',daily='0.60',max_requests=10)
            except BudgetError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows=list(pool.map(reserve,range(2)))
        self.assertEqual(sum(r is not None for r in rows),1)

    def test_raw_only_scope_and_invalid_configuration(self):
        self.assertEqual(self.provider.retrieve(replace(TARGET,graded=True),TODAY,authorize_paid=True)['status'],'unsupported_target')
        self.client.responses.create.assert_not_called()
        for data in ({'max_search_calls':0},{'minimum_sales':2},{'model':'unknown'},{'daily_limit_usd':'NaN'}):
            with self.assertRaises(ValueError):Settings(**data)
