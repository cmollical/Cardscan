"""Verify references independently, without changing the completed-sale evaluator."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

from ..ai.models import digest
from ..ai.valuation import _number
from .models import VerificationRecord
from .transport import canonical_source_url, SourceRetrievalError


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None: raise ValueError('Timezone required')
    return parsed.astimezone(timezone.utc)


def same(field, actual, expected):
    if field == 'price':
        try:
            a, b = Decimal(str(actual)), Decimal(str(expected))
            return a.is_finite() and b.is_finite() and a == b
        except (InvalidOperation, ValueError): return False
    if field == 'number' and isinstance(actual,str) and isinstance(expected,str):
        return _number(actual) == _number(expected)
    if isinstance(actual,str) and isinstance(expected,str):
        return actual.strip().casefold() == expected.strip().casefold()
    return type(actual) is type(expected) and actual == expected


class ReferenceVerifier:
    def __init__(self, adapters, transport, *, purpose='research', max_age_days=7):
        if purpose not in {'research','commercial'} or type(max_age_days) is not int or not 0 <= max_age_days <= 365:
            raise ValueError('Explicit purpose and valid freshness window required')
        self.adapters = {a.source:a for a in adapters}
        self.transport, self.purpose, self.max_age_days = transport, purpose, max_age_days
        self.seen = set()  # Invocation-local deduplication, not a price cache.

    def verify(self, target, candidate, *, now=None):
        if now is not None and now.tzinfo is None: raise ValueError('Timezone required for verification')
        record = VerificationRecord(candidate.source, candidate.url, target.identity(),
                                    ai_claims=candidate.claims, purpose=self.purpose)
        try:
            record.canonical_url = canonical_source_url(candidate.url)
            adapter = self.adapters.get(candidate.source)
            if adapter is None or not adapter.accepts(record.canonical_url):
                raise ValueError('No approved adapter for this source URL')
        except ValueError as exc:
            record.rejection_reasons.append(str(exc)); record.transition('rejected'); return record
        p = adapter.permission
        record.permission = asdict(p)
        if (p.source != adapter.source or not p.retrieval_allowed or not p.minimal_retention_allowed
                or not p.references or not p.reviewed_on or (self.purpose=='commercial' and not p.commercial_allowed)):
            record.rejection_reasons.append('Source permission does not cover retrieval, minimal retention or requested purpose')
            record.transition('permission_blocked'); return record
        record.transition('permission_checked')
        key = digest({'source':candidate.source,'url':record.canonical_url,'variant':candidate.variant,
                      'target':target.identity(),'method':adapter.method})
        record.reference_key = key
        if key in self.seen:
            record.rejection_reasons.append('Duplicate reference in this verification session')
            record.transition('duplicate'); return record
        try:
            document = self.transport.get(record.canonical_url)
            if canonical_source_url(document.url) != record.canonical_url:
                raise ValueError('Retrieved source URL differs from candidate URL')
            if not re.fullmatch(r'[0-9a-f]{64}', document.sha256): raise ValueError('Invalid source content hash')
            retrieved = timestamp(document.retrieved_at)
            verification_time = now or datetime.now(timezone.utc)
            if not timedelta(0) <= verification_time - retrieved <= timedelta(minutes=5):
                raise ValueError('Source retrieval timestamp is stale or future')
            record.retrieved_at, record.content_sha256 = document.retrieved_at, document.sha256
            record.transition('retrieved')
            record.fields = adapter.extract(document, candidate.variant)
            record.extraction_method = adapter.method
            record.transition('extracted')
        except (SourceRetrievalError, OSError, TimeoutError) as exc:
            record.rejection_reasons.append(f'Retrieval failure: {type(exc).__name__}')
            record.transition('retrieval_failed'); return record
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            record.rejection_reasons.append(f'Invalid source document: {type(exc).__name__}')
            record.transition('rejected'); return record
        self.seen.add(key)
        mismatch = False
        condition = record.fields.get('condition')
        if condition is not None and condition.substantiated:
            if condition.value in {'NM','LP','MP','HP','DMG'}:
                record.condition_scope = 'explicit_condition'
            elif isinstance(condition.value,str) and condition.value.casefold() in {'raw','ungraded','generic ungraded'}:
                record.condition_scope = 'generic_ungraded'
            else:
                record.condition_scope = 'ambiguous'
        for name, expected in target.identity().items():
            evidence = record.fields.get(name)
            if evidence is None or not evidence.substantiated:
                record.rejection_reasons.append(name + ' not independently substantiated')
            elif not same(name,evidence.value,expected):
                record.rejection_reasons.append(name + ' source mismatch or non-specific scope')
                if name != 'condition' or record.condition_scope == 'explicit_condition': mismatch = True
        for name, evidence in record.fields.items():
            if evidence.source_url != document.url or evidence.content_sha256 != document.sha256:
                record.rejection_reasons.append(name + ' provenance differs from retrieved source'); mismatch = True
            if evidence.basis in {'inferred','ai_claim','contradictory'}:
                record.rejection_reasons.append(name + ' is ' + evidence.basis)
                if evidence.basis=='contradictory': mismatch=True
        for name in ('price','currency','price_type','price_basis','published_at'):
            if name not in record.fields or not record.fields[name].substantiated:
                record.rejection_reasons.append(name + ' not independently substantiated')
        def value(name):
            return record.fields[name].value if name in record.fields else None
        try:
            amount = Decimal(str(value('price')))
            if not amount.is_finite() or amount <= 0: raise ValueError('Positive finite price required')
        except (InvalidOperation, ValueError, TypeError):
            record.rejection_reasons.append('Missing or invalid source price'); mismatch=True
        if value('currency') != 'USD':
            record.rejection_reasons.append('Explicit USD reference required; no inferred FX'); mismatch=True
        if value('price_type') != 'published_market_reference':
            record.rejection_reasons.append('Price is not a supported published market benchmark'); mismatch=True
        if value('price_basis') != 'card_only_excluding_shipping_and_tax':
            record.rejection_reasons.append('Card-only price basis not substantiated')
        record.published_at = value('published_at')
        try:
            updated = timestamp(record.published_at)
            if not timedelta(0) <= retrieved - updated <= timedelta(days=self.max_age_days):
                record.rejection_reasons.append('Reference update timestamp is stale or future')
        except (ValueError, TypeError, AttributeError):
            record.rejection_reasons.append('Publisher timestamp unknown; freshness requires review')
        # Reject contradictory AI claims; unknown source information stays unknown.
        for name, claimed in candidate.claims.items():
            if name not in record.fields or claimed is None: continue
            source = record.fields[name]
            if not source.substantiated:
                record.claim_issues.append(name + ' AI claim not source-supported')
            elif not same(name,source.value,claimed):
                record.claim_issues.append(name + ' AI claim contradicts source'); mismatch=True
        missing = ' '.join(str(s) for s in candidate.claims.get('missing_information',[])).casefold()
        summary = str(candidate.claims.get('summary') or '').casefold()
        if candidate.claims.get('condition') is not None and ('condition' in missing or
                re.search(r'condition (?:is )?(?:unknown|not specified)|only raw|only ungraded|beyond ungraded',summary)):
            record.claim_issues.append('Condition claim contradicts AI summary/missing-information')
            mismatch=True
        if mismatch:
            record.rejection_reasons.extend(record.claim_issues)
            record.transition('rejected')
        elif record.rejection_reasons:
            record.transition('context_only')
        else:
            record.eligible_for_condition_valuation = True
            record.transition('verified')
        return record


def write_audit(record, destination):
    """Persist extracted facts only, not source bodies. Never a reusable pricing cache."""
    if record.fields and not record.permission.get('minimal_retention_allowed'):
        raise ValueError('Minimal retention permission required')
    p = Path(destination)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {'record':record.to_dict(), 'record_sha256':record.audit_hash(),
               'retained_content':'Extracted facts and locators only; source body discarded. Hash is not a saved page.'}
    # Do not overwrite an earlier audit decision.
    with p.open('x',encoding='utf-8') as f:
        json.dump(payload,f,indent=2,ensure_ascii=False,allow_nan=False); f.write('\n')
