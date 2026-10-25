"""Independent manual reference comparison. No network or model grading."""
import argparse
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from statistics import median

from .market_policy import money
from .market_experiment import summarize


def score(results,references):
    rows=[];errors=[];within=[];ranges=[];printing=[];conditions=[];unsupported=[];relevance=[]
    for result in results:
        case=result['case_id'];e=result.get('estimate');ref=references.get(case,{})
        row={'case_id':case,'absolute_percentage_error':None,'within_10_percent':None,'range_contains_reference':None,
             'reference_status':'unavailable','reviewed_price_relevance':None}
        review=ref.get('output_review',{})
        reviewer=ref.get('reviewer')
        independent=(isinstance(reviewer,str) and bool(reviewer.strip()) and
                     not reviewer.casefold().startswith(('openai','model','ai:')) and ref.get('independently_established') is True)
        try:valid_date=date.fromisoformat(ref.get('reviewed_on',''))<=date.today()
        except (ValueError,TypeError):valid_date=False
        valid_review=independent and valid_date and ref.get('target_identity')==result['target']
        if valid_review:
            for key,bucket in [('correct_printing',printing),('correct_condition_handling',conditions),('unsupported_pricing_claims',unsupported)]:
                if type(review.get(key)) is bool:bucket.append(review[key]);row[key]=review[key]
            reviewed_sources=review.get('source_relevance',{})
            known_ids={s['id'] for s in (e or {}).get('sources',[])}
            if isinstance(reviewed_sources,dict):
                relevance.extend(v for k,v in reviewed_sources.items() if k in known_ids and type(v) is bool)
        try:reference=money(ref.get('reference_price'))
        except ValueError:reference=None
        qualifies=(valid_review and reference is not None and ref.get('currency')=='USD'
                   and ref.get('as_of')==result['as_of'] and ref.get('condition')==result['target']['condition']
                   and bool(ref.get('evidence_notes') or ref.get('evidence_urls'))
                   and ref.get('reference_origin') in {'collector_assessment','shop_assessment','independently_reviewed_comps'}
                   and ref.get('used_agent_estimate_as_reference') is False)
        if qualifies:
            row['reference_status']='independent_attestation_not_software_authenticated'
            if e and e['estimated_market_value'] is not None and e['valuation_type']!='generic_ungraded_reference':
                # Unsupported/wrong-printing outputs stay visible but cannot count
                # as validated accuracy success. Report their APE separately.
                value=Decimal(e['estimated_market_value']);ape=abs(value-reference)/reference*100
                row.update(absolute_percentage_error=str(ape),within_10_percent=ape<=10,
                           range_contains_reference=Decimal(e['estimated_low'])<=reference<=Decimal(e['estimated_high']))
                output_supported=(review.get('correct_printing') is True and review.get('correct_condition_handling') is True
                                  and review.get('unsupported_pricing_claims') is False)
                row['eligible_accuracy_success']=output_supported
                if output_supported:
                    errors.append(ape);within.append(ape<=10);ranges.append(row['range_contains_reference'])
        rows.append(row)
    def rate(values):return sum(values)/len(values) if values else None
    return {'cases':rows,'pricing_metrics':{'scored_supported_estimates':len(errors),
             'median_absolute_percentage_error':str(median(errors)) if errors else None,
             'within_10_percent':rate(within),'range_contains_reference':rate(ranges)},
            'human_review_metrics':{'printing_correct_rate':rate(printing),'printing_review_count':len(printing),
              'condition_handling_correct_rate':rate(conditions),'condition_review_count':len(conditions),
              'unsupported_claim_rate':rate(unsupported),'unsupported_review_count':len(unsupported),
              'source_relevance_rate':rate(relevance),'source_review_count':len(relevance)},
            'attempt_metrics':summarize(results),
            'limitations':['Manual reference and review are attestations, not authenticated ground truth.',
                          'Generic references are not scored against requested-condition reference prices.',
                          'Missing independent prices never produce accuracy metrics.']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,required=True);p.add_argument('--references',type=Path,required=True)
    a=p.parse_args()
    from .experiment import load_manifest,DEFAULT_MANIFEST
    manifest=load_manifest(DEFAULT_MANIFEST)
    results=[json.loads((a.results/(c['id']+'.json')).read_text()) for c in manifest['cases']]
    print(json.dumps(score(results,json.loads(a.references.read_text())),indent=2))


if __name__=='__main__':main()
