"""Deterministic replay of exact retained final texts. No SDK, network or paid calls."""
import argparse
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from .market_models import MarketEstimate
from .market_policy import validate_estimate, money as legacy_money
from .market_review import review_proposal
from .models import ResearchTarget, digest

ROOT=Path(__file__).resolve().parents[2]
DEFAULT_BUNDLE=ROOT/'research/evidence/market-ai-2026-10-25/raw-final-texts.json'


def replay(bundle):
    if bundle.get('format_version')!='exact-final-texts-v1':raise ValueError('Exact final text bundle required')
    ids=[r['case_id'] for r in bundle['records']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate replay case ID')
    cases=[];before_parseable=0;before_prices=0;after_prices=0
    for record in bundle['records']:
        text=record['final_text']
        if sha256(text.encode()).hexdigest()!=record['final_text_sha256']:raise ValueError('Original response text hash mismatch')
        target=ResearchTarget(**record['target']);as_of=date.fromisoformat(record['as_of'])
        raw=json.loads(text)
        parsed=MarketEstimate.model_validate(raw)
        _,original_errors=validate_estimate(target,parsed,record['api_returned_urls'],as_of)
        if original_errors!=record['original_validation_errors']:
            raise ValueError('Original validator replay differs from recorded original errors')
        try:
            before_parseable+=all(legacy_money(raw[k]) is not None for k in ('estimated_market_value','estimated_low','estimated_high'))
        except ValueError:pass
        for source in raw['sources']:
            try:before_prices+=legacy_money(source['reported_price']) is not None
            except ValueError:pass
        reviewed=review_proposal(target,parsed,record['api_returned_urls'],as_of,record['response_id'],research_retrieved_at=record['retrieved_at'])
        after_prices+=sum(r['monetary_normalization']['amount'] is not None and not r['monetary_normalization']['errors']
                          for r in reviewed['normalization']['rows'])
        cases.append({'case_id':record['case_id'],'target':record['target'],'as_of':record['as_of'],
                      'response_id':record['response_id'],'original_text_sha256':record['final_text_sha256'],
                      'original_retrieved_at':record['retrieved_at'],
                      'original_status':record['original_status'],'original_validation_errors':original_errors,
                      'structurally_parseable_before':True,'structurally_parseable_after':True,
                      'original_api_cost_usd':record['estimated_api_cost_usd'],
                      'original_api_usage':record['api_usage'],'original_latency_seconds':record['latency_seconds'],
                      'review':reviewed})
    rows=[r for c in cases for r in c['review']['normalization']['rows']]
    summary={'model_proposals':len(cases),'structurally_parseable_before':len(cases),'structurally_parseable_after':len(cases),
             'complete_numeric_proposals_before':int(before_parseable),
             'complete_numeric_proposals_after':sum(all(v['amount'] is not None and not v['errors'] for v in c['review']['normalization']['proposal_money'].values()) for c in cases),
             'evidence_rows_before':sum(len(json.loads(r['final_text'])['sources']) for r in bundle['records']),
             'evidence_rows_after':len(rows),'numeric_source_prices_before':before_prices,'numeric_source_prices_after':after_prices,
             'usable_estimates_before':0,'provisional_estimates_before':0,
             'explicit_insufficient_outcomes_before':sum(r['original_status']=='insufficient_evidence' for r in bundle['records']),
             'invalid_estimate_outcomes_before':sum(r['original_status']=='invalid_estimate' for r in bundle['records']),
             'usable_estimates_after':sum(c['review']['result_status']=='usable_estimate' for c in cases),
             'provisional_estimates_after':sum(c['review']['result_status']=='provisional_estimate' for c in cases),
             'insufficient_evidence_after':sum(c['review']['result_status']=='insufficient_evidence' for c in cases),
             'substantive_contradictory_rows_after':sum(bool(r['contradictions']) for r in rows),
             'cross_source_price_conflicts_after':sum(len(c['review']['substantive_conflicts']) for c in cases),
             'known_printing_mismatch_rows_after':sum(any(i.startswith('printing_mismatch:') for i in r['issues']) for r in rows),
             'known_condition_mismatch_rows_after':sum('condition_mismatch' in r['issues'] for r in rows),
             'conflict_before_note':'The original validator did not produce a comparable substantive-conflict count; no numeric baseline is invented.',
             'incremental_api_cost_usd':'0','paid_api_calls':0,'accuracy_metrics':None}
    return {'protocol':'normalized-market-replay-v1','input_bundle_sha256':digest(bundle),
            'original_artifact_sha256':bundle['artifact_sha256'],'model_instructions_sha256':bundle['model_instructions_sha256'],
            'summary':summary,'cases':cases,
            'limitations':['Normalizing syntax and aliases does not verify source truth.',
                           'Displayable provisional proposals are not approved inventory prices.',
                           'No independent benchmark values have been supplied.']}


def render_markdown(result):
    s=result['summary']
    lines=['# Original-response normalization replay','',
           'No paid API calls. Original final output text is preserved unchanged and hash-checked. All amounts remain model proposals, not verified market values.','',
           '| Card | Original proposal | Original status | Revised status | Display for review | Approved valuation |',
           '| --- | --- | --- | --- | --- | --- |']
    for c in result['cases']:
        r=c['review'];d=r['display_estimate'];raw=r['original_model_proposal']
        lines.append(f"| {c['case_id']} | {raw['estimated_market_value']} | {c['original_status']} | {r['result_status']} | {d['value']+' USD' if d else 'none'} | {'none' if r['accepted_valuation'] is None else r['accepted_valuation']['value']} |")
    lines+=['','## Measured before and after','','| Metric | Original | Normalized |','| --- | ---: | ---: |']
    for label,a,b in [('Model proposals','model_proposals','model_proposals'),
                      ('Structurally parseable proposals','structurally_parseable_before','structurally_parseable_after'),
                      ('Complete decimal-parsed proposal/range','complete_numeric_proposals_before','complete_numeric_proposals_after'),
                      ('Retained evidence rows','evidence_rows_before','evidence_rows_after'),
                      ('Decimal-parsed source prices','numeric_source_prices_before','numeric_source_prices_after'),
                      ('Usable estimates','usable_estimates_before','usable_estimates_after'),
                      ('Provisional estimates','provisional_estimates_before','provisional_estimates_after'),
                      ('Explicit insufficient-evidence outcomes','explicit_insufficient_outcomes_before','insufficient_evidence_after')]:
        lines.append(f'| {label} | {s[a]} | {s[b]} |')
    lines+=['',f"The original run had {s['invalid_estimate_outcomes_before']} invalid-estimate outcomes, not explicit model abstentions. They are not retroactively relabeled as insufficient-evidence outcomes.",
            '',f"Remaining substantive findings: {s['substantive_contradictory_rows_after']} rows with contradictions; {s['cross_source_price_conflicts_after']} cross-source price-spread conflicts; {s['known_condition_mismatch_rows_after']} known condition mismatch rows. The old validator did not measure a directly comparable conflict count.",
            '', '## Per-card decisions']
    for c in result['cases']:
        r=c['review']
        lines+=['',f"### {c['case_id']}",'',f"**{r['result_status']}**. Original estimate and range: {r['original_model_proposal']['estimated_market_value']} ({r['original_model_proposal']['estimated_low']}–{r['original_model_proposal']['estimated_high']}).",'',
                'Remaining decision errors: '+(', '.join(r['remaining_validation_errors']) or 'none; review warnings still apply')+'.',
                'Warnings: '+'; '.join(r['warnings'])+'.','', '| Row | Source | Normalized price | Evidence classification | Exclusion / uncertainty |','| --- | --- | --- | --- | --- |']
        for row in r['normalization']['rows']:
            source=row['normalized_source'];issues=row['issues']+row['warnings']
            lines.append(f"| {row['position']} | [{source['source_name']}]({row['canonical_page_url'] or source['url']}) | {source['reported_price'] or 'unknown'} {source['currency'] or ''} | {row['evidence_classification']} | {'; '.join(issues) or 'no row-level exclusion; source claims still unverified'} |")
        if r['substantive_conflicts']:lines+=['','Price conflicts: '+json.dumps(r['substantive_conflicts'],ensure_ascii=False)]
    lines+=['','Full row transformations, raw fields, identifiers, original errors and decisions are preserved in the adjacent JSON report. Accuracy remains unmeasured without independent benchmark prices.','']
    return '\n'.join(lines)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,default=DEFAULT_BUNDLE)
    p.add_argument('--output',type=Path,required=True,help='JSON report; adjacent .md report also written')
    a=p.parse_args();r=replay(json.loads(a.bundle.read_text()))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    a.output.with_suffix('.md').write_text(render_markdown(r))
    print(json.dumps(r['summary'],indent=2))


if __name__=='__main__':main()
