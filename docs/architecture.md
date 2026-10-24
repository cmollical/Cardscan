# Pricing research architecture

## Boundaries

1. **Identification** (`cardscan.identification`): explicit canonical attributes
   resolve against a reviewed catalog. No fuzzy search or scanner yet. Zero exact
   catalog matches abstains. Catalog coverage and authenticity are not inferred
   from an arbitrary input string.
2. **Evidence retrieval** (`PricingProvider` in `cardscan.providers`): adapters
   return `Sale` records, not estimates. `ManualCompsProvider` reads authorized,
   verified JSONL. It preserves mismatches so rejection reasons remain visible.
   Malformed input fails the whole file; missing files and provider failures must
   not masquerade as a successful empty retrieval.
3. **Comparable matching** (`match_reasons`): compare each printing attribute and
   condition separately; surface which dimension differs. Set names are canonical
   keys, not fuzzy names; collector numbers retain denominator/subset prefixes.
4. **Valuation** (`evaluate`): reject unverified, stale, future, duplicate, graded,
   bundled, refunded, unsupported-currency and unknown-shipping records. Use the
   median of item price plus shipping. Default minimum 3, configurable upward.
   No condition multipliers, invented FX or confidence scores.
5. **Evaluation** (`cardscan.validation`): separate held-out sales, independent
   reviewer labels, reproducible cutoff date and auditable per-card output.

A future catalog adapter may use TCGdex metadata under the database's MIT terms,
with attribution retained. A provider card ID is not sufficient for edition,
shadowless, promo-stamp or holo-pattern identity. Human-reviewed mappings must
resolve these distinctions before records enter the engine. Unknown attributes
are rejected; a missing finish is never treated as ordinary holo. Current lookup
requires a caller-supplied reviewed catalog; a complete catalog is not shipped.
The manual CLI accepts reviewer-supplied explicit target attributes; it does not
claim to authenticate a physical card or validate every printing's existence.

## Provider admission

Before enabling network retrieval, record the public access method, explicit
commercial reuse rights, permitted retention/redistribution, exact evidence type,
rate limits, currency semantics, and source's transaction identity. Cache with
observed retrieval time, source payload hash and adapter version when a real
adapter is implemented. Respect 429/Retry-After, timeouts and revocation. No
fallback to HTML scraping or a secondhand copy lacking upstream permission.

The existing manual implementation uses a local source-to-permission-document
registry. A reference is a reviewable assertion, not automated proof of rights.
A human must review grants; the software cannot establish legal permission,
truthfulness, physical condition or a completed payment from a boolean flag.
No source is enabled by default. Permission documents should cover public
collection **and** commercial use, including combinations with other sources.

## Normalization and statistical policy

Only USD is implemented. Explicit zero shipping is supported; null shipping is
unknown and rejected. Values include shipping and exclude tax/fees; compare
against references with the same basis. Shipping must concern the single card
and intended domestic market, not a bundled order allocation or unknown service.
No overseas/currency pooling; finer region restrictions need a future model.

A median limits isolated outlier influence. A total outside one-third to three
times the median (configurable `outlier_factor`) causes `review_required` and no
price. Flagged records remain in rejected evidence with a reason. No re-estimate
is issued after silent trimming. This conservative heuristic is uncalibrated;
it can reject legitimate volatile sales and cannot detect coordinated or tightly
clustered bad prices. Three consistent comps are a policy minimum, not evidence
of ±10% accuracy, liquidity or statistical confidence.

`Result.to_dict()` records target, cutoff, currency, policy settings, method
version, all accepted/rejected records and explanations. Decimals are strings;
no floating-point arithmetic is used for prices. Keep output alongside input
files and permission/verification artifacts. This is an auditable research
snapshot, not an immutable ledger or a calibrated prediction interval.

## Deferred

Live pricing, complete catalog ingestion, cross-provider syndicated-sale identity,
regional shipping models, permission revocation automation, trend detection,
probabilistic intervals, scanner, inventory UI and PWA. Accuracy validation gates
all product-interface work.
