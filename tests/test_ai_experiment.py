"""Five-card orchestration and independent scoring with synthetic evidence only."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

from cardscan.ai.costs import Settings
from cardscan.ai.experiment import DEFAULT_MANIFEST,load_manifest,plan,run_cases
from cardscan.ai.models import ResearchTarget,Candidate,claim_id
from cardscan.ai.provider import OpenAIWebSearchProvider
from cardscan.ai.storage import ResearchStore
from cardscan.ai.score import score
from ai_fixtures import TARGET,TODAY,candidate,response,SyntheticVerifier,review


class AIExperimentTests(unittest.TestCase):
    def manifest(self):
        return {'cases':[{'id':'synthetic-'+str(i),'category':'synthetic test only','target':{
            'game':TARGET.game,'name':TARGET.name,'set_name':TARGET.set_name,'number':TARGET.number,
            'language':TARGET.language,'edition':TARGET.edition,'finish':TARGET.finish,'condition':condition,'graded':False}}
            for i,condition in enumerate(('NM','LP','MP','HP','DMG'))]}

    def test_offline_plan_requires_no_sdk_key_or_api(self):
        manifest=load_manifest(DEFAULT_MANIFEST)
        result=plan(manifest,Settings(),TODAY)
        self.assertEqual(len(result['cases']),5)
        self.assertEqual(result['paid_api_calls_executed'],0)
        self.assertIsNone(result['actual_api_cost_usd'])
        self.assertEqual({c['target']['condition'] for c in manifest['cases']},{'NM','LP'})
        run=subprocess.run([sys.executable,'-m','cardscan.ai.experiment','--as-of',str(TODAY)],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(run.stdout)['status'],'not_run_paid_authorization_required')

    def run_fixture(self,root):
        manifest=self.manifest()
        client=MagicMock()
        responses=[]
        for case in manifest['cases']:
            target=ResearchTarget(**case['target'])
            responses.append(response([candidate(i,str(100+i*10),target) for i in range(3)]))
        client.responses.create.side_effect=responses
        provider=OpenAIWebSearchProvider(ResearchStore(root/'state.sqlite'),client=client)
        summary=run_cases(manifest,Settings(),TODAY,root/'run',provider,SyntheticVerifier(),authorize_paid=True)
        return manifest,summary,client

    def independent(self,manifest):
        result={'cases':{}}
        for case in manifest['cases']:
            target=ResearchTarget(**case['target'])
            predictions=[candidate(i,str(100+i*10),target) for i in range(3)]
            refs=[candidate(i+10,str(100+i*10),target) for i in range(3)]
            refs=[{**c,'source_name':'synthetic reference only'} for c in refs]
            attestations={}
            for c in refs:attestations.update(review(c))
            result['cases'][case['id']]={
                'target_identity_verified':True,'reviewer':'synthetic human','references':refs,'reviews':attestations,
                'labels':{claim_id(Candidate.model_validate(c)):dict(printing_matches=True,condition_matches=True,source_supports_claim=True) for c in predictions}}
        return result

    def test_five_card_mock_experiment_and_independent_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            manifest,summary,client=self.run_fixture(root)
            self.assertEqual(client.responses.create.call_count,5)
            self.assertTrue(all(c['valuation']=='110.00' for c in summary['cases']))
            result=score(manifest,root/'run',self.independent(manifest),Settings())
            self.assertEqual(result['independently_scored_cards'],5)
            self.assertEqual(result['median_absolute_percentage_error'],0)
            self.assertEqual(result['within_10_pct_of_independently_scored'],100)
            self.assertEqual(result['url_substantiation_pct_all'],100)
            self.assertEqual(result['exact_matching_accuracy_pct_audited'],100)
            self.assertEqual(result['condition_accuracy_pct_audited'],100)
            self.assertEqual(result['average_incremental_api_cost_usd'],'0.0229')
            self.assertEqual(result['status'],'complete')

    def test_no_reviews_cannot_count_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            manifest,_,_=self.run_fixture(root)
            result=score(manifest,root/'run',{},Settings())
            self.assertEqual(result['independent_success_count'],0)
            self.assertIsNone(result['median_absolute_percentage_error'])
            self.assertIsNone(result['url_substantiation_pct_all'])
            self.assertIsNone(result['exact_matching_accuracy_pct_audited'])

    def test_reference_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            manifest,_,_=self.run_fixture(root)
            independent=self.independent(manifest)
            item=independent['cases']['synthetic-0']
            item['references'][0]['url']='https://example.org/synthetic-sale/0'
            with self.assertRaisesRegex(ValueError,'overlap'):
                score(manifest,root/'run',independent,Settings())

    def test_negative_independent_labels_prevent_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            manifest,_,_=self.run_fixture(root)
            independent=self.independent(manifest)
            for case in independent['cases'].values():
                for label in case['labels'].values():label['source_supports_claim']=False
            result=score(manifest,root/'run',independent,Settings())
            self.assertEqual(result['independent_success_count'],0)
            self.assertEqual(result['url_substantiation_pct_all'],0)
            self.assertIsNone(result['median_absolute_percentage_error'])

    def test_revaluation_uses_saved_research_without_api_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            manifest,_,_=self.run_fixture(root)
            provider=MagicMock()
            result=run_cases(manifest,Settings(),TODAY,root/'revalued',provider,SyntheticVerifier(),revalue=root/'run')
            provider.retrieve.assert_not_called()
            self.assertTrue(all(c['incremental_cost_usd']=='0' for c in result['cases']))

    def test_paid_cli_needs_both_execution_flags(self):
        for flag in ('--execute','--authorize-paid'):
            result=subprocess.run([sys.executable,'-m','cardscan.ai.experiment','--as-of',str(TODAY),flag],capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertIn('BOTH',result.stderr)


    def test_independent_matching_labels_can_disprove_model_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            manifest,_,_=self.run_fixture(root)
            independent=self.independent(manifest)
            for label in independent['cases']['synthetic-0']['labels'].values():
                label['printing_matches']=False
                label['condition_matches']=False
            result=score(manifest,root/'run',independent,Settings())
            self.assertEqual(result['exact_matching_accuracy_pct_audited'],80)
            self.assertEqual(result['condition_accuracy_pct_audited'],80)
            self.assertEqual(result['independently_scored_cards'],4)

    def test_unknown_cost_is_not_reported_as_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            manifest,_,_=self.run_fixture(root)
            path=root/'run'/'synthetic-0.json'
            result=json.loads(path.read_text())
            result['research']['incremental_cost_usd']=None
            path.write_text(json.dumps(result))
            metrics=score(manifest,root/'run',{},Settings())
            self.assertIsNone(metrics['average_incremental_api_cost_usd'])
            self.assertFalse(metrics['cost_measurement_complete'])
            self.assertEqual(metrics['unknown_cost_requests'],1)
