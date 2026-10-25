"""TEST-ONLY proposed contracts, not imported by the production pricing engine.

These fail-closed checks illustrate the documented design. Passing them does not
prove source truth; `verified` is a trusted adapter/reviewer attestation, not a
field the research model is authorized to supply.
"""
import re


def condition_issues(candidate):
    observed = candidate['identity'].get('condition')
    if observed is None:
        return ['condition unknown']
    missing = ' '.join(candidate.get('missing_information', [])).casefold()
    summary = (candidate.get('evidence_summary') or '').casefold()
    issues = []
    if 'condition' in missing:
        issues.append('condition conflicts with missing-information declaration')
    if re.search(r'(condition (?:is )?(?:unknown|not specified)|only raw|only ungraded|beyond ungraded)', summary):
        issues.append('condition conflicts with summary')
    if observed not in {'NM', 'LP', 'MP', 'HP', 'DMG'}:
        issues.append('unreviewed condition label or range')
    return issues


def reference_issues(target, reference):
    """Minimal executable policy illustration, deliberately not a full v2 parser."""
    issues = []
    if reference.get('kind') != 'published_reference':
        issues.append('not a published reference')
    if reference.get('verification_state') != 'verified':
        issues.append('independent verification required')
    if reference.get('identity') != target:
        issues.append('printing or condition mismatch')
    if reference.get('condition_scope') != 'explicit_condition':
        issues.append('explicit condition required')
    if reference.get('benchmark_type') not in {'sold_derived_market_estimate', 'guide'}:
        issues.append('asking or unknown benchmark semantics')
    for field in ('identity', 'condition', 'price', 'currency', 'benchmark_definition', 'price_basis'):
        support = reference.get('field_support', {}).get(field, {})
        if support.get('state') != 'explicit' or support.get('verified') is not True or not support.get('locator'):
            issues.append(field + ' source support required')
    if reference.get('price_basis') != 'card_only_excluding_shipping_and_tax':
        issues.append('card-only semantics required')
    if not reference.get('freshness_reviewed'):
        issues.append('freshness review required')
    return issues
