"""The prepared workflow must not spend until a new commit-bound approval exists."""
import unittest
from scripts.market_workflow_gate import gate


class WorkflowApprovalTests(unittest.TestCase):
    def config(self):
        return dict(authorized=True,experiment_id='synthetic-market',budget_usd='2.00',base_commit='a'*40)

    def env(self):
        return {'GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','GITHUB_REF':'refs/heads/main'}

    def test_default_and_missing_authorization_never_permit_paid_execution(self):
        self.assertFalse(gate({'authorized':False},{},None))
        self.assertFalse(gate({},self.env(),'a'*40))

    def test_exact_first_approval_push_is_required(self):
        self.assertTrue(gate(self.config(),self.env(),'a'*40))
        for field,value in [('GITHUB_EVENT_NAME','workflow_dispatch'),('GITHUB_RUN_ATTEMPT','2'),
                            ('GITHUB_REF','refs/heads/other')]:
            env=self.env();env[field]=value
            with self.assertRaises(ValueError):gate(self.config(),env,'a'*40)
        with self.assertRaises(ValueError):gate(self.config(),self.env(),'b'*40)

    def test_unsafe_experiment_id_and_over_limit_budget_rejected(self):
        for key,value in [('experiment_id','../../bad'),('budget_usd','2.01'),('budget_usd','NaN')]:
            c=self.config();c[key]=value
            with self.assertRaises(ValueError):gate(c,self.env(),'a'*40)
