# Experimental AI market estimation

This is a separate pricing experiment, implemented on 2026-10-25. It asks an
OpenAI web-search agent to synthesize a value and range like a collector researching
a card. The [first authorized paid run](../research/results/ai-market-five-2026-10-25.md)
completed five requests for a conservative $0.18680975 estimate. The model proposed
five prices; validation accepted none. Authorization is consumed and disabled.
Mocked test outputs demonstrate contracts and behavior, not real pricing accuracy.

## How it differs from verified-sales pricing

| Method | Evidence and calculation | Meaning of result |
| --- | --- | --- |
| Existing deterministic engine | Minimum qualified, independently substantiated exact-condition completed sales; median and outlier review | Verified-sales valuation under existing policy |
| New AIResearchValuationProvider | AI synthesis of identifiable published references and/or reported completed sales, with asking prices as context | Experimental market estimate, with assumptions and unverified source extractions |
| Source-reference adapter | Independent source retrieval, field support and policy checks | Source-supported observations; not automatically a valuation |

The original engine, provider, verifier and their qualification rules are unchanged.
No scanner, inventory system, price cache, refresh scheduler or background job was
added. The legacy ResearchStore has a cache table; the new experiment uses its
ledger infrastructure but never reads or writes a valuation cache.

## Architecture and schema

- `market_models.py`: strict Pydantic model for API structured outputs; the checked-in
  [schema](../experiments/market-ai/schema.json) is generated from this contract.
- `market_provider.py`: official Responses SDK, web search, low reasoning, server-side
  credentials, no SDK retries, strict schema, response IDs, raw-response audit.
- `market_policy.py`: target matching, evidence classification, condition/identity
  contradictions, range checks and source-URL grounding. It never calculates a
  sales median or manufactures missing source fields.
- `market_budget.py`: atomic experiment-wide budget and one-attempt-per-case slots,
  in addition to existing daily/request controls. Survives UTC date changes and
  process restarts when the SQLite ledger is retained.
- `market_experiment.py`: the exact original five targets, incremental evidence
  files, strict-pilot historical comparison, cost/latency summary and stop rules.
- `market_score.py`: manual independent reference entry and human review metrics.
- `accounting_audit.py`: separate action-based diagnostics; does not change the
  original estimator or lower production reserves.

Model output includes requested identity/condition, estimated value/low/high,
currency, valuation type, evidence quality, sources, supporting source IDs,
rationale, assumptions, limitations, recommendation and abstention flags.

Each source retains name/URL, reported price/currency, price meaning, category,
nullable observed identity, source condition label/scope, source date and its
meaning, item-price basis, observation kind, summary and missing fields.
Server output additionally retains source audit decisions, API-returned URLs,
research retrieval timestamp, usage, conservative and diagnostic cost estimates,
request/response IDs and latency. `card_identity` is explicitly the requested target
echo; it is not proof that a source reported that identity.

The model cannot assign independent verification. Every source is marked
`unverified_ai_extraction`, with `independently_verified=false`. The separate
source adapter remains available for a future enrichment step but is not silently
run or credited here. Search snippets and aggregator rows stay reported-sale
evidence, never authenticated transactions. API source lists establish that a URL
was returned, not that the page substantiates its reported price.

`research_retrieved_at` records when CardScan received the research response.
`source_page_retrieved_at` remains null because the API does not provide a verified
page-fetch timestamp. Missing source dates remain null; retrieval time never fills
in a sale date or publisher update date.

## Acceptance policy

No fixed source count or transaction ID is required. One suitable published price
may support an estimate. The AI supplies the synthesis and range; deterministic
checks constrain how that synthesis may be presented.

Known wrong set, collector number, language, edition, finish, grading or condition
excludes a source as an estimate anchor. A plausible name/set/number match with
unknown remaining printing dimensions can support only a provisional output with
review and explicit unknown-field warnings. It is never called an exact verified
match. Missing name/set/number cannot support a scalar estimate.

