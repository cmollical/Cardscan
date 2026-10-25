# Pilot forensics and proposed reference-first methodology

Analysis date: 2026-10-24. Scope: documentation and offline test specifications.
No paid API requests, production pricing changes, or provider replacement were made.

## Finding and recommended next step

The strongest confirmed cause is **weak evidence acquisition and representation**,
combined with a transaction-only valuation architecture. Insufficient accessible
condition-specific data remains plausible but unproved: we never retained source
documents with which to distinguish absent data from poor extraction. Strict sold
verification prevented unsupported prices and should remain intact.

The single most valuable engineering step is a **source verification boundary that
captures field-level provenance for published benchmarks**, initially tested against
the two exact English NM targets. A benchmark must retain its price label, condition
scope, product/variant selection and source snapshot before a reference evaluator can
use it. First establish whether one permitted source exposes those facts. This step
is proposed, not installed in the production provider by this assignment.

Reference-first has **no demonstrated coverage gain in this pilot**. All prices are
unverified model claims about sales or asks, not independently substantiated market
benchmarks. Generic ungraded guides cannot price a requested condition by assumption.

## Artifact, reproducibility and evidence boundary

- [Original run, attempt 2](https://github.com/cmollical/Cardscan/actions/runs/40114686775/attempts/2)
- [Original artifact](https://github.com/cmollical/Cardscan/actions/runs/40114686775/artifacts/12568485590)
- Pilot code: `bac237d9912f270af78c590d300e907816ef781b`.
- ZIP SHA-256: `91c674bd4c3a2885453511cddc974096484d1692660e8ac342dd7fe49b3c725a`.
- Inspected all seven ZIP entries: six result/summary JSON files and
  `ai-research.sqlite`. SQLite has cache and request-ledger records; each request's
  audit preserves full API output, including text discarded by provider validation.
- No marketplace HTML, independent review, source snapshot, or original snippet text
  appears in those entries. API source URL lists establish discovery, not the price
  or identity fields visible at the URL. `access=full_page` is itself a model assertion.
- No marketplace pages were fetched for this historical audit. A new page could
  inform future verification, but cannot prove what was visible during the pilot.
- [Machine-readable extraction](../research/results/pilot-forensics-2026-10-24/evidence-analysis.json)
  preserves all 20 claims, claim hashes, request/response IDs, raw pointers, source
  URL lists, action statuses, actual rejection reasons, and separately labeled replay.
- [Candidate table](../research/results/pilot-forensics-2026-10-24/candidates.md)
  assesses every retained and recoverable candidate individually.

The original artifact has seven-day GitHub retention. A local copy was inspected;
the committed extraction preserves the relevant claims and accounting without
republishing opaque reasoning payloads, credentials, or full source documents.

## Confirmed findings

| Classification | Retained candidates | Additional discarded candidates | Total |
| --- | ---: | ---: | ---: |
| Verified completed sales | 0 | 0 | 0 |
| Verified published market references | 0 | 0 | 0 |
| Unverified potentially useful discovery leads | 13 | 4 | 17 |
| Active asks, model-classified and unverified | 0 | 2 | 2 |
| Independently established wrong printing | 0 | 0 | 0 |
| Unusable redundant duplicate claim | 0 | 1 | 1 |

There are 18 purported sales and two purported asks. V4 repeats V1's source URL,
date and amount. This is a redundant claim, not a second sale. No confirmed wrong
printing does not mean the printings were verified. The unverified-lead bucket is
not permission to label a purported sale as a Tier 2 benchmark.

All thirteen retained sale claims lacked marketplace record IDs. Charmander's four
PriceCharting rows also lacked explicit bundle status. The six modern Charizard
rows lacked quantity/bundle and paid-price semantics. Five of those six claimed NM
while admitting unknown precise condition. Gengar's three rows lacked card-only
price confirmation; two also lacked currency and one sale date. No retained
candidate passed preliminary gates, so none reached the configured eBay verifier.

Discarded Base Set Charizard text adds four sale claims with dollar-symbol strings,
missing IDs, admitted language/edition uncertainty and one uncertain sold status.
Discarded Japanese Charizard text adds one direct eBay sale lead and two eBay asks.
The sale lead has a record ID, but source condition is `Near mint or better`, not the
canonical `NM`; its supporting page was not retained. This deserves source review,
not an automatic alias or acceptance. All seven claims are in the candidate table.

No reported amount can be independently substantiated **from this artifact**.
Whether those amounts are actually correct is unknown. The artifact does not prove
that TCGplayer or any other source lacks suitable data. Prompts explicitly favored
completed sales; their failure to extract benchmarks is not a benchmark-availability
test. The provider presently routes references to context and never values them.

## Validation assessment

| Requirement | Individual completed sale | Published reference | Finding on current implementation |
| --- | --- | --- | --- |
| Source ID | Stable transaction/listing ID plus corroboration | Stable product/variant/benchmark key, not a transaction ID | Keep sold gate; add separate reference contract |
| Date | Actual sale date within configured window | Publisher effective date when available; retrieval time always | Retrieval time must not masquerade as publisher freshness |
| Condition | Explicit source label with reviewed mapping | Explicit condition scope of this exact benchmark | Neither generic raw nor ungraded establishes NM |
| Shipping | Known card-only paid amount; shipping may be null | Known benchmark inclusion/exclusion semantics | Existing code allows unknown shipping; earlier shorthand blaming missing shipping was imprecise |
| Currency | Explicit; current evaluator supports USD only | Explicit; retain original currency, abstain without approved FX | Foreign-language card need not imply foreign currency |
| Single card | Explicit single-card transaction, no lots | Per-card benchmark definition; bundle/quantity transaction fields not applicable | Do not invent quantity=1 for a benchmark |
| Printing | Name, set, collector number, language, edition, finish, raw status | Same dimensions; reviewed canonical product mapping | Exact matching is necessary, but copied target fields are not source proof |
| URL | Primary record with stable provenance and source support | Source product/condition/variant URL and captured selection state | Consulted URL is necessary in current adapter, insufficient as verification |
| Independent verification | Full claim corroborated by adapter or review | Benchmark value AND meaning corroborated | Current automatic adapter only supports eBay |
| Minimum evidence | Existing configurable minimum of three distinct qualified sales | Policy may accept one transparent, fresh, condition-specific benchmark, labeled single-source | Three transactions are not required to quote one verified benchmark |

Strict sale validation is not shown to be overly restrictive. A verified alternative
transaction identity scheme could eventually replace marketplace IDs for a specific
source, but none exists in this pilot. Keep the present sold gates unchanged.
Literal aliases (e.g. reviewed source condition labels) may cause false negatives;
map only documented source semantics, preserving the original label and mapping
version. Never map by deleting qualifiers or matching an arbitrary substring.

The architecture is restrictive for references: `Candidate` has sale-shaped fields
but lacks benchmark definition, condition scope, publisher timestamp and field-level
support. Merely disabling its ID/date/bundle gates would introduce errors rather
than implement reference pricing. Duplicate-by-page-URL is reasonable for the
current direct sale path; an aggregator page with multiple rows needs independently
identified row/transaction provenance, not guessed distinct sales.

## Proposed three-tier contract (not a production implementation)

Use a discriminated union, with evidence *kind* separate from verification *state*.
An unverified extraction may claim a kind but belongs to no verified valuation tier.
Unknown and contradicted evidence remains quarantined context.

```text
EvidenceEnvelope:
  evidence_id, schema_version, claimed_kind, verification_state
  source: publisher, role(primary_marketplace|aggregator|retailer), original_url,
          canonical_url, source_product_key, permission_reference
  provenance: retrieved_at_utc, source_effective_at_utc?, artifact_sha256,
              artifact_location, adapter_version, reviewer?, reviewed_at_utc?
  observed_identity: canonical_printing_key?, source_labels, raw_or_graded
  field_support: map(field -> {observed_value, source_locator, source_text,
                               support_kind, mapping_version?, verified})
  price: decimal_amount, currency, basis(card_only|includes_shipping|unknown),
         includes_tax(true|false|unknown), unit(per_card|per_lot|unknown)
  uncertainties[], contradictions[], source_dependencies[]

CompletedSale extends EvidenceEnvelope:
  kind=completed_sale; transaction_id; sold_at; sold_status; quantity; bundle;
  condition_source_label; condition_canonical?; shipping?; offer_price_confirmed

PublishedReference extends EvidenceEnvelope:
  kind=published_reference; benchmark_name; benchmark_definition;
  benchmark_type(sold_derived_market_estimate|asking_statistic|guide|unknown);
  condition_scope(explicit_condition|ungraded_generic|mixed|unknown);
  condition_source_label?; condition_canonical?; sample_window?; sample_count?;
  publisher_updated_at?; currency_region; underlying_marketplaces[]

ActiveAsk extends EvidenceEnvelope:
  kind=active_ask; listing_id; observed_active_at; seller?; quantity?; bundle?;
  condition_source_label?; condition_canonical?; shipping?; offers_allowed?
```

For any **verified** object, every material price/identity/status/condition claim
requires a matching support locator in a retained source artifact, or an independent
attestation bound to the whole claim. A hash identifies an artifact; it does not
prove its contents. Verification is by trusted adapter/reviewer, never by the model.
Source permission status remains explicit; public visibility grants no automatic
commercial redistribution rights. Store only permitted minimal supporting material.

Tier 1: only verified CompletedSale objects satisfying existing sold policy feed
`completed_sales_value` (robust median, minimum count, outlier review unchanged).
Tier 2: only verified PublishedReference objects with known benchmark meaning,
exact printing and explicit requested condition can support `reference_value`.
Asking-statistic references remain asking context; unknown/opaque definitions need
review and cannot be called sold-derived prices. Generic ungraded references may
be displayed as ungraded context, never as a condition-specific valuation.
Tier 3: ActiveAsk objects provide labeled context; even verified asks never feed
either market-clearing sold medians or automatic reference valuations.

Return separate slots: `completed_sales_value`, `reference_value`, `asking_context`,
`selected_method`, `selection_reason`, `limitations`, `evidence_ids` and objective
quality indicators. Unsupported slots are null. Never average across tiers or
describe a source benchmark as CardScan's observed transaction median.

## Reference-first architecture and decision policy

1. Resolve exact printing with a reviewed product mapping, independent of pricing.
   Preserve raw collector labels, accents, language, edition and finish. PriceCard
   product metadata is not evidence of an individual seller's condition.
2. Discover published references for that printing and requested condition. Model
   outputs are candidate locations/claims only; unknown fields stay null.
3. A source-specific read-only adapter or independent reviewer captures the actual
   price label, selection state, currency, condition scope, meaning and provenance.
   Stop on access restrictions; no hidden endpoints or challenge bypass.
4. Apply deterministic support and contradiction gates. Cache verified extraction
   separately from discovery, keyed by all identity dimensions, condition, source,
   mapping version and retrieval policy. A cached URL alone is not a cached price.
5. Discover and verify recent completed sales as corroboration, separately.
6. Evaluate each tier separately. Prefer sufficient, recent, consistent verified
   sales; otherwise allow a verified explicit-condition reference with a clear
   `published_reference` label and single-source limitation when applicable.
7. If material conflict exists, return both with `manual_review_required` and no
   selected scalar. Suggested preregistered pilot conflict threshold: more than
   15% difference using the lower value as denominator. This is a review trigger,
   not a calibrated accuracy boundary and not permission to discard expensive sales.

Do not count aggregators redisplaying TCGplayer/eBay as independent markets. For
conflicting benchmarks, compare definitions, time windows, currencies and conditions
before selecting; never use a blind median. A transparent source-specific selection
policy must be frozen before evaluation. An asking median cannot corroborate a
transaction median as if it were another transaction source.

Suggested experimental freshness policy: retrieve within 24 hours; if the publisher
gives an effective timestamp, require it within seven days. A recent retrieval with
no publisher date may be a current-page reference only when the source explicitly
defines it as current; flag freshness unknown, and exclude it from independent
accuracy success until reviewed. Retrieval does not reset a known stale price.
Low liquidity, missing sample size, unknown methodology or unusually wide dispersion
are disclosed limitations; stale/ambiguous references or material conflict abstain.
No formulaic condition discounts or language conversions.

## Deterministic condition integrity

- Require observed condition support tied to this particular row/benchmark, not
  merely the page title, URL query, requested target or another row.
- Unknown is null; generic ungraded/raw is a grading state, not NM. “Great
  condition,” pack-fresh claims and condition ranges do not establish a canonical
  condition without a reviewed mapping and explicit support.
- Separate `source_condition_label`, `canonical_condition`, `condition_scope` and
  mapping version. Preserve `Near mint or better` as a range until its platform
  semantics are reviewed; do not silently turn it into NM.
- If missing-information includes raw/precise condition while structured condition
  is populated, reject or quarantine. Do the same for “condition unknown,” “not
  specified” and “only raw/ungraded” summaries. Negations and mixed-row wording need
  review rather than optimistic keyword matching.
- Prefer explicit structured support states (`explicit`, `unknown`, `inferred`,
  `contradictory`) over trying to prove truth with regular expressions. Text rules
  are fail-closed alarms, not evidence verification. A consistent fabricated claim
  still needs independent source verification.
- Apply parallel checks to language (English page does not imply English card),
  edition (no “1st Edition” in title does not establish Unlimited or exclude
  Shadowless), finish (rarity/holo artwork does not prove reverse/non-holo variant),
  grading (no slab mentioned does not prove raw), and identity (same name/number
  without denominator/set does not establish the printing). Distinguish stamps,
  promos, reprints, Japanese versus English numbers and graded “9” from NM.
- Unknown sold status cannot coexist with an accepted completed-sale claim. A
  bundle-confirmation gap cannot coexist with verified single-card status.

The test-only executable specification is in `tests/methodology_contract.py`.
It is deliberately not imported by the production provider. Offline tests both
illustrate these proposed gates and characterize the current production gaps.

## Search accounting: correction to the initial pilot interpretation

Official documentation checked on 2026-10-24:

- [Responses create](https://developers.openai.com/api/reference/resources/responses/methods/create):
  `max_tool_calls` limits processed built-in tool calls across tools; extra model
  attempts are ignored. It is not a reasoning-step or query-string count.
- [Web-search guide](https://developers.openai.com/api/docs/guides/tools-web-search):
  output actions distinguish search, open-page and find-in-page. Search actions
  incur tool fees. Source lists are not full source bodies. `return_token_budget`
  exposes default/unlimited, not a dollar or arbitrary numeric token cap.
- [Pricing](https://developers.openai.com/api/docs/pricing) and
  [model rates](https://developers.openai.com/api/docs/models/gpt-5.4-mini):
  web search $10/1,000 calls, plus search-content tokens at model rates; mini rates
  remain $0.75/M input, $0.075/M cached input, $4.50/M output.
- [Project spending controls](https://help.openai.com/en/articles/9186755-managing-projects-in-the-api-platform):
  current guidance provides optional hard-limit enforcement, but notes enforcement
  delay. Alerts alone do not stop requests. Neither setting guarantees an exact
  $0.15 request-level cap. This differs from older soft-budget-only guidance.

| Case | All web output items | Completed actions | Completed searches | Unfinished actions | Raw tool_usage.web_search.num_requests |
| --- | ---: | ---: | ---: | --- | ---: |
| Charmander | 2 | 2 | 1 | none | 1 |
| Modern Charizard | 2 | 2 | 1 | none | 1 |
| Base Set Charizard | 3 | 2 | 1 | open_page, searching, URL null | 1 |
| Gengar | 2 | 2 | 2 | none | 2 |
| Japanese Charizard | 3 | 2 | 2 | open_page, searching, URL null | 2 |

All responses echo max_tool_calls=2. Each rejected response has two completed
actions plus an unfinished attempted page open. This is consistent with ignored
extra attempts, not evidence of three processed calls or an API limit violation.
The provider counts all web_search_call items regardless of action or status.
It therefore rejects both outputs unnecessarily and overcounts search fees.
The exact internal reason for an unfinished item cannot be proved from output alone.

Original token-cost estimate totals $0.07245450. Twelve output items were charged
locally as $0.12, yielding the reported **$0.19245450** conservative estimate.
Seven completed search actions, corroborated by returned num_requests values,
would imply $0.07 in search fees and **$0.14245450** total under the published rate
assumptions. This revised figure is a diagnostic estimate, not a corrected invoice.
The raw responses additionally report billing.payer=openai; this field does not
establish the user's actual charge or credits. Invoice/usage reconciliation remains
necessary. Production estimates and original report have not been silently rewritten.

Recommended accounting separates: attempted items, processed completed actions,
search actions, page opens/finds, reported request counters, token categories and
invoice charge. Validate counter types/status; hold reservations for ambiguous
usage. Do not blindly promote undocumented optional fields to a billing contract.
Count unique call IDs; preserve unfamiliar actions and reconcile conservatively.
An unfinished surplus item should be an audit warning, not proof that otherwise
valid evidence is false. Correcting this does not make its candidates verified.

## Spending safeguard assessment

Current strengths: atomic SQLite preflight reservations, no automatic SDK retries,
timeouts, cost retention on missing usage, usage recorded even for rejected output,
and identity-specific caching. The ledger reserves $0.3335/request using the full
400k model context and configured tools/output, then settles a calculated estimate.

Current limitations: settled values are estimates; fee counting is wrong; reserved
tools assume the API processes the configured limit; full-context arithmetic is a
conservative policy rather than a server dollar cap. The daily ledger resets by UTC
date, and an ephemeral Actions runner gets a fresh database unless explicitly
restored. Concurrency serialization alone does not persist spending. A timeout or
workflow rerun could incur additional cost. Existing workflow push/manual triggers
remain unchanged and **must not be used for Experiment 2** without a new explicit
authorization and experiment ledger. No workflow was triggered in this assignment.

Proposed safeguards before another live pilot:

1. Durable experiment ID with a fixed total authorization, independent of UTC days,
   process restarts and Actions reruns. Atomically reserve before every outbound
   request. Deny concurrent or repeated execution of consumed request slots.
2. Store response/usage/ledger after every request, before parsing or next work.
   On timeout, unknown usage, spend-model discrepancy or interrupted persistence,
   retain the reservation and stop; do not retry or assume zero charge.
3. Sequential requests, explicit maximum paid attempts and no automatic retries;
   low output cap, fixed model/service tier, default search return budget, bounded
   tool processing. Search-context low is a hint, not an exact cost bound.
4. Compare both measured estimate and remaining authorization before each next
   dispatch. Require remaining budget to cover the full conservative reservation
   plus safety margin; do not use only historical average cost as a reserve.
5. Dedicated project/key and enforced platform spending control where supported,
   with awareness of enforcement lag and other traffic. Cancellation is best effort,
   not a refund or exact cap. Explicitly reconcile invoice before budget claims.

At $0.15 total, current conservative reservation exceeds the entire experiment
budget even for **one** request. A strict preflight must therefore refuse paid
execution. Do not silently shrink the reserve to make the plan run. See the
[Experiment 2 plan](../experiments/reference-first-v2/PLAN.md).

## What this establishes and what it does not

Confirmed: flawed extraction consistency, missing source artifacts, no verified
benchmarks, an unimplemented reference evaluator, and incorrect output-item call
accounting. All thirteen retained sale rejections were defensible. No shipping
value should ever be added to CardScan market value.

Hypotheses: a permitted condition-specific reference is easier to verify than enough
individual sales; reviewed aliases improve recall; direct source adapters provide
better coverage than search snippets. These need testing, not assertions.

Accuracy and achievable coverage remain unknown. Neither the five-card abstention
rate nor the twenty unverified claims establish source scarcity or pricing accuracy.
Reference-first is worth a controlled offline/source-verification trial; it is not
yet an evidence-supported solution to CardScan's pricing problem.
