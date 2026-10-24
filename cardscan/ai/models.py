"""Typed research contracts. Model assertions never confer verification."""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, Field
from ..pricing import Card

VERSION = 'openai_research_v1'


@dataclass(frozen=True)
class ResearchTarget:
    game: str
    name: str
    set_name: str
    number: str
    language: str
    edition: str
    finish: str
    condition: str
    graded: bool = False

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key == 'graded':
                if type(value) is not bool:
                    raise ValueError('graded must be a boolean')
            elif not isinstance(value, str) or not value.strip() or len(value) > 120 or any(ord(c) < 32 for c in value):
                raise ValueError(f'Invalid {key}')
        if self.game.casefold() != 'pokemon':
            raise ValueError('Only Pokemon is supported')
        self.card()

    def card(self):
        return Card(*(getattr(self, key).strip().casefold() for key in
                      ('game', 'set_name', 'number', 'language', 'edition', 'finish')), self.condition.upper())

    def identity(self):
        return {**asdict(self.card()), 'name': self.name.strip().casefold(), 'graded': self.graded}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ObservedIdentity(StrictModel):
    game: str | None
    name: str | None
    set_name: str | None
    number: str | None
    language: str | None
    edition: str | None
    finish: str | None
    condition: str | None
    graded: StrictBool | None


class Candidate(StrictModel):
    kind: Literal['completed_sale', 'market_reference', 'active_listing', 'unknown']
    identity: ObservedIdentity
    source_name: str
    source_record_id: str | None
    url: str
    item_price: str | None
    shipping: str | None
    currency: str | None
    sold_on: str | None
    bundle: StrictBool | None
    quantity: StrictInt | None
    price_is_item_only: StrictBool | None
    access: Literal['full_page', 'snippet', 'unknown']
    evidence_summary: str | None = Field(max_length=600)
    missing_information: list[str]


class ResearchEvidence(StrictModel):
    candidates: list[Candidate] = Field(max_length=20)
    limitations: list[str]


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def claim_id(candidate: Candidate):
    return digest(candidate.model_dump())