A requested-condition estimate needs at least one priced reference with an explicit
matching condition label. NM is not inferred from raw/ungraded, pack fresh, great
or excellent condition, or ranges such as near mint or better. Structured condition
contradicting its label, summary or missing-information declaration is excluded.
The detector is conservative and incomplete; it cannot prove that a consistently
fabricated extraction is true. Independent review is still needed to measure errors.

Generic/unknown-condition evidence can support `generic_ungraded_reference`,
clearly labeled review recommended and not a requested-condition valuation. A
`provisional_condition_estimate` requires explicit condition support but admits
printing uncertainties. Only a complete claimed printing and explicit condition
may receive `condition_specific_market_estimate`; this remains an AI estimate.

Asks are supplementary context and never the sole pricing anchor. Unknown prices,
currency, price meaning, observation type, uncited URLs, future/stale dates and
known shipping-inclusive totals cannot support the estimate. All market values
exclude shipping and tax; item-only price classification is required. Original
source date may be unknown, but this forces review. Current freshness window is
90 days, matching the original experiment, and is configurable.

The range must be positive, finite and contain the estimate. A generic/provisional
result cannot be recommended as a usable condition-specific estimate. Accepted
output can still be inaccurate; recommendation and evidence-quality labels are not
calibrated probabilities. There are no numerical confidence percentages.

Incorrectly structured or unsupported estimates are quarantined with validation
errors and no accepted scalar. Too-weak or materially contradictory evidence can
return explicit abstention with all three values null. Raw source claims and
response audit are retained to diagnose failures; they are not promoted to facts.

## Five-card experiment

The harness imports the original manifest unchanged: English Obsidian Flames
Charmander 26/197 standard non-holo NM; English 151 Charizard ex 199/165 standard
holo NM; English Base Set Unlimited Charizard 4/102 holo LP; English First Edition
Fossil Gengar 5/62 holo LP; Japanese Pokémon Card 151 Charizard ex 201/165 standard
holo NM. All raw. The first live proposals are retained in the results report as
unvalidated model output, with original rejection reasons.

Offline plan, no credentials or API calls:

```bash
python -m pip install -r requirements-ai.txt
python -m cardscan.ai.market_experiment --as-of 2026-10-25 \
  --settings experiments/market-ai/settings.json
```

[Checked-in plan](../experiments/market-ai/plan.json) has null live estimates,
costs and latency. The mock five-card run is tested separately and not stored as
market results. Comparison to the strict pilot is historical coverage/cost/latency
only; returning more estimates does not establish improved accuracy.

After **new explicit user authorization**, a server-side operator can run:

```bash
python -m cardscan.ai.market_experiment --as-of 2026-10-25 \
  --settings experiments/market-ai/settings.json \
  --experiment-id market-ai-five-v1 --total-limit-usd 2.00 \
  --database local-evidence/market-ai/ledger.sqlite \
  --output local-evidence/market-ai/run --execute --authorize-paid
```

Set `OPENAI_API_KEY` only in the server environment, never in a committed file or
command argument. The existing GitHub repository Actions secret can be used; no
new key is required and the user does not need to run Python from a phone.

The prepared workflow is `market-estimate-pilot.yml`. Its checked-in authorization
is false. Adding it runs tests/an offline plan only. After new approval, the
operator records that approval in `experiments/market-ai/authorization.json`, binds
`base_commit` to the current main head and commits that file alone. The push can
then execute the five-card run using the existing secret. The gate allows only
the first attempt of that direct approval push on main. Manual dispatch and reruns
cannot execute a paid replay. Results and ledger upload as a seven-day artifact.

Do not edit the authorization file to true without session authorization. Another
paid attempt after interruption requires a new user decision, retrieval/reconciliation
of the prior ledger and a reviewed plan; do not simply reset the experiment ID or
create a new ledger. The workflow intentionally refuses paid reruns rather than
assuming an ephemeral runner has preserved budget state. Other clients using the
same key remain outside this application's ledger.

## Costs and stop rules

