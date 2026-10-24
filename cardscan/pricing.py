"""Deterministic, abstaining valuation of exact, verified sold comparables."""
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from typing import Iterable, Optional
from urllib.parse import urlsplit, urlunsplit

CONDITIONS = frozenset({"NM", "LP", "MP", "HP", "DMG"})
UNKNOWN = frozenset({"", "unknown", "unspecified", "?"})


@dataclass(frozen=True)
class Card:
    game: str
    set_name: str  # Canonical set key; aliases must be resolved before evaluation.
    number: str    # Preserve denominator and subset prefixes.
    language: str
    edition: str   # Include shadowless/stamp distinctions in the canonical key.
    finish: str    # Include special holo/stamp variants; never infer from rarity.
    condition: str

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if not isinstance(value, str) or value.strip().casefold() in UNKNOWN:
                raise ValueError(f"Explicit {field.name} required")
        if self.condition not in CONDITIONS:
            raise ValueError("Condition must be NM, LP, MP, HP or DMG")

    @property
    def printing(self):
        return tuple(getattr(self, f.name) for f in fields(self) if f.name != "condition")


def evidence_url(url: str) -> str:
    """Canonicalize ordinary URL aliases, retaining query parameters for identity."""
    try:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("Evidence must have a public HTTP(S) URL")
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))
    except (TypeError, AttributeError) as exc:
        raise ValueError("Evidence URL must be text") from exc


@dataclass(frozen=True)
class Sale:
    card: Card
    item_price: Decimal
    shipping: Optional[Decimal]  # Audit context only; excluded from market value.
    sold_on: date
    url: str
    sold: bool = True
    graded: bool = False
    bundle: bool = False
    currency: str = "USD"
    source: str = ""
    transaction_id: str = ""  # Stable source ID; deduplicates tracking URL variants.
    verified_by: str = ""
    verified_on: Optional[date] = None
    verification_notes: str = ""  # Actual paid price, condition and printing evidence.
    permission_reference: str = ""  # Personal research asserts no commercial license.
    price_confirmed: bool = False  # False for hidden best offers and asking prices.
    condition_confirmed: bool = False
    refunded: bool = False
    verification_level: str = "reviewed"  # Or seller_reported from public listing extraction.

    @property
    def key(self):
        return (self.source, self.transaction_id)


