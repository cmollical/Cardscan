"""Independent, manually reviewed benchmark workflow. No model or network calls."""
import argparse
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from statistics import median
from typing import Literal
from pydantic import Field, StrictBool

from .models import StrictModel, ObservedIdentity
from .normalization import normalize_money


class OutputReview(StrictModel):
    correct_card_printing: StrictBool | None
    correct_condition_handling: StrictBool | None
    unsupported_pricing_claims: StrictBool | None
    notes: str


class Benchmark(StrictModel):
    case_id: str
    card_identity: ObservedIdentity
    requested_condition: Literal['NM','LP','MP','HP','DMG']
    reference_market_value: str | None
    reference_low: str | None
    reference_high: str | None
    currency: str | None
    reference_date: str | None
    reference_source: str | None
    reference_urls: list[str]
    reference_methodology: Literal['collector_assessment','shop_assessment','independently_reviewed_comps','published_reference','unknown']
    condition_specificity: Literal['explicit_condition','generic_ungraded','mixed','unknown']
    verification_status: Literal['draft','independently_reviewed','rejected']
    reviewer: str | None
    reviewed_on: str | None
    reviewer_notes: str
    independent_of_ai: StrictBool
    used_ai_proposal_as_ground_truth: StrictBool | None
    output_review: OutputReview


class BenchmarkDataset(StrictModel):
    version: Literal['independent-benchmarks-v1']
    benchmarks: list[Benchmark]


def qualify_benchmark(b,case,*,max_date_difference_days=0):
    errors=[];reviewer=(b.reviewer or '').strip()
    if b.card_identity.model_dump()!=case['target'] or b.requested_condition!=case['target']['condition']:
        errors.append('benchmark_identity_or_condition_mismatch')
    if b.verification_status!='independently_reviewed':errors.append('benchmark_not_independently_reviewed')
    if not reviewer or reviewer.casefold().startswith(('openai','model','ai:','chatgpt','gpt')):errors.append('independent_reviewer_required')
    if not b.independent_of_ai or b.used_ai_proposal_as_ground_truth is not False:errors.append('independent_reference_required')
    if b.condition_specificity!='explicit_condition':errors.append('explicit_condition_benchmark_required')
    if b.reference_methodology=='unknown' or not b.reference_source or not b.reviewer_notes.strip():errors.append('benchmark_source_methodology_notes_required')
    try:
        refdate=date.fromisoformat(b.reference_date)
        reviewed=date.fromisoformat(b.reviewed_on)
        if not refdate<=reviewed<=date.today():errors.append('benchmark_review_date_invalid')
        if abs((refdate-date.fromisoformat(case['as_of'])).days)>max_date_difference_days:
            errors.append('benchmark_date_does_not_match_experiment_cutoff')
    except (ValueError,TypeError):errors.append('benchmark_dates_required')
    value=normalize_money(b.reference_market_value,b.currency)
    if value.amount is None or value.errors:errors.append('valid_explicit_usd_benchmark_price_required')
    endpoints=[normalize_money(v,b.currency) for v in (b.reference_low,b.reference_high)]
    if any(v is not None for v in (b.reference_low,b.reference_high)):
        if any(e.amount is None or e.errors for e in endpoints):errors.append('complete_valid_benchmark_range_required')
        elif value.amount is not None and not Decimal(endpoints[0].amount)<=Decimal(value.amount)<=Decimal(endpoints[1].amount):
            errors.append('benchmark_range_invalid')
    return value.amount,list(dict.fromkeys(errors))


