"""No paid calls: accounting diagnostics over saved pilot metadata and mocks."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import unittest
from cardscan.ai.accounting_audit import search_action_audit
from cardscan.ai.costs import Settings


class AccountingAuditTests(unittest.TestCase):
    def rows(self):
        p=Path(__file__).resolve().parents[1]/'research/results/pilot-forensics-2026-10-24/evidence-analysis.json'
        return json.loads(p.read_text())['requests']

    def response(self,row):
        return {'model':'gpt-5.4-mini-2026-03-17','usage':row['usage'],'tool_usage':row['reported_tool_usage'],
                'output':[dict(a,type='web_search_call') for a in row['actions']]}

    def test_pilot_counts_and_both_estimates_reproduce_without_rewriting_history(self):
        audits=[search_action_audit(self.response(r)) for r in self.rows()]
        self.assertEqual(sum(a['completed_search_actions'] for a in audits),7)
        self.assertEqual(sum(a['web_output_items'] for a in audits),12)
        self.assertEqual(sum(Decimal(a['search_action_estimate_usd']) for a in audits),Decimal('0.14245450'))
        self.assertEqual(sum(Decimal(a['conservative_estimate_usd']) for a in audits),Decimal('0.19245450'))
        self.assertEqual(Settings().reservation(),Decimal('0.3335'))

    def test_duplicate_ids_unknown_actions_and_counter_mismatches_require_review(self):
        r=self.response(self.rows()[0])
        for altered in ('duplicate','counter','unknown'):
            c=deepcopy(r)
            if altered=='duplicate':c['output'].append(c['output'][0])
            if altered=='counter':c['tool_usage']['web_search']['num_requests']=100
            if altered=='unknown':c['output'][0]['action']['type']='mystery'
            result=search_action_audit(c)
            self.assertEqual(result['status'],'review_required')
            self.assertIsNone(result['search_action_estimate_usd'])

    def test_missing_usage_is_never_zero_cost(self):
        r=self.response(self.rows()[0]);r['usage']=None
        a=search_action_audit(r)
        self.assertIsNone(a['search_action_estimate_usd']);self.assertIsNone(a['conservative_estimate_usd'])

    def test_malformed_action_fields_counters_and_unknown_model_fail_closed(self):
        for field,value in [('tool_usage',[]),('tool_usage',{'web_search':[]}),('model','unknown')]:
            r=self.response(self.rows()[0]);r[field]=value
            self.assertIsNone(search_action_audit(r)['search_action_estimate_usd'])
        r=self.response(self.rows()[0]);r['output'][0]['id']=[]
        self.assertIsNone(search_action_audit(r)['search_action_estimate_usd'])
