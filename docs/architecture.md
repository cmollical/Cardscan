# Pricing architecture

The prototype now has two evidence paths, sharing item-price median/outlier
arithmetic. Shipping and tax are excluded from every market-value estimate.

1. `identification.py`: exact lookup in a caller-reviewed catalog; no fuzzy or
   image identification. Canonical game, set, full collector number, language,
   edition, finish and NM/LP/MP/HP/DMG condition remain separate dimensions.
2. `providers.py`: original offline verified-comps import and provider protocol.
   That legacy workflow retains its explicit permission-reference registry.
3. `public_web.py`: personal public-page retrieval, parsing, matching and report
   extraction. No registry or paid API is required for this path. HTTP reads are
   bounded, at most one per second per client, with no challenge retries/bypass.
4. `pricing.py`: comparable qualification and shared `median_and_outliers`
   arithmetic. Default minimum 3, configurable upward; factor-3 extremes trigger
   review and no estimate. Unknown shipping is allowed and not added to prices.
5. `research.py`: reproducible CLI and auditable report orchestration.
6. `validation.py`: independent holdout protocol and metrics, not yet populated
   with a completed real-market benchmark.

## Evidence levels

`reviewed`: manually checked comparable. `seller_reported`: fields extracted
from an individual public eBay sold page; accepted only with explicit research
mode. `secondary_publisher_report`: PriceCharting's public sale rows attributed
to a marketplace. These rows remain separate from direct eBay evidence and from
other marketplace groups; they are not labeled verified original transactions.

Direct eBay matching requires explicit game/set/number/language/finish/condition
attributes. A standard modern edition can be configured only where the reviewed
printing has no edition ambiguity. Never infer unlimited or shadowless from
missing vintage edition data. Missing sale year is not guessed. OutOfStock or an
“N sold” counter does not prove a dated single transaction. Accepted offers are
rejected unless their paid amount can be independently established.

Secondary reports require a reviewed product-page mapping plus explicit card
name, full collector number, condition and language in the row. Current secondary
mapping supports standard English holo printings. Page context supplies set,
edition and finish; publisher mapping mistakes remain possible. Publisher row
IDs and source fragments identify observations, not independently proven original
transaction IDs. Publisher amounts may be currency conversions; retain this
limitation and do not call them confirmed original USD transactions.

## Audit and uncertainty

Each network observation has requested/final URL, actual UTC observation time
and SHA-256 of raw HTML. Cached HTML stays local. Extracted observations retain
source fields, rejection reasons and card-only prices. Result output includes
target, date window, counts, method and evidence level. No confidence scores or
missing prices are invented. Source outages are explicit failures.

Public sold status does not prove payment settlement, authenticity, physical
condition or absence of refunds. Seller declarations and secondary reports
support research estimates, not independently validated valuations. Do not pool
secondary reports with the same directly observed sale or treat correlated
publisher feeds as independent market confirmation.

Deferred: full catalog coverage, reverse/special variant secondary mappings,
trend-aware window selection, calibrated uncertainty, independent 20-card accuracy
validation, scanner and PWA. Personal research access is not a representation
that commercial redistribution rights have been obtained.
