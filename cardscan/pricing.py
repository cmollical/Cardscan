"""Deterministic evaluation of independently verified sold comparables."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from statistics import median
from typing import Optional


@dataclass(frozen=True)
class Card:
    game: str
    set_name: str
    number: str
    language: str
    edition: str
    finish: str
    condition: str


@dataclass(frozen=True)
class Sale:
    card: Card
    item_price: Decimal
    shipping: Decimal
    sold_on: date
    url: str
    sold: bool = True
    graded: bool = False
    bundle: bool = False


@dataclass(frozen=True)
class Result:
    value: Optional[Decimal]
    accepted: tuple
    rejected: tuple
    reason: str


def evaluate(target: Card, sales: list[Sale], as_of: Optional[date] = None,
             max_age_days: int = 90, minimum_sales: int = 3) -> Result:
    """Return a median only when enough exact, recent, verified sales exist."""
    today = as_of or date.today()
    accepted, rejected = [], []
    seen_urls = set()
    for sale in sales:
        reasons = []
        if sale.card != target:
            reasons.append("card attributes mismatch")
        if not sale.sold:
            reasons.append("not a completed sale")
        if sale.graded:
            reasons.append("graded")
        if sale.bundle:
            reasons.append("bundle")
        if not sale.url.startswith(("https://", "http://")):
            reasons.append("missing evidence URL")
        if sale.url in seen_urls:
            reasons.append("duplicate URL")
        age = (today - sale.sold_on).days
        if age < 0 or age > max_age_days:
            reasons.append("outside sale window")
        if sale.item_price <= 0 or sale.shipping < 0:
            reasons.append("invalid price")
        if reasons:
            rejected.append((sale, tuple(reasons)))
        else:
            accepted.append(sale)
            seen_urls.add(sale.url)
    if len(accepted) < minimum_sales:
        return Result(None, tuple(accepted), tuple(rejected),
                      f"Insufficient evidence: {len(accepted)}/{minimum_sales} qualified sales")
    amounts = [s.item_price + s.shipping for s in accepted]
    value = Decimal(str(median(amounts))).quantize(Decimal("0.01"))
    return Result(value, tuple(accepted), tuple(rejected), "Median of qualified sales")
