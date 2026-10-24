"""Evidence retrieval contracts and strict offline manual ingestion; no network I/O."""
from dataclasses import fields
from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Iterable, Mapping, Protocol

from .pricing import Card, Sale


class PricingProvider(Protocol):
    """Implementations return evidence, never a provider's estimate as a sale.

    A future provider must surface retrieval failures; an outage is not an empty
    successful response. License approval and rate limiting belong in the adapter.
    """
    def retrieve(self, target: Card, as_of: date) -> Iterable[Sale]: ...


class IngestionError(ValueError):
    pass


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise IngestionError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(text):
    return json.loads(text, object_pairs_hook=_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(IngestionError(f"Invalid JSON number: {value}")))


def parse_sale(record: dict, permissions: Mapping[str, str]) -> Sale:
    """Fail closed on missing facts; approval references are reviewed externally.

    Money MUST be decimal strings. Required flags have no ingestion defaults.
    A permission reference is an assertion with a reviewable document, not proof
    of legal rights. Empty policy maps intentionally authorize no sources.
    """
    names = {field.name for field in fields(Sale)}
    if not isinstance(record, dict) or set(record) != names:
        raise IngestionError("Sale must contain exactly all documented Sale fields")
    record = dict(record)
    try:
        record["card"] = Card(**record["card"])
        for key in ("sold", "graded", "bundle", "price_confirmed", "condition_confirmed", "refunded"):
            if type(record[key]) is not bool:
                raise IngestionError(f"{key} must be a JSON boolean")
        for key in ("currency", "source", "transaction_id", "url", "verified_by", "verification_notes", "permission_reference", "verification_level"):
            if not isinstance(record[key], str) or not record[key].strip():
                raise IngestionError(f"{key} must be nonempty text")
        reference = permissions.get(record["source"])
        if not isinstance(reference, str) or not reference.strip() or record["permission_reference"] != reference:
            raise IngestionError("Source not approved for collection and commercial reuse")
        for key in ("item_price", "shipping"):
            if record[key] is None and key == "shipping":
                continue  # Shipping is audit context; unknown shipping is allowed.
            if not isinstance(record[key], str):
                raise IngestionError(f"{key} must be a decimal string")
            record[key] = Decimal(record[key])
            if not record[key].is_finite():
                raise IngestionError(f"{key} must be finite")
        for key in ("sold_on", "verified_on"):
            record[key] = date.fromisoformat(record[key])
        return Sale(**record)
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise IngestionError(str(exc)) from exc


class ManualCompsProvider:
    def __init__(self, path: Path, permissions: Mapping[str, str]):
        self.path = Path(path)
        if not isinstance(permissions, Mapping) or any(
                not isinstance(k, str) or not isinstance(v, str) or not k.strip() or not v.strip()
                for k, v in permissions.items()):
            raise IngestionError("Permissions must map source names to reviewed reference strings")
        self.permissions = dict(permissions)

    def retrieve(self, target: Card, as_of: date) -> tuple[Sale, ...]:
        # Preserve mismatches for the evaluator's rejection audit, rather than
        # filtering them invisibly in retrieval. Malformed files fail atomically.
        sales = []
        for line_no, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    sales.append(parse_sale(read_json(line), self.permissions))
                except (ValueError, TypeError) as exc:
                    raise IngestionError(f"{self.path}:{line_no}: {exc}") from exc
        return tuple(sales)
