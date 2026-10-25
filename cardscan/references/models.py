"""Field-level source evidence, distinct from requested identity and model claims."""
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any, Literal


@dataclass(frozen=True)
class ReferenceCandidate:
    source: str
    url: str
    variant: str
    claims: dict = field(default_factory=dict)

    @classmethod
    def from_ai(cls, candidate, *, source=None, variant):
        """AI fields remain claims; never used as observed source fields."""
        c = candidate.model_dump() if hasattr(candidate, 'model_dump') else candidate
        return cls(source or c['source_name'], c['url'], variant,
                   {**c.get('identity', {}), 'price':c.get('item_price'),
                    'currency':c.get('currency'), 'summary':c.get('evidence_summary'),
                    'missing_information':c.get('missing_information', [])})


@dataclass(frozen=True)
class FieldEvidence:
    value: Any
    basis: Literal['direct_content', 'structured_metadata', 'inferred', 'ai_claim', 'missing', 'contradictory']
    locator: str
    method: str
    source_url: str
    content_sha256: str

    @property
    def substantiated(self):
        return (self.value is not None and self.basis in {'direct_content', 'structured_metadata'}
                and bool(self.locator) and len(self.content_sha256) == 64)


@dataclass(frozen=True)
class SourcePermission:
    source: str
    retrieval_allowed: bool
    minimal_retention_allowed: bool
    commercial_allowed: bool
    references: tuple[str, ...]
    reviewed_on: str
    scope: str


@dataclass
class VerificationRecord:
    source: str
    canonical_url: str
    requested_identity: dict
    status: str = 'discovered'
    fields: dict[str, FieldEvidence] = field(default_factory=dict)
    ai_claims: dict = field(default_factory=dict)
    claim_issues: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    transitions: list[str] = field(default_factory=lambda:['discovered'])
    retrieved_at: str | None = None
    published_at: str | None = None
    condition_scope: str = 'unknown'
    content_sha256: str | None = None
    extraction_method: str | None = None
    permission: dict = field(default_factory=dict)
    purpose: str = 'research'
    reference_key: str | None = None
    eligible_for_condition_valuation: bool = False

    def transition(self, status):
        self.status = status
        self.transitions.append(status)

    def to_dict(self):
        return asdict(self)

    def audit_hash(self):
        return sha256(json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False,
                                 separators=(',', ':'), allow_nan=False).encode()).hexdigest()
