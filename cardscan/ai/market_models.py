"""Experimental estimates, never authenticated completed-sales valuations."""
from typing import Literal
from pydantic import Field, StrictBool
from .models import StrictModel, ObservedIdentity


class MarketSource(StrictModel):
    id: str
    source_name: str
    url: str
    reported_price: str | None
    currency: str | None
    price_type: Literal['completed_sale_report','published_market_reference','active_asking_price','unknown']
    price_meaning: str | None = Field(max_length=300)
    observed_identity: ObservedIdentity
    condition_scope: Literal['explicit_condition','generic_ungraded','mixed','unknown']
    condition_label: str | None
    source_date: str | None
    date_meaning: Literal['sale_date','published_update','listing_observation','unknown']
    price_basis: Literal['item_only','includes_shipping','unknown']
    observation_kind: Literal['search_result','page_content','unknown']
    source_summary: str | None = Field(max_length=400)
    missing_information: list[str]


class MarketEstimate(StrictModel):
    card_identity: ObservedIdentity  # Echo of request; never source-observed identity.
    requested_condition: Literal['NM','LP','MP','HP','DMG']
    estimated_market_value: str | None
    estimated_low: str | None
    estimated_high: str | None
    currency: Literal['USD']
    valuation_type: Literal['condition_specific_market_estimate','provisional_condition_estimate',
                            'generic_ungraded_reference','insufficient_evidence']
    evidence_quality: Literal['limited','mixed','corroborated_reports','insufficient']
    sources: list[MarketSource] = Field(max_length=8)
    supporting_source_ids: list[str]
    reasoning_summary: str = Field(min_length=1,max_length=1200)
    assumptions: list[str]
    limitations: list[str]
    recommendation: Literal['usable_estimate','review_recommended','insufficient_evidence']
    review_recommended: StrictBool
    insufficient_evidence: StrictBool
