"""Deterministic evidence routing, matching and existing-engine integration."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from statistics import median
from urllib.parse import urlsplit

from .models import Candidate, claim_id
from .provider import canonical_url
from .verification import Unverified
from ..pricing import Sale, evaluate


def _number(value):
    import re
    m = re.fullmatch(r'([A-Za-z]*)(\d+)/([A-Za-z]*)(\d+)', value.replace(' ', ''))
    return (m[1].upper(), int(m[2]), m[3].upper(), int(m[4])) if m else value.casefold()


def matching_reasons(target, candidate):
    expected, actual = target.identity(), candidate.identity.model_dump()
    reasons = []
    for field, value in expected.items():
        observed = actual[field]
        if field == 'number' and isinstance(observed, str):
            same = _number(observed) == _number(value)
        elif isinstance(value, str) and isinstance(observed, str):
            same = value.strip().casefold() == observed.strip().casefold()
        else:
            same = observed is value if field == 'graded' else observed == value
        if not same:
            reasons.append(field + ' mismatch or unknown')
    return reasons


def qualify_reasons(target, candidate, consulted, as_of, max_age_days):
    reasons = matching_reasons(target, candidate)
    try:
        if canonical_url(candidate.url) not in consulted:
            reasons.append('URL absent from API search sources/citations')
    except ValueError:
        reasons.append('invalid source URL')
    if candidate.kind != 'completed_sale':
        reasons.append('not a completed sale')
    if candidate.identity.graded is not False:
        reasons.append('graded or unknown')
    if candidate.bundle is not False or candidate.quantity != 1:
        reasons.append('not an explicit single-card transaction')
    if candidate.price_is_item_only is not True:
        reasons.append('card-only paid price unconfirmed')
    if not candidate.source_record_id or not candidate.source_record_id.strip():
        reasons.append('missing genuine source record ID')
    if candidate.currency != 'USD':
        reasons.append('USD comparable required; no inferred FX conversion')
    try:
        amount = Decimal(candidate.item_price)
        if not amount.is_finite() or amount <= 0:
            reasons.append('invalid item price')
        if candidate.shipping is not None:
            shipping = Decimal(candidate.shipping)
            if not shipping.is_finite() or shipping < 0:
                reasons.append('invalid shipping context')
    except (InvalidOperation, ValueError, TypeError):
        reasons.append('invalid money')
    try:
        sold = date.fromisoformat(candidate.sold_on)
        if not 0 <= (as_of - sold).days <= max_age_days:
            reasons.append('sale outside configured window')
    except (ValueError, TypeError):
        reasons.append('missing or invalid actual sale date')
    return reasons


def value_research(target, research, settings, verifier=None):
    verifier = verifier or Unverified()
    as_of = date.fromisoformat(research['as_of'])
    consulted = set()
    for url in research.get('sources', []):
        try:
            consulted.add(canonical_url(url))
        except ValueError:
            continue
    sold, rows, references, listings = [], [], [], []
    seen_ids, seen_urls = set(), set()
    for data in (research.get('evidence') or {}).get('candidates', []):
        candidate = Candidate.model_validate(data)
        record = {'claim_id':claim_id(candidate), 'candidate':candidate.model_dump(),
                  'independently_substantiated':False}
        if candidate.kind in ('market_reference', 'active_listing'):
            record['matching_issues'] = matching_reasons(target, candidate)
            try:
                record['source_consulted'] = canonical_url(candidate.url) in consulted
            except ValueError:
                record['source_consulted'] = False
            (references if candidate.kind == 'market_reference' else listings).append(record)
            continue
        reasons = qualify_reasons(target, candidate, consulted, as_of, settings.max_age_days)
        if not reasons:
            url = canonical_url(candidate.url)
            identity = (urlsplit(url).hostname, candidate.source_record_id)
            if identity in seen_ids or url in seen_urls:
                reasons.append('duplicate evidence URL or source transaction')
            else:
                seen_ids.add(identity)
                seen_urls.add(url)
        if not reasons:
            verification = verifier.verify(target, candidate, as_of)
            record['verification'] = verification.__dict__
            if not verification.verified:
                reasons.append(verification.reason)
            else:
                record['independently_substantiated'] = True
                sold.append(Sale(target.card(), Decimal(candidate.item_price),
                                 None if candidate.shipping is None else Decimal(candidate.shipping),
                                 date.fromisoformat(candidate.sold_on), canonical_url(candidate.url),
                                 source=urlsplit(candidate.url).hostname, transaction_id=candidate.source_record_id,
                                 verified_by=verification.reviewer, verified_on=date.fromisoformat(verification.reviewed_on),
                                 verification_notes=verification.reason+'; artifact SHA-256 '+verification.artifact_sha256,
                                 price_confirmed=True, condition_confirmed=True))
        record['rejections'] = reasons
        rows.append(record)
    result = evaluate(target.card(), sold, as_of, minimum_sales=settings.minimum_sales,
                      max_age_days=settings.max_age_days, verification_as_of=datetime.now(timezone.utc).date())
    amounts = [s.item_price for s in result.accepted]
    quality = {'qualified_sold_count':len(result.accepted), 'candidate_sold_count':len(rows),
               'rejected_candidate_count':sum(bool(r['rejections']) for r in rows) + len(result.rejected),
               'source_domain_count':len({urlsplit(s.url).hostname for s in result.accepted}),
               'consulted_domain_count':len({urlsplit(u).hostname for u in consulted}),
               'oldest_comp_age_days':max(((as_of-s.sold_on).days for s in result.accepted), default=None),
               'median_comp_age_days':median([(as_of-s.sold_on).days for s in result.accepted]) if result.accepted else None,
               'min_item_price':str(min(amounts)) if amounts else None,
               'max_item_price':str(max(amounts)) if amounts else None,
               'max_to_min_ratio':str(max(amounts)/min(amounts)) if amounts else None,
               'confidence_score':None,
               'note':'Objective evidence indicators, not a calibrated probability. Domain counts do not prove independent transactions.'}
    return {'valuation':result.to_dict(), 'evidence_quality':quality,
            'sold_candidates':rows, 'market_references':references, 'active_listings':listings,
            'independently_validated_accuracy':False, 'research':research}