def score_replay(replay,dataset,*,max_date_difference_days=0):
    if type(max_date_difference_days) is not int or max_date_difference_days<0:raise ValueError('Nonnegative date tolerance required')
    dataset=BenchmarkDataset.model_validate(dataset) if isinstance(dataset,dict) else dataset
    ids=[b.case_id for b in dataset.benchmarks]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate benchmark case ID')
    known={c['case_id'] for c in replay['cases']}
    if set(ids)-known:raise ValueError('Benchmark references unknown case')
    by_id={b.case_id:b for b in dataset.benchmarks};rows=[]
    groups={k:[] for k in ('usable_estimate','provisional_estimate')}
    counts={k:0 for k in ('usable_estimate','provisional_estimate','insufficient_evidence')}
    printing_failures=[];condition_failures=[]
    for case in replay['cases']:
        review=case['review'];status=review['result_status'];counts[status]+=1
        row={'case_id':case['case_id'],'result_status':status,'benchmark_status':'missing',
             'absolute_dollar_error':None,'absolute_percentage_error':None,'within_10_percent':None,
             'within_20_percent':None,'estimated_range_contains_benchmark':None,'benchmark_rejection_reasons':[],
             'approved_valuation':status=='usable_estimate','approved_inventory_price':False}
        b=by_id.get(case['case_id'])
        if b is not None:
            value,errors=qualify_benchmark(b,case,max_date_difference_days=max_date_difference_days)
            row['benchmark_rejection_reasons']=errors
            row['benchmark_status']='eligible_independent_attestation' if not errors else 'unavailable_or_ineligible'
            if not errors:
                labels=b.output_review
                if labels.correct_card_printing is not None:printing_failures.append(not labels.correct_card_printing)
                if labels.correct_condition_handling is not None:condition_failures.append(not labels.correct_condition_handling)
                display=review['display_estimate']
                if display and display['scope']=='requested_condition_proposal':
                    benchmark=Decimal(value);estimate=Decimal(display['value'])
                    absolute=abs(estimate-benchmark);ape=absolute/benchmark*100
                    row.update(absolute_dollar_error=str(absolute),absolute_percentage_error=str(ape),
                               within_10_percent=ape<=10,within_20_percent=ape<=20,
                               estimated_range_contains_benchmark=Decimal(display['low'])<=benchmark<=Decimal(display['high']))
                    # Include wrong/unsupported outputs in the error denominator;
                    # review flags expose them instead of improving accuracy by exclusion.
                    row['independent_output_review']=labels.model_dump()
                    row['validated_success']=(ape<=10 and labels.correct_card_printing is True
                        and labels.correct_condition_handling is True and labels.unsupported_pricing_claims is False)
                    groups[status].append(row)
                elif display:row['benchmark_status']='generic_estimate_not_comparable_to_condition_benchmark'
        rows.append(row)
    def metrics(values):
        def percentage(key):return str(Decimal(sum(r[key] is True for r in values))*100/len(values)) if values else None
        return {'scored_estimates':len(values),
                'median_absolute_percentage_error':str(median(Decimal(r['absolute_percentage_error']) for r in values)) if values else None,
                'median_absolute_dollar_error':str(median(Decimal(r['absolute_dollar_error']) for r in values)) if values else None,
                'percentage_within_10_percent':percentage('within_10_percent'),
                'percentage_within_20_percent':percentage('within_20_percent'),
                'percentage_ranges_containing_benchmark':percentage('estimated_range_contains_benchmark'),
                'validated_success_percentage':percentage('validated_success')}
    total=len(rows)
    return {'protocol':'independent-benchmark-evaluation-v1','cases':rows,
            'accuracy_by_status':{k:metrics(v) for k,v in groups.items()},
            'coverage':{'planned_cards':total,**counts,
                        'usable_estimate_coverage':counts['usable_estimate']/total if total else None,
                        'provisional_estimate_coverage':counts['provisional_estimate']/total if total else None,
                        'abstention_rate':counts['insufficient_evidence']/total if total else None},
            'matching':{'human_reviewed_printing_failures':sum(printing_failures) if printing_failures else None,
                        'human_printing_review_count':len(printing_failures),
                        'human_reviewed_condition_failures':sum(condition_failures) if condition_failures else None,
                        'human_condition_review_count':len(condition_failures),
                        'policy_known_printing_mismatch_rows':replay['summary']['known_printing_mismatch_rows_after'],
                        'policy_known_condition_mismatch_rows':replay['summary']['known_condition_mismatch_rows_after']},
            'max_reference_date_difference_days':max_date_difference_days,
            'limitations':['Manual verification is an attestation, not software authentication.',
                           'Provisional errors are reported separately and never counted as approved valuations.',
                           'Absent eligible benchmark values leave pricing accuracy unmeasured.']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--replay',type=Path,required=True);p.add_argument('--benchmarks',type=Path,required=True)
    p.add_argument('--output',type=Path);p.add_argument('--max-date-difference-days',type=int,default=0)
    a=p.parse_args();r=score_replay(json.loads(a.replay.read_text()),json.loads(a.benchmarks.read_text()),
                                  max_date_difference_days=a.max_date_difference_days)
    text=json.dumps(r,indent=2,ensure_ascii=False,allow_nan=False)+'\n'
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text)
    else:print(text,end='')


if __name__=='__main__':main()
