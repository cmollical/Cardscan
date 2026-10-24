"""Five-card experiment. Default is an offline plan; paid execution needs two flags."""
import argparse
from dataclasses import asdict
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import time

from .costs import Settings
from .models import ResearchTarget
from .provider import OpenAIWebSearchProvider
from .storage import ResearchStore
from .valuation import value_research
from .verification import ReviewedEvidence, EbaySourceVerifier, Unverified

DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / 'experiments' / 'ai-five' / 'manifest.json'


def load_manifest(path):
    document = json.loads(Path(path).read_text())
    cases = document['cases']
    ids = [case['id'] for case in cases]
    if len(cases) != 5 or len(set(ids)) != 5 or any(not value or not all(c.isalnum() or c in '-_' for c in value) for value in ids):
        raise ValueError('Exactly five unique cases with safe directory names required')
    for case in cases:
        ResearchTarget(**case['target'])
    return document


def plan(manifest, settings, as_of):
    return {'status':'not_run_paid_authorization_required', 'as_of':str(as_of),
            'paid_api_calls_executed':0, 'actual_api_cost_usd':None,
            'settings':asdict(settings), 'conservative_request_reservation_usd':str(settings.reservation()),
            'conservative_five_request_reservations_usd':str(settings.reservation()*5),
            'illustrative_cost_per_card_usd':str(Decimal('10000')*Decimal('0.75')/1_000_000
                                                + Decimal('2000')*Decimal('4.50')/1_000_000
                                                + settings.max_search_calls*Decimal('0.01')),
            'illustration_assumptions':'10,000 input tokens, 2,000 output tokens, all configured tool calls; not measured usage',
            'cases':[{'id':c['id'], 'category':c['category'], 'target':c['target'],
                      'status':'not_run', 'qualified_sold_count':None, 'rejected_count':None,
                      'valuation':None, 'evidence_urls':[], 'api_cost_usd':None,
                      'latency_seconds':None} for c in manifest['cases']]}


def run_cases(manifest, settings, as_of, output, provider, verifier, *, authorize_paid=False, revalue=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for case in manifest['cases']:
        start = time.monotonic()
        target = ResearchTarget(**case['target'])
        if revalue:
            previous = json.loads((Path(revalue)/(case['id']+'.json')).read_text())
            research = previous['research']
            if research['target'] != target.identity() or research['as_of'] != str(as_of):
                raise ValueError('Revaluation target/cutoff differs from original research')
            research = {**research, 'incremental_cost_usd':'0', 'revaluation_only':True}
        else:
            research = provider.retrieve(target, as_of, authorize_paid=authorize_paid)
        result = value_research(target, research, settings, verifier)
        result.update(case_id=case['id'], target=target.identity(), category=case['category'],
                      total_latency_seconds=time.monotonic()-start)
        (output/(case['id']+'.json')).write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
        summaries.append({'id':case['id'], 'provider_status':research['status'],
                          'valuation':result['valuation']['value'], 'valuation_status':result['valuation']['status'],
                          'qualified_sold_count':result['evidence_quality']['qualified_sold_count'],
                          'rejected_count':result['evidence_quality']['rejected_candidate_count'],
                          'incremental_cost_usd':research.get('incremental_cost_usd'),
                          'total_latency_seconds':result['total_latency_seconds']})
    summary = {'as_of':str(as_of), 'cases':summaries,
               'status':'completed_attempts_not_independent_accuracy_validation',
               'settings':asdict(settings)}
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--settings', type=Path)
    parser.add_argument('--as-of', type=date.fromisoformat, required=True)
    parser.add_argument('--output', type=Path, default=Path('local-evidence/ai-five'))
    parser.add_argument('--database', type=Path, default=Path('local-evidence/ai-research.sqlite'))
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--authorize-paid', action='store_true')
    parser.add_argument('--revalue', type=Path, help='Revalue saved research without OpenAI API calls')
    parser.add_argument('--reviews', type=Path)
    parser.add_argument('--verify-ebay', action='store_true', help='Also make ordinary free public eBay fetches; no challenges bypassed')
    args = parser.parse_args()
    try:
        settings = Settings(**(json.loads(args.settings.read_text()) if args.settings else {}))
        manifest = load_manifest(args.manifest)
        if args.authorize_paid != args.execute:
            parser.error('Paid execution requires BOTH --execute and --authorize-paid')
        if args.revalue and args.execute:
            parser.error('--revalue never permits paid execution')
        if not args.execute and not args.revalue:
            print(json.dumps(plan(manifest, settings, args.as_of), indent=2, ensure_ascii=False))
            return
        if args.reviews and args.verify_ebay:
            parser.error('Choose independent review or eBay source verifier per run')
        verifier = Unverified()
        if args.reviews:
            verifier = ReviewedEvidence(json.loads(args.reviews.read_text()))
        elif args.verify_ebay:
            from ..public_web import PublicClient
            verifier = EbaySourceVerifier(PublicClient(Path('local-evidence/ai-source-cache')))
        store = ResearchStore(args.database)
        provider = OpenAIWebSearchProvider(store, settings)
        result = run_cases(manifest, settings, args.as_of, args.output, provider, verifier,
                           authorize_paid=args.authorize_paid, revalue=args.revalue)
        print(json.dumps(result, indent=2))
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f'Experiment input error: {exc}\n')


if __name__ == '__main__':
    main()
