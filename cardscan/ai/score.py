"""Independent five-card scoring. Unknown evidence never counts as success."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
from statistics import mean, median

from .costs import Settings
from .experiment import load_manifest, DEFAULT_MANIFEST
from .models import Candidate, ResearchTarget, claim_id
from .provider import canonical_url
from .valuation import value_research
from .verification import ReviewedEvidence


def percent(n, d):
    return 100*n/d if d else None


def score(manifest, run_directory, independent, settings):
    rows, errors, costs, latencies = [], [], [], []
    qualified_cards = valued = verified_success = checked_matching = matched = conditioned = 0
    urls_all, urls_audited, urls_supported = set(), set(), set()
    for case in manifest['cases']:
        path = Path(run_directory)/(case['id']+'.json')
        if not path.exists():
            rows.append({'id':case['id'], 'status':'not_run'})
            continue
        result = json.loads(path.read_text())
        target = ResearchTarget(**case['target'])
        if result['target'] != target.identity() or result['research']['target'] != target.identity():
            raise ValueError('Saved result identity differs from frozen manifest')
        qualified_cards += result['evidence_quality']['qualified_sold_count'] >= settings.minimum_sales
        value = result['valuation']['value']
        valued += value is not None
        cost = result['research'].get('incremental_cost_usd')
        costs.append(None if cost is None else Decimal(cost))
        latencies.append(result['total_latency_seconds'])
        annotation = independent.get('cases', {}).get(case['id'], {})
        labels = annotation.get('labels', {})
        for label in labels.values():
            if any(type(label.get(k)) is not bool for k in ('printing_matches','condition_matches','source_supports_claim')):
                raise ValueError('Every independent label requires three explicit boolean judgements')
        raw_candidates = [Candidate.model_validate(c) for c in (result['research'].get('evidence') or {}).get('candidates', [])]
        per_url = {}
        for candidate in raw_candidates:
            if candidate.item_price is None:
                continue
            try:
                url = canonical_url(candidate.url)
            except ValueError:
                continue
            key = (case['id'], url)
            urls_all.add(key)
            per_url.setdefault(key, []).append(labels.get(claim_id(candidate)))
        for key, url_labels in per_url.items():
            if all(label is not None for label in url_labels):
                urls_audited.add(key)
                if all(label['source_supports_claim'] for label in url_labels):
                    urls_supported.add(key)
        accepted = {(s['source'],s['transaction_id']) for s in result['valuation']['accepted']}
        all_supported = bool(accepted)
        for row in result['sold_candidates']:
            candidate = Candidate.model_validate(row['candidate'])
            from urllib.parse import urlsplit
            if (urlsplit(candidate.url).hostname,candidate.source_record_id) not in accepted:
                continue
            label = labels.get(row['claim_id'])
            if label is None:
                all_supported = False
                continue
            checked_matching += 1
            matched += label['printing_matches']
            conditioned += label['condition_matches']
            all_supported &= all(label.values())
        review = annotation.get('reviewer')
        existing_reviewers = {s['verified_by'] for s in result['valuation']['accepted']}
        row = {'id':case['id'], 'valuation':value, 'status':'pending_independent_review'}
        if annotation.get('target_identity_verified') is True and review:
            if not isinstance(review, str) or review.lower().startswith(('openai','model','source_adapter:')) or review in existing_reviewers:
                raise ValueError('A separate human reference reviewer is required')
            references = [Candidate.model_validate(c) for c in annotation.get('references', [])]
            source_urls = {canonical_url(u) for u in result['research']['sources']}
            source_ids = {(c.source_name,c.source_record_id) for c in raw_candidates if c.source_record_id}
            if any(canonical_url(c.url) in source_urls or (c.source_name,c.source_record_id) in source_ids for c in references):
                raise ValueError('Independent reference sales overlap research evidence')
            reviews = annotation.get('reviews', {})
            if any(r.get('reviewer') != review for r in reviews.values()):
                raise ValueError('Reference attestations must belong to independent reviewer')
            reference_research = {'as_of':result['research']['as_of'], 'sources':[c.url for c in references],
                                  'evidence':{'candidates':[c.model_dump() for c in references]}}
            reference = value_research(target, reference_research, settings, ReviewedEvidence(reviews))
            row['reference_valuation'] = reference['valuation']
            reference_value = reference['valuation']['value']
            if value is not None and reference_value is not None and all_supported:
                error = 100*abs(Decimal(value)-Decimal(reference_value))/Decimal(reference_value)
                errors.append(error)
                verified_success += error <= 10
                row.update(status='independently_scored', absolute_percentage_error=str(error), within_10_pct=error <= 10)
            else:
                row['status'] = 'abstained_or_unsubstantiated'
        rows.append(row)
    complete_costs = bool(costs) and all(c is not None for c in costs)
    return {'planned_cards':len(manifest['cases']), 'cards_attempted':len(costs),
            'cards_with_sufficient_evidence':qualified_cards,
            'sufficient_evidence_pct':percent(qualified_cards,len(manifest['cases'])),
            'valuations_emitted':valued, 'independently_scored_cards':len(errors),
            'independent_success_count':verified_success,
            'independent_success_pct_all_planned':percent(verified_success,len(manifest['cases'])),
            'exact_matching_accuracy_pct_audited':percent(matched,checked_matching),
            'condition_accuracy_pct_audited':percent(conditioned,checked_matching),
            'accepted_comps_independently_audited':checked_matching,
            'source_urls_with_prices':len(urls_all), 'source_urls_audited':len(urls_audited),
            'url_review_coverage_pct':percent(len(urls_audited),len(urls_all)),
            'url_substantiation_pct_audited':percent(len(urls_supported),len(urls_audited)),
            'url_substantiation_pct_all':percent(len(urls_supported),len(urls_all)) if urls_all == urls_audited else None,
            'median_absolute_percentage_error':float(median(errors)) if errors else None,
            'within_10_pct_of_independently_scored':percent(sum(e<=10 for e in errors),len(errors)),
            'average_incremental_api_cost_usd':str(mean(costs)) if complete_costs else None,
            'maximum_incremental_api_cost_usd':str(max(costs)) if complete_costs else None,
            'cost_measurement_complete':complete_costs, 'unknown_cost_requests':sum(c is None for c in costs),
            'average_total_latency_seconds':mean(latencies) if latencies else None,
            'cases':rows, 'status':'complete' if len(errors)==len(manifest['cases']) else 'incomplete',
            'limitations':['Five observations do not establish general accuracy or liquidity',
                           'Human review is an attestation; preserve source artifacts',
                           'Costs are usage-based estimates, not invoices; cache hits cost zero incrementally']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directory',type=Path)
    parser.add_argument('independent_reviews',type=Path)
    parser.add_argument('--manifest',type=Path,default=DEFAULT_MANIFEST)
    parser.add_argument('--settings',type=Path)
    args=parser.parse_args()
    try:
        result=score(load_manifest(args.manifest),args.run_directory,json.loads(args.independent_reviews.read_text()),
                     Settings(**(json.loads(args.settings.read_text()) if args.settings else {})))
        print(json.dumps(result,indent=2,allow_nan=False))
    except (ValueError,TypeError,KeyError,OSError) as exc:
        parser.exit(2,f'Scoring input error: {exc}\n')


if __name__ == '__main__':
    main()
