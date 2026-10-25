"""Validate AI judgment without pretending it is independent source verification."""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import urlsplit
from .provider import canonical_url
from .valuation import _number


def same(field,a,b):
    if field=='number' and isinstance(a,str) and isinstance(b,str):return _number(a)==_number(b)
    if isinstance(a,str) and isinstance(b,str):return a.strip().casefold()==b.strip().casefold()
    return type(a) is type(b) and a==b


def money(value):
    if value is None:return None
    try:
        d=Decimal(value)
        if not d.is_finite() or d<=0:raise ValueError('Price must be finite and positive')
        return d
    except (InvalidOperation,TypeError):raise ValueError('Invalid decimal price')


def validate_estimate(target,estimate,consulted_urls,as_of,max_age_days=90):
    expected=target.identity(); errors=[];warnings=[];rows=[];anchors={};seen_ids=set();seen_records=set()
    echoed=estimate.card_identity.model_dump()
    if any(not same(k,echoed[k],v) for k,v in expected.items()):errors.append('Requested identity echo differs from exact target')
    if estimate.requested_condition!=target.condition:errors.append('Requested condition differs from target')
    consulted=set()
    for url in consulted_urls:
        try:consulted.add(canonical_url(url))
        except ValueError:continue
    for source in estimate.sources:
        s=source.model_dump();issues=[];notes=[];identity=s['observed_identity'];partial=[]
        if not s['id'].strip() or s['id'] in seen_ids:errors.append('Duplicate or empty source ID')
        seen_ids.add(s['id'])
        try:
            url=canonical_url(s['url'])
            if url not in consulted:issues.append('URL absent from API sources/citations')
        except ValueError:url=None;issues.append('Invalid evidence URL')
        for k,v in expected.items():
            if k=='condition':continue
            if identity[k] is None:partial.append(k)
            elif not same(k,identity[k],v):issues.append(k+' printing mismatch')
        # A name/set/number match identifies a plausible printing lead; remaining
        # unknown dimensions mandate provisional labeling, never assumed facts.
        if any(identity[k] is None for k in ('name','set_name','number')):
            issues.append('Insufficient card identification')
        if partial:notes.append('Unknown source identity fields: '+', '.join(partial))
        condition=identity['condition']
        missing=' '.join(s['missing_information']).casefold();summary=(s['source_summary'] or '').casefold()
        contradiction=condition is not None and ('condition' in missing or re.search(
            r'condition (?:is )?(?:unknown|not specified)|only raw|only ungraded|beyond ungraded',summary))
        if contradiction:issues.append('Condition contradicts summary/missing-information')
        if s['condition_scope']=='explicit_condition':
            if condition not in {'NM','LP','MP','HP','DMG'} or not s['condition_label']:
                issues.append('Explicit condition not supported by a source label')
            elif condition!=target.condition:issues.append('Wrong condition')
            labels={'nm':'NM','near mint':'NM','lp':'LP','lightly played':'LP','mp':'MP','moderately played':'MP',
                    'hp':'HP','heavily played':'HP','dmg':'DMG','damaged':'DMG'}
            if s['condition_label'] and labels.get(s['condition_label'].strip().casefold())!=condition:
                issues.append('Unreviewed or contradictory source condition label')
        elif condition is not None:
            issues.append('Non-specific condition scope cannot assert requested condition')
        price=None
        try:price=money(s['reported_price'])
        except ValueError:issues.append('Invalid reported source price')
        if price is None:notes.append('Source price missing')
        if s['currency']!='USD':issues.append('USD price required; no invented currency conversion')
        if s['price_basis']!='item_only':issues.append('Item-only price basis unknown or includes shipping')
        if s['observation_kind']=='unknown':issues.append('No claimed observed source content')
        if not s['price_meaning']:issues.append('Price meaning unknown')
        if s['source_date'] is not None:
            try:
                age=(as_of-date.fromisoformat(s['source_date'])).days
                if age<0 or age>max_age_days:issues.append('Source date outside research window')
            except ValueError:issues.append('Invalid source date')
        else:notes.append('Source date unknown; freshness unconfirmed')
        signature=(url,s['reported_price'],s['source_date'],s['price_type'],tuple(identity.items()))
        if signature in seen_records:issues.append('Duplicate evidence claim')
        seen_records.add(signature)
        if s['price_type'] in {'active_asking_price','unknown'}:notes.append('Supplementary context, not a market-clearing anchor')
        if not issues and price is not None and s['price_type'] in {'completed_sale_report','published_market_reference'}:
            anchors[s['id']]={'condition_specific':s['condition_scope']=='explicit_condition',
                              'exact_claimed_identity':not partial,'dated':s['source_date'] is not None}
        rows.append({'source':s,'verification_status':'unverified_ai_extraction',
                     'api_returned_url':url in consulted if url else False,
                     'identity_match':'mismatched' if any('mismatch' in i for i in issues) else 'partial_claimed_match' if partial else 'claimed_match',
                     'issues':issues,'warnings':notes,'independently_verified':False})
    used=estimate.supporting_source_ids
    if len(used)!=len(set(used)):errors.append('Repeated supporting source ID')
    if any(i not in seen_ids for i in used):errors.append('Unknown supporting source ID')
    values=[estimate.estimated_market_value,estimate.estimated_low,estimate.estimated_high]
    parsed=[]
    for v in values:
        try:parsed.append(money(v))
        except ValueError:errors.append('Invalid estimated price');parsed.append(None)
    has_estimate=all(v is not None for v in parsed)
    if any(v is not None for v in parsed) and not has_estimate:errors.append('Estimate and both range endpoints must be present together')
    if has_estimate and not parsed[1]<=parsed[0]<=parsed[2]:errors.append('Estimate must lie within low/high range')
    if estimate.insufficient_evidence:
        if any(v is not None for v in values) or estimate.valuation_type!='insufficient_evidence' or estimate.recommendation!='insufficient_evidence':
            errors.append('Abstention must have null prices and insufficient-evidence labels')
        if used:errors.append('Abstention cannot claim supporting estimate sources')
    elif not has_estimate or estimate.valuation_type=='insufficient_evidence' or estimate.recommendation=='insufficient_evidence':
        errors.append('Missing estimate or inconsistent insufficient-evidence flags')
    if has_estimate:
        if not used or any(i not in anchors for i in used):errors.append('Estimate relies on missing, mismatched, asking-only or unsupported evidence')
        chosen=[anchors[i] for i in used if i in anchors]
        specific=any(a['condition_specific'] for a in chosen)
        if estimate.valuation_type in {'condition_specific_market_estimate','provisional_condition_estimate'} and not specific:
            errors.append('Condition-specific estimate lacks explicit requested-condition evidence')
        if estimate.valuation_type=='condition_specific_market_estimate' and any(not a['exact_claimed_identity'] for a in chosen):
            errors.append('Incomplete printing requires provisional labeling')
        if estimate.valuation_type=='generic_ungraded_reference' and not estimate.review_recommended:
            errors.append('Generic reference requires review and is not requested-condition pricing')
        if estimate.valuation_type!='condition_specific_market_estimate' and estimate.recommendation=='usable_estimate':
            errors.append('Generic/provisional output cannot be labeled usable condition estimate')
        needs_review=(estimate.valuation_type!='condition_specific_market_estimate' or
                      any(not a['dated'] or not a['exact_claimed_identity'] for a in chosen))
        if needs_review:
            warnings.append('Review required: generic/provisional identity, condition, or freshness limitations')
        if estimate.recommendation=='review_recommended' and not estimate.review_recommended:
            errors.append('Review recommendation flags disagree')
        # Model judgment remains intact; policy can downgrade its recommendation.
        result=estimate.model_dump()
        if needs_review or result['review_recommended']:result.update(review_recommended=True,recommendation='review_recommended')
    else:result=estimate.model_dump()
    warnings.extend(note for row in rows if row['source']['id'] in used for note in row['warnings'])
    result.update(source_audit=rows,policy_warnings=warnings,independently_validated_accuracy=False,
                  independent_transaction_count=0,confidence_percentage=None,
                  distinction='AI market estimate; reported source facts are unverified AI extractions, not authenticated transactions.')
    return result,errors
