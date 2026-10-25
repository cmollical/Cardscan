"""Five-card AI estimation experiment. Offline plan by default, no pricing cache."""
import argparse
from dataclasses import asdict
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

from .costs import Settings
from .experiment import DEFAULT_MANIFEST, load_manifest
from .market_budget import MarketExperimentStore
from .market_provider import AIResearchValuationProvider
from .models import ResearchTarget, digest


def plan(manifest,settings,as_of,total_limit='2.00'):
    return {'status':'not_run_requires_new_paid_authorization','as_of':str(as_of),'paid_api_calls':0,
            'settings':asdict(settings),'experiment_budget_target_usd':total_limit,
            'conservative_per_request_reserve_usd':str(settings.reservation()),
            'five_full_reservations_usd':str(settings.reservation()*5),
            'illustrative_per_attempt_usd':'0.0365','illustrative_five_attempts_usd':'0.1825',
            'illustration':'10k uncached input tokens, 2k output tokens, two search actions. Not measured usage or invoice.',
            'cases':[{'id':c['id'],'target':c['target'],'status':'not_run','estimate':None,
                      'estimated_api_cost_usd':None,'latency_seconds':None} for c in manifest['cases']]}


def summarize(results,planned_count=5):
    attempts=[r for r in results if r.get('request_id')]
    costs=[Decimal(r['estimated_api_cost_usd']) for r in attempts if r.get('estimated_api_cost_usd') is not None]
    unknown_costs=len(costs)!=len(attempts)
    estimates=[r for r in results if r.get('estimate') and r['estimate']['estimated_market_value'] is not None]
    usable=[r for r in estimates if r['estimate']['recommendation']=='usable_estimate']
    total=None if unknown_costs else sum(costs,Decimal(0))
    return {'planned_cards':planned_count,'paid_attempts':len(attempts),'returned_estimates':len(estimates),
            'generic_references':sum(r['estimate']['valuation_type']=='generic_ungraded_reference' for r in estimates),
            'provisional_estimates':sum(r['estimate']['valuation_type']=='provisional_condition_estimate' for r in estimates),
            'usable_recommendations_not_accuracy_proof':len(usable),'coverage':len(estimates)/planned_count,
            'estimated_total_api_cost_usd':None if total is None else str(total),
            'estimated_cost_per_attempt_usd':str(total/len(attempts)) if total is not None and attempts else None,
            'estimated_cost_per_usable_recommendation_usd':str(total/len(usable)) if total is not None and usable else None,
            'max_estimated_attempt_cost_usd':str(max(costs)) if costs and not unknown_costs else None,
            'average_latency_seconds':sum(r['latency_seconds'] for r in attempts)/len(attempts) if attempts else None,
            'independent_accuracy':None,'independently_verified_transactions':0,
            'strict_pilot_baseline':{'valuations':0,'planned_cards':5,'original_estimate_usd':'0.19245450',
                'search_action_estimate_usd':'0.14245450','average_latency_seconds':9.596558991,
                'note':'Historical comparison, not a contemporaneous accuracy control.'}}


def run(manifest,provider,as_of,output,*,authorize_paid=False):
    output=Path(output)
    # A new directory prevents overwriting prior evidence or casually re-running.
    output.mkdir(parents=True,exist_ok=False)
    results=[];stopped=False
    for case in manifest['cases']:
        if stopped:
            r={'status':'not_attempted_after_stop','target':ResearchTarget(**case['target']).identity(),
               'as_of':str(as_of),'estimate':None,'request_id':None,'estimated_api_cost_usd':'0','latency_seconds':0}
        else:
            r=provider.value(ResearchTarget(**case['target']),as_of,case_id=case['id'],authorize_paid=authorize_paid)
        r.update(case_id=case['id'],category=case['category'],experiment_id=provider.store.experiment_id,
                 manifest_sha256=digest(manifest),settings=asdict(provider.settings))
        with (output/(case['id']+'.json')).open('x') as f:json.dump(r,f,indent=2,ensure_ascii=False,allow_nan=False)
        results.append(r)
        with (output/'summary.json').open('w') as f:json.dump(summarize(results,len(manifest['cases'])),f,indent=2)
        stopped=stopped or r.get('stop_experiment',False) or r['status']=='configuration_error'
    return summarize(results,len(manifest['cases']))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--as-of',type=date.fromisoformat,required=True)
    p.add_argument('--manifest',type=Path,default=DEFAULT_MANIFEST)
    p.add_argument('--settings',type=Path)
    p.add_argument('--experiment-id',default='market-ai-five-v1')
    p.add_argument('--total-limit-usd',default='2.00')
    p.add_argument('--database',type=Path,default=Path('local-evidence/market-ai/ledger.sqlite'))
    p.add_argument('--output',type=Path,default=Path('local-evidence/market-ai/run'))
    p.add_argument('--execute',action='store_true');p.add_argument('--authorize-paid',action='store_true')
    a=p.parse_args()
    try:
        settings=Settings(**(json.loads(a.settings.read_text()) if a.settings else {'max_output_tokens':4000,'max_daily_requests':5}))
        manifest=load_manifest(a.manifest)
        limit=Decimal(a.total_limit_usd)
        if not limit.is_finite() or limit<=0:raise ValueError('Positive finite total limit required')
        if a.execute!=a.authorize_paid:p.error('Paid execution requires BOTH --execute and --authorize-paid')
        if not a.execute:
            print(json.dumps(plan(manifest,settings,a.as_of,a.total_limit_usd),indent=2));return
        if a.output.exists():raise ValueError('Use a new output directory; prior evidence must not be overwritten')
        store=MarketExperimentStore(a.database,a.experiment_id,a.total_limit_usd)
        provider=AIResearchValuationProvider(store,settings)
        print(json.dumps(run(manifest,provider,a.as_of,a.output,authorize_paid=True),indent=2))
    except (ValueError,TypeError,KeyError,OSError) as exc:p.exit(2,f'Experiment setup error: {exc}\n')


if __name__=='__main__':main()
