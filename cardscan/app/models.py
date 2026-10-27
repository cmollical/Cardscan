from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator

Condition = Literal["NM", "LP", "MP", "HP", "DMG"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CardFields(Strict):
    game: Literal["pokemon"] = "pokemon"
    product_id: int | None = Field(None, gt=0)
    name: str = Field("", max_length=200)
    set_name: str = Field("", max_length=200)
    number: str = Field("", max_length=40)
    language: str = Field("", max_length=50)
    edition: Literal["standard", "unlimited", "first edition", "shadowless"] | None = (
        None
    )
    finish: Literal["holo", "non-holo", "reverse holo"] | None = None
    rarity: str | None = Field(None, max_length=100)
    condition: Condition | None = None
    graded: Literal[False] = False
    notes: str = Field("", max_length=3000)


class IntakeWrite(Strict):
    session_id: UUID
    expected_revision: int = Field(0, ge=0)
    fields: CardFields
    front_id: UUID | None = None
    back_id: UUID | None = None


class SessionWrite(Strict):
    id: UUID
    name: str = Field("Card intake", min_length=1, max_length=100)


class ListingWrite(Strict):
    intake_id: UUID
    intake_revision: int = Field(ge=1)
    expected_revision: int | None = Field(None, ge=1)
    item_name: str = Field("", max_length=250)
    description: str = Field("", max_length=5000)
    listing_price: str
    quantity: int = Field(1, ge=0, le=100000)
    notes: str = Field("", max_length=3000)
    approved: Literal[True]

    @field_validator("listing_price")
    @classmethod
    def money(cls, v):
        import re

        if not re.fullmatch(r"\d{1,8}(?:\.\d{1,2})?", v):
            raise ValueError("Enter a USD amount with at most two decimal places")
        amount = Decimal(v)
        if not amount.is_finite() or amount < 0:
            raise ValueError("Invalid price")
        return format(amount.quantize(Decimal(".01")), "f")


class JobWrite(Strict):
    kind: Literal["identify", "condition"]
    authorize_paid: Literal[True]
    expected_revision: int = Field(ge=1)


class VisibleIdentityReading(Strict):
    name: str | None
    collector_number: str | None
    set_code: str | None
    language: str | None
    edition: str | None
    finish: str | None
    rarity: str | None


class Identification(Strict):
    readings: list[VisibleIdentityReading] = Field(max_length=5)
    observations: list[str] = Field(max_length=12)
    limitations: list[str] = Field(max_length=12)
    recommended_condition: Condition | None
    condition_observations: list[str] = Field(max_length=15)
    condition_limitations: list[str] = Field(max_length=12)
    additional_photos_helpful: bool


class SetCodeResolution(Strict):
    reading_index: int = Field(ge=0, le=4)
    selected_set_code: str | None
    observation: str


class CatalogGuidedIdentification(Strict):
    resolutions: list[SetCodeResolution] = Field(max_length=5)
    limitations: list[str] = Field(max_length=5)


class Assessment(Strict):
    recommended_condition: Condition | None
    observations: list[str] = Field(max_length=15)
    limitations: list[str] = Field(max_length=12)
    additional_photos_helpful: bool
