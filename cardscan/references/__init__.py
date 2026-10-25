"""Independent source-reference verification. No valuation, cache or paid API calls."""
from .models import FieldEvidence, ReferenceCandidate, SourcePermission, VerificationRecord
from .service import ReferenceVerifier

__all__ = ['FieldEvidence', 'ReferenceCandidate', 'SourcePermission', 'VerificationRecord', 'ReferenceVerifier']
