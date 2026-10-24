"""Independent substantiation boundary. Citation presence alone is not verification."""
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Protocol
from urllib.parse import urlsplit

from .models import Candidate, ResearchTarget, claim_id
from .provider import canonical_url
from ..public_web import parse_ebay, qualify, normalized


@dataclass(frozen=True)
class Verification:
    verified: bool
    reviewer: str = ''
    reviewed_on: str = ''
    artifact_sha256: str = ''
    reason: str = 'No independent verification supplied'


class EvidenceVerifier(Protocol):
    def verify(self, target: ResearchTarget, candidate: Candidate, as_of: date) -> Verification: ...


class Unverified:
    def verify(self, target, candidate, as_of):
        return Verification(False)


class ReviewedEvidence:
    """Local human attestations bound to the entire extracted claim, not just URL.

    Required format: {claim_id: {reviewer, reviewed_on, artifact_sha256,
    substantiates: true}}. Reviewer must check price, sold status, date, currency,
    all identity dimensions, raw/single-card status and condition. This is an
    attestation, not software authentication of the reviewer or the artifact.
    """
    def __init__(self, reviews):
        self.reviews = reviews

    def verify(self, target, candidate, as_of):
        import re
        review = self.reviews.get(claim_id(candidate), {})
        try:
            reviewed = date.fromisoformat(review.get('reviewed_on', ''))
            valid = (review.get('substantiates') is True and isinstance(review.get('reviewer'), str)
                     and review['reviewer'].strip() and not review['reviewer'].lower().startswith(('openai', 'model'))
                     and re.fullmatch(r'[a-f0-9]{64}', review.get('artifact_sha256', '')) is not None
                     and date.fromisoformat(candidate.sold_on) <= reviewed <= datetime.now(timezone.utc).date())
        except (ValueError, TypeError):
            valid = False
        if not valid:
            return Verification(False, reason='Missing, negative or invalid independent review')
        return Verification(True, review['reviewer'], str(reviewed), review['artifact_sha256'],
                            'Independent reviewer substantiates this exact claim')


class EbaySourceVerifier:
    """Optional ordinary public fetch; no model-generated facts are trusted.

    Uses the existing parser and exact matching. It checks source support, not
    authenticity, payment settlement or physical condition. No other hosts fetched.
    """
    def __init__(self, public_client, *, standard_edition_is_reviewed=False):
        self.client = public_client
        self.standard_edition_is_reviewed = standard_edition_is_reviewed

    def verify(self, target, candidate, as_of):
        if urlsplit(candidate.url).hostname != 'www.ebay.com':
            return Verification(False, reason='No deterministic verifier for this source; independent review needed')
        try:
            snapshot = self.client.get(candidate.url)
            listing = parse_ebay(snapshot)
            sale, reasons = qualify(target.card(), listing, standard_edition=self.standard_edition_is_reviewed)
            if not sale:
                return Verification(False, reason='Source rejected: ' + '; '.join(reasons))
            specifics = {normalized(k):v for k,v in listing.specifics.items()}
            if normalized(specifics.get('card name', '')) != normalized(target.name):
                return Verification(False, reason='Card name not corroborated on source')
            if (sale.item_price != Decimal(candidate.item_price) or str(sale.sold_on) != candidate.sold_on
                    or sale.currency != candidate.currency or sale.transaction_id != candidate.source_record_id
                    or canonical_url(sale.url) != canonical_url(candidate.url)):
                return Verification(False, reason='Source price/date/currency/record ID differs from model claim')
            return Verification(True, 'source_adapter:ebay_public_v1', snapshot.observed_at[:10],
                                snapshot.sha256, 'Public sold page corroborates matched seller-declared attributes and item price')
        except (ValueError, TypeError, OSError) as exc:
            return Verification(False, reason=f'Source verification failed: {type(exc).__name__}')