At the currently reviewed GPT-5.4-mini rates ($0.75/M input, $0.075/M cached input,
$4.50/M output; $0.01/search action), 10k uncached input + 2k output + two searches
illustrates **$0.0365/card, $0.1825/five cards**. This is a scenario, not a forecast,
invoice, guarantee or authorization. Price and availability can change; recheck
[official model rates](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
and [web-search pricing](https://developers.openai.com/api/docs/pricing) before running.

New output cap: 4k tokens. Conservative reserve: **$0.338/request**, using the same
full-400k-context policy, plus output/tools. Five full reserves: **$1.69**. Proposed
authorization envelope: **$2 total**, with a $0.35 per-request guard and five paid
attempts maximum. The previous five-card approval is not authorization for this
experiment. Cache TTL is zero and no cache is used. Existing minimum_sales remains
in the reused settings but applies only to the strict engine, not AI synthesis.

The original conservative usage estimator still charges all web output items for
local accounting; action diagnostics distinguish completed searches, page opens,
unfinished attempts and reported counters. This prevents the prior response-wide
rejection caused solely by an unfinished extra page open. Processed tool actions
and token assumptions are still checked. None of these settings is an API dollar
cap. Invoice reconciliation remains necessary.

Unknown-model/usage responses, API timeouts/errors, incomplete responses and
accounting discrepancies stop further attempts. Unknown cost holds the full
reservation. No SDK retries. Per-experiment and per-day preflight is atomic. Each
card consumes one durable paid-attempt slot; it cannot be retried under that
experiment ID. Outputs refuse directory overwrite. Partial runs retain all five
planned cards in the coverage denominator. No known-cost reservation is reduced
until the response has been accounted for and saved in the ledger.

## Independent reference entry and scoring

Copy [the blank reference template](../experiments/market-ai/independent-references.template.json)
to a local file. A collector/shop owner enters an independent reference price,
USD currency, exact target/condition, matching as-of date, reviewer/date, evidence
notes/URLs and reference origin. Set independently_established only after review,
and used_agent_estimate_as_reference=false. Never fill in the agent's output as its
own reference. Collector and shop assessments are supported; three authenticated
sales are not required for a human assessment in this experiment.

The reviewer also labels printing correctness, condition handling, unsupported
pricing claims and source relevance by source ID. The reference price can be absent
while qualitative review is completed. Blank/unreviewed/invalid entries are not
ground truth. These attestations are not authenticated by the software.

```bash
python -m cardscan.ai.market_score --results local-evidence/market-ai/run \
  --references local-evidence/market-ai/independent-references.json
```

Reports APE, within ±10%, range containment, human-reviewed source/printing/condition
metrics, unsupported-claim rate, coverage, cost per attempt and per usable
recommendation, and latency. Accuracy uses only independently attested references
with a supported output review; unsupported output errors remain visible separately.
Generic references are not scored against requested-condition reference values.
Missing independent prices yield null metrics, never presumed success. Correlated
source controls may test extraction more than independent market accuracy; disclose
that in notes. Five cards demonstrate feasibility only, not commercial reliability.

## Validation and next step

Routine tests use mocked SDK responses and synthetic fixtures. They cover exact
identity, generic/explicit conditions, contradictions, categories, missing evidence,
API errors, abstention, price ranges, costs, budgets, one-shot approval and manual
scoring. Existing strict-engine and source-adapter tests continue to run.

Validation on 2026-10-25: **156 tests passed**. A separate official OpenAI SDK
serialization/response-parsing check also passed using `httpx.MockTransport`, a
synthetic key and an in-memory response. It made no network or paid API requests.
An offline plan/schema consistency check and disabled-authorization check passed.
The SDK check does not establish live source coverage or valuation accuracy.

Next: replay the saved first-run responses offline to fix representation/normalization
gaps, inspect every source claim, and collect independent collector/shop reference
prices. Further paid experiments require new authorization. Measure real error and
cost per accepted useful estimate before deciding whether to expand the approach.
No claim of meeting the ±10% target is made.
