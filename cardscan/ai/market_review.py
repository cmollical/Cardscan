"""Three-outcome review of normalized AI evidence, not transaction authentication."""
from datetime import date
from decimal import Decimal
import re

from .market_models import MarketEstimate
from .normalization import normalize_identity, normalize_proposal, SetAliasRegistry
from .provider import canonical_url

POLICY_VERSION='normalized-market-review-v1'


def review_proposal(target,proposal,api_urls,as_of,response_id,*,max_age_days=90,transaction_records=None,source_reviews=None,research_retrieved_at=None):
    """Never edits a model proposal or computes a replacement estimate/average.

    Usable status requires reviewed source support, not authenticated transactions.
    A proposed scalar may otherwise be retained only for review, with null approved
    valuation. External reviews bind to the raw source claim and cannot be model flags.
    """
    raw=proposal.model_dump() if hasattr(proposal,'model_dump') else proposal
    parsed=MarketEstimate.model_validate(raw)
    registry=SetAliasRegistry()
    norm=normalize_proposal(parsed.model_dump(),response_id,registry=registry,transaction_records=transaction_records)
    n=norm['normalized_proposal'];global_errors=[];warnings=[];conflicts=[]
    expected,requested_changes,requested_errors=normalize_identity(target.identity(),registry)
    if requested_errors:global_errors.append('requested_identity_not_resolved_by_reviewed_catalog')
    echo,_,echo_errors=normalize_identity(raw['card_identity'],registry)
    if echo_errors or any(echo.get(k)!=v for k,v in expected.items()):global_errors.append('requested_identity_mismatch')
    if raw['requested_condition']!=target.condition:global_errors.append('requested_condition_mismatch')
    consulted=set()
    for u in api_urls:
        try:consulted.add(canonical_url(u))
        except ValueError:pass
    selected=set(n['supporting_source_ids']);seen_transactions=set();seen_claims=set();support=[]
    for row in norm['rows']:
        s=row['normalized_source'];identity=s['observed_identity'];issues=[];notes=[];contradictions=[]
        for error in row['normalization_errors']:
            issues.append('representation_unresolved: '+error)
        if row['canonical_page_url'] not in consulted:issues.append('source_url_not_returned_by_api')
        for field,wanted in expected.items():
            if field=='condition':continue
            actual=identity.get(field)
            if actual is None:notes.append('missing_identity:'+field)
            elif field=='number' and '/' not in str(actual):notes.append('collector_denominator_missing')
            elif actual!=wanted:issues.append('printing_mismatch:'+field)
        if any(identity.get(k) is None for k in ('name','set_name','number')):issues.append('card_identification_incomplete')
        if identity.get('graded') is True:issues.append('graded_card_excluded')
        condition=identity.get('condition');scope=s['condition_scope']
        label=s['condition_label']
        missing=' '.join(row['raw_source']['missing_information']).casefold()
        summary=(s['source_summary'] or '').casefold()
        if scope=='explicit_condition':
            if condition is None or label is None or condition!=label:
                issues.append('contradictory_condition_fields');contradictions.append('explicit scope, observed condition and label disagree')
            elif condition!=target.condition:issues.append('condition_mismatch')
            if row['condition_label_error']:issues.append('condition_label_unreviewed')
            if condition is not None and (re.search(r'(?:exact|precise|unknown|missing|unstated|not stated)(?: raw| physical| canonical| source)? condition|condition(?: label| scope| specificity)?(?: is)? (?:unknown|missing|unstated|not stated)',missing)
                                         or re.search(r'condition (?:is )?(?:unknown|not specified)|only raw|only ungraded|beyond ungraded',summary)):
                issues.append('contradictory_condition_narrative');contradictions.append('observed condition conflicts with missing information or summary')
        elif condition is not None:
            issues.append('contradictory_condition_scope');contradictions.append('non-specific scope asserts specific condition')
        if s['reported_price'] is None:issues.append('no_valid_source_price')
        if s['currency']!='USD':issues.append('explicit_usd_required')
        if s['price_basis']!='item_only':issues.append('item_only_price_required')
        if re.search(r'shipping exclusion|(?:whether|unknown).*shipping|shipping.*(?:included|confirmation)|tax exclusion',missing):
            issues.append('shipping_or_tax_basis_uncertain');contradictions.append('item-only flag conflicts with unresolved source price basis')
        if s['price_type']=='completed_sale_report' and re.search(r'accepted offer|closing bid|actual paid price|sold status',missing):
            issues.append('completed_sale_price_or_status_uncertain')
        if s['observation_kind']=='unknown' or not s['price_meaning']:issues.append('price_meaning_or_observation_unknown')
        if s['source_date'] is None:notes.append('freshness_unknown')
        else:
            try:
                age=(as_of-date.fromisoformat(s['source_date'])).days
                if not 0<=age<=max_age_days:issues.append('source_date_outside_window')
            except ValueError:issues.append('source_date_invalid')
        transaction=row['marketplace_transaction']
        if transaction:
            key=(transaction['source'],transaction['id'])
            if key in seen_transactions:issues.append('duplicate_marketplace_transaction')
            seen_transactions.add(key)
        signature=(row['canonical_page_id'],s['reported_price'],s['source_date'],s['price_type'],tuple(sorted(identity.items())))
        if signature in seen_claims:issues.append('duplicate_evidence_claim')
        seen_claims.add(signature)
        if s['price_type'] in {'active_asking_price','unknown'}:issues.append('asking_or_unknown_context_not_market_anchor')
        specific=scope=='explicit_condition' and condition==target.condition and label==condition
        row.update(issues=list(dict.fromkeys(issues)),warnings=notes,contradictions=contradictions,
                   requested_as_support=row['internal_row_id'] in selected,
                   explicit_requested_condition=specific,source_verification='unverified_ai_extraction',
                   evidence_classification={'completed_sale_report':'unverified_completed_sale_claim',
                      'published_market_reference':'unverified_published_reference_claim',
                      'active_asking_price':'active_asking_price','unknown':'unknown_evidence'}[s['price_type']],
                   generic_condition_context=scope in {'generic_ungraded','mixed','unknown'})
        # An external claim-bound review confirms source support, not source truth
        # or a marketplace transaction. No flag from AI output is read here.
        review=(source_reviews or {}).get(row['internal_row_id'],{})
        reviewer=review.get('reviewer')
        try:review_date=date.fromisoformat(review.get('reviewed_on',''))<=date.today()
        except (ValueError,TypeError):review_date=False
        verified=(review.get('raw_source_sha256')==row['raw_source_sha256'] and review.get('source_substantiates') is True
                  and isinstance(reviewer,str) and bool(reviewer.strip()) and not reviewer.casefold().startswith(('model','openai','ai:'))
                  and review_date and bool(re.fullmatch(r'[a-f0-9]{64}',review.get('artifact_sha256',''))))
        if verified:
            row['source_verification']='independent_source_review_attestation'
            row['independent_review']=dict(review)
            if s['price_type']=='published_market_reference':row['evidence_classification']='reviewed_published_market_reference'
            # A source-page review alone does not authenticate a sale transaction.
        row['eligible_anchor']=not issues
        row['research_retrieved_at']=research_retrieved_at
        row['source_page_retrieved_at']=None
        row['independently_verified_source_support']=bool(verified)
        if row['requested_as_support'] and row['eligible_anchor']:support.append(row)
    prices=[Decimal(r['normalized_source']['reported_price']) for r in support]
    condition_support=[r for r in support if r['explicit_requested_condition']]
    specific_prices=[Decimal(r['normalized_source']['reported_price']) for r in condition_support]
    if len(specific_prices)>=2 and max(specific_prices)/min(specific_prices)>Decimal('1.25'):
        conflicts.append({'kind':'material_condition_matched_price_spread','prices':[str(p) for p in specific_prices],
                          'ratio':str(max(specific_prices)/min(specific_prices)),
                          'meaning':'Review trigger above 25% spread, not an outlier-removal or accuracy rule.'})
    if norm['ambiguous_support_ids']:warnings.append('Original support IDs resolve to multiple rows; all rows retained, no invented independence')
    if norm['unresolved_support_ids']:global_errors.append('supporting_source_ids_unresolved')
    invalid_money=[f for f,v in norm['proposal_money'].items() if v['errors']]
    if invalid_money:global_errors.append('proposal_monetary_format_invalid')
    vals=[n[k] for k in ('estimated_market_value','estimated_low','estimated_high')]
    has_estimate=all(v is not None for v in vals)
    if has_estimate and not Decimal(vals[1])<=Decimal(vals[0])<=Decimal(vals[2]):global_errors.append('invalid_estimate_range')
    if raw['insufficient_evidence']:
        global_errors.append('model_abstained')
        if any(v is not None for v in vals):global_errors.append('contradictory_model_abstention')
    elif not has_estimate:global_errors.append('no_complete_proposal')
    if has_estimate and not raw['reasoning_summary'].strip():global_errors.append('missing_estimate_explanation')
    if not support:global_errors.append('no_identifiable_eligible_priced_anchor')
    generic=raw['valuation_type']=='generic_ungraded_reference'
    if not generic and not condition_support:global_errors.append('no_explicit_requested_condition_anchor')
    evidence_prices=prices if generic else specific_prices
    if has_estimate and evidence_prices and not any(Decimal(vals[1])<=p<=Decimal(vals[2]) for p in evidence_prices):
        global_errors.append('no_relevant_source_price_within_proposed_range')
    all_specific_exact=bool(condition_support) and all(not r['warnings'] for r in condition_support)
    excluded=[r['internal_row_id'] for r in norm['rows'] if r['requested_as_support'] and r['issues']]
    if excluded:warnings.append('Some model-designated support is excluded; proposal retained for review only if other eligible anchors support it')
    if support and any(r['source_verification']=='unverified_ai_extraction' for r in support):warnings.append('Source prices and source facts remain unverified AI claims')
    if support and any(r['warnings'] for r in support):warnings.append('Missing identity/freshness fields remain unknown')
    if generic:warnings.append('Generic reference is not requested-condition pricing')
    if conflicts:warnings.append('Material source price disagreement is preserved; no averaging or outlier removal')
    if global_errors:status='insufficient_evidence'
    elif warnings or not all_specific_exact or raw['review_recommended']:status='provisional_estimate'
    else:status='usable_estimate'
    display=None if status=='insufficient_evidence' else {
        'value':n['estimated_market_value'],'low':n['estimated_low'],'high':n['estimated_high'],'currency':'USD',
        'scope':'generic_reference_not_requested_condition' if generic else 'requested_condition_proposal',
        'review_required':status!='usable_estimate','approved_inventory_price':False}
    approved=display if status=='usable_estimate' else None
    return {'policy_version':POLICY_VERSION,'max_source_age_days':max_age_days,'result_status':status,'requested_identity':target.identity(),
            'normalized_requested_identity':expected,'requested_identity_transformations':requested_changes,
            'original_model_proposal':raw,'normalization':norm,'display_estimate':display,
            'accepted_valuation':approved,'approval_status':'not_approved_for_inventory',
            'remaining_validation_errors':list(dict.fromkeys(global_errors)), 'warnings':warnings,
            'substantive_conflicts':conflicts,'excluded_support_rows':excluded,
            'eligible_support_rows':[r['internal_row_id'] for r in support],
            'condition_matched_support_rows':[r['internal_row_id'] for r in condition_support],
            'canonical_support_pages':len({r['canonical_page_id'] for r in support}),
            'known_distinct_transactions':len({(r['marketplace_transaction']['source'],r['marketplace_transaction']['id'])
                                               for r in support if r['marketplace_transaction']}),
            'independently_validated_accuracy':False,'incremental_api_cost_usd':'0'}