@dataclass(frozen=True)
class Result:
    value: Optional[Decimal]
    accepted: tuple
    rejected: tuple
    reason: str
    as_of: date
    currency: str
    minimum_sales: int
    max_age_days: int
    status: str
    target: Card
    outlier_factor: Decimal
    allow_seller_reported: bool = False
    verification_as_of: Optional[date] = None
    method: str = "median_item_price_v3"

    def to_dict(self):
        def encode(value):
            if isinstance(value, (date, datetime)):
                return value.isoformat()
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, dict):
                return {k: encode(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [encode(v) for v in value]
            return value
        return encode(asdict(self))


def match_reasons(target: Card, candidate: Card) -> list[str]:
    return [f"{field.name} mismatch" for field in fields(Card)
            if getattr(target, field.name) != getattr(candidate, field.name)]


def _valid_money(value, positive=False):
    return (isinstance(value, Decimal) and value.is_finite()
            and (value > 0 if positive else value >= 0))


def median_and_outliers(amounts: list[Decimal], factor: Decimal):
    """Shared arithmetic for reviewed evidence and clearly labeled research data."""
    center = median(amounts)
    flagged = tuple(i for i, amount in enumerate(amounts)
                    if amount < center / factor or amount > center * factor)
    return center.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), flagged


def evaluate(target: Card, sales: Iterable[Sale], as_of: Optional[date] = None,
             max_age_days: int = 90, minimum_sales: int = 3,
             currency: str = "USD", outlier_factor: Decimal = Decimal("3"),
             allow_seller_reported: bool = False,
             verification_as_of: Optional[date] = None) -> Result:
    """No FX/condition multipliers. Extreme dispersion triggers review, not a price.

    The factor guard is a conservative heuristic, not a calibrated confidence score.
    Medians resist isolated outliers; flagged records remain in the audit trail.
    """
    if type(minimum_sales) is not int or minimum_sales < 3:
        raise ValueError("minimum_sales must be an integer >= 3")
    if type(max_age_days) is not int or max_age_days < 0:
        raise ValueError("max_age_days must be a nonnegative integer")
    if currency != "USD":
        raise ValueError("Only USD normalization is currently implemented")
    if not _valid_money(outlier_factor, positive=True) or outlier_factor <= 1:
        raise ValueError("outlier_factor must be a finite Decimal > 1")
    today = as_of or date.today()
    if type(today) is not date:
        raise ValueError("as_of must be a date")
    verification_day = verification_as_of or today
    if type(verification_day) is not date:
        raise ValueError("verification_as_of must be a date")
    accepted, rejected = [], []
    seen_ids, seen_urls = set(), set()
    for sale in sales:
        reasons = match_reasons(target, sale.card)
        if target.game != "pokemon":
            reasons.append("unsupported game")
        if sale.sold is not True:
            reasons.append("not a completed sale")
        if sale.graded is not False:
            reasons.append("graded or unknown grading status")
        if sale.bundle is not False:
            reasons.append("bundle or unknown lot status")
        if sale.refunded is not False:
            reasons.append("refunded or unknown refund status")
        if sale.currency != currency:
            reasons.append("currency mismatch; FX unavailable")
        if not _valid_money(sale.item_price, positive=True):
            reasons.append("invalid item price")
        if sale.shipping is not None and not _valid_money(sale.shipping):
            reasons.append("invalid shipping context")
        if sale.verification_level not in {"reviewed", "seller_reported"}:
            reasons.append("unknown verification level")
        if sale.verification_level == "seller_reported" and not allow_seller_reported:
            reasons.append("seller-reported evidence requires research mode")
        try:
            url = evidence_url(sale.url)
        except ValueError:
            url = None
            reasons.append("missing evidence URL")
        if not all(isinstance(v, str) and v.strip() for v in (
                sale.source, sale.transaction_id, sale.verified_by,
                sale.verification_notes)):
            reasons.append("missing verification provenance")
        if sale.price_confirmed is not True:
            reasons.append("actual paid price unconfirmed")
        if sale.condition_confirmed is not True:
            reasons.append("condition unconfirmed")
        if type(sale.sold_on) is not date or not 0 <= (today - sale.sold_on).days <= max_age_days:
            reasons.append("outside sale window")
        if (type(sale.verified_on) is not date or sale.verified_on > verification_day
                or (type(sale.sold_on) is date and sale.verified_on < sale.sold_on)):
            reasons.append("invalid verification date")
        if sale.key in seen_ids or (url is not None and url in seen_urls):
            reasons.append("duplicate transaction or URL")
        if reasons:
            rejected.append((sale, tuple(reasons)))
        else:
            accepted.append(sale)
            seen_ids.add(sale.key)
            seen_urls.add(url)
    status = "insufficient_evidence"
    value = None
    reason = f"Insufficient evidence: {len(accepted)}/{minimum_sales} qualified sales"
    if len(accepted) >= minimum_sales:
        amounts = [s.item_price for s in accepted]
        center, outlier_indices = median_and_outliers(amounts, outlier_factor)
        # Do not silently trim real sales or convert a thin market into false certainty.
        flagged = [accepted[i] for i in outlier_indices]
        if flagged:
            status = "review_required"
            reason = "Extreme price dispersion; inspect outliers before valuation"
            for sale in flagged:
                rejected.append((sale, ("price outlier; manual review required",)))
            accepted = [s for s in accepted if s not in flagged]
        else:
            value = center.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            status = "valued"
            reason = "Median card sale price; excludes shipping and tax"
    if value is not None and any(s.verification_level == "seller_reported" for s in accepted):
        status = "research_estimate"
        reason += "; public seller-reported sales, condition not physically verified"
    return Result(value, tuple(accepted), tuple(rejected), reason, today, currency,
                  minimum_sales, max_age_days, status, target, outlier_factor, allow_seller_reported, verification_as_of)
