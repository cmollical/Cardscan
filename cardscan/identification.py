"""Resolve explicit attributes against a reviewed catalog without fuzzy guessing."""
from typing import Iterable
from .pricing import Card


class IdentificationError(ValueError):
    pass


def identify(attributes: dict, catalog: Iterable[Card]) -> Card:
    """Catalog entries represent allowed printing/condition combinations.

    Canonical keys must already be mapped by a reviewed source adapter. No name
    search, OCR, inferred edition or default language is permitted here.
    """
    candidate = Card(**attributes)
    matches = set(card for card in catalog if card == candidate)
    if len(matches) != 1:
        raise IdentificationError("Exact printing not present in reviewed catalog")
    return matches.pop()
