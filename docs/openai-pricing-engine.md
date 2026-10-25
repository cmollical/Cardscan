# OpenAI pricing research engine

## What is implemented and what is pending

`OpenAIWebSearchProvider` uses the official Python SDK's Responses API with the
built-in `web_search` tool and a strict JSON schema. It returns **evidence
candidates**, not model-calculated valuations. The first authorized five-card
pilot completed on October 24, 2026; all requests returned usage, but no verified
valuation was established. See the [original results](../research/results/openai-five-card-pilot-2026-10-24.md)
and [forensic analysis](pricing-evidence-forensics.md) for actual costs, recovered
candidates and accounting limitations. Market accuracy remains unmeasured.
Routine tests and the offline SDK integration use mocks.

The forensic assignment added twelve offline tests (102 total) and a test-only
reference-contract specification. It did not change the production provider,
completed-sale validation or estimator. In particular, the current estimator
counts all web output items, including page opens and unfinished attempts, as
search fees. Do not treat that count as a verified number of billable searches.
The existing reservation policy also blocks a strictly enforced $0.15 experiment
before any request. No additional paid experiment is authorized.

The older public-page and manual workflows remain intact. No scanner, inventory
integration or PWA has been added. Shipping and tax remain **excluded** from
market value, following the user's explicit instruction. Shipping, if known,
is stored as context; unknown shipping is allowed. USD is the only valuation
currency implemented. Foreign-language cards are researched for USD sales; JPY
or other original currencies remain visible but cannot enter a USD median.

## Repository review and reuse

The original suite passed 51 tests before these changes. `Card`, `Sale`, exact
matching, the minimum-three policy, item-price median and review-on-outlier logic
are reused. `pricing.py` adds an optional verification cutoff so later human
reviews retain their real date when valuing an earlier sale window; legacy callers
keep the original date checks. Its extreme-price guard
abstains instead of issuing a trimmed valuation. Existing manual and public-web
providers, their captured evidence and their diagnostics are preserved.

Existing limitations were broad marketplace access gaps, no model research
adapter, no API budgets/cache, and a 20-card protocol with no independent market
benchmark. The new five-card pilot is deliberately separate from those historical
results. A citation or a model's claim of certainty was never added as a shortcut
to verification.

## Architecture and evidence boundary

- `ai/models.py`: requested identity (including name and graded status), observed
  nullable identity and strict candidate schema. All observed fields must be
  supplied explicitly; unknown is null. Sets, editions and languages use exact
  canonical keys; collector-number zero padding is normalized while prefixes and
  denominators are preserved.
- `ai/provider.py`: precise source-specific query suggestions, Responses request,
  actual consulted URLs/citations, response IDs, timestamps and refusal/error
  handling. Web content is untrusted input. The model is instructed to respect
  access restrictions and not solve challenges or infer missing attributes.
- `ai/verification.py`: independent source substantiation. Default `Unverified`
  accepts no comps. `ReviewedEvidence` binds a human attestation and saved-source
  hash to the **entire claim hash**. `EbaySourceVerifier` optionally reuses the
  existing public-page parser to check the original sold page against the claim.
- `ai/valuation.py`: deterministic matching/rejection, deduplication and routing
  into the existing evaluator. Market references and active listings remain
  separate arrays and never enter the sold-comps median.
- `ai/storage.py` and `ai/costs.py`: SQLite cache, atomic budget reservations,
  actual usage records and estimated cost accounting.
- `ai/experiment.py` and `ai/score.py`: offline plans, opt-in paid execution,
  cost-free revaluation, and independent holdout scoring.

For sold candidates, exact identity, raw/single-card status, genuine source
record ID, original USD currency, date and explicit card-only price are required.
The URL must appear in API tool sources or citations. That URL check establishes
that it was consulted, **not** that it substantiates the price. Independent
verification is still mandatory. Missing IDs or ambiguous offers stay rejected;
no artificial transaction IDs are manufactured to reach the minimum count.

The default output may therefore contain useful research and references while
its formal valuation remains `insufficient_evidence`. To enable ordinary eBay
source checks use `--verify-ebay`, or independently review the captured claims
and revalue them. The eBay checker remains conservative about canonical set
aliases and modern editions; it cannot substantiate all possible printings.
It does not fetch arbitrary model-provided hosts or bypass denied access.
TCGplayer/PriceCharting candidates require independent review where no suitable
permitted deterministic source checker exists.

“Verified” in the new source adapter means a public sold page corroborates the
specific seller-declared attributes and price. It does not establish authenticity,
physical condition, payment settlement or subsequent refunds. The experiment
separately requires an independent human audit before counting success.

## Configuration and key safety

Install optional dependencies in a Python 3.10+ virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-ai.txt
```

Configure `OPENAI_API_KEY` in the server process environment or a secret manager.
For an interactive shell, this avoids displaying the key or putting it in history:

```bash
read -rsp 'OpenAI API key: ' OPENAI_API_KEY
export OPENAI_API_KEY
printf '\n'
```

Do not put the key into a manifest, source file, browser bundle, command argument,
report or GitHub. The official SDK is imported only after paid authorization and
configuration checks. It uses the official API URL, a configured timeout and
`max_retries=0`. Errors expose exception class names rather than credential-bearing
messages. Raw response/usage audit records stay in ignored `local-evidence/`.
`.env` files and SQLite state are ignored too; ignore patterns do not replace
reviewing commits for secrets.

Settings are in `experiments/ai-five/settings.json`. The initially implemented
rate card supports `gpt-5.4-mini` only. Adding a different model requires reviewing
its capabilities, context size and rates rather than silently reusing cheap rates.
Search-call/output-token limits, cache TTL, daily/request budgets, maximum daily
requests, minimum comps and sale window are configurable within validated bounds.

## Cost model and spending safeguards

Published standard USD rates checked **2026-10-24**:

| Component | Rate |
|---|---:|
| GPT-5.4 mini input | $0.75 / million tokens |
| Cached input | $0.075 / million tokens |
| Output, including reasoning tokens | $4.50 / million tokens |
| Web-search calls | $10 / 1,000 calls ($0.01 each), plus search-content tokens |

At **10,000 uncached input tokens, 2,000 output tokens and two search calls**, the
illustrative cost is **$0.0365/card**, or **$0.1825 for five**. At 20,000 input,
3,000 output and two calls it is $0.0485/card. These are arithmetic examples, not
measured performance. Finding trustworthy comps may need more research or still
fail. A cache hit has zero incremental OpenAI cost, while preserving its original
usage/cost provenance. Source verification fetches do not call OpenAI.

`usage_cost` separates cached input and counts reasoning only once as part of
output. It conservatively charges each returned `web_search_call` item and assumes
search-content tokens are included in API input usage. Actual billing details,
regional surcharges, taxes and rate changes must be reconciled with the invoice.
No API-level dollar cap is claimed.

Because “low” search context does not establish a numeric input-token ceiling,
the local ledger reserves the full published 400,000-token context at uncached
rates, plus configured maximum output and tool fees. Defaults reserve **$0.3335**
per call against a **$0.35/request** and **$2/day** guard. This is a conservative
reservation under the documented rate/context assumptions, not an expected
charge or an unconditional billing guarantee. A $0.05 request guard will block
execution because it cannot cover that reservation, even if typical usage might
cost less. Use project-level billing controls as an additional backstop.

Successful responses settle reservations using usage-based estimates. Missing
usage, timeouts, crashes and transport errors retain their reservation rather than
pretending the charge was zero. Reconcile unknown requests before adjusting
budgets; never retry automatically. Reservations use SQLite `BEGIN IMMEDIATE`
so concurrent workers sharing the same database cannot independently spend the
same allowance. Separate databases do not share a budget. Local midnight is not
used: limits are counted by actual UTC request date, not the valuation cutoff.

The SDK makes one attempt. HTTP 429, authentication/provider failures, refusals,
incomplete output, unexpected models, invalid schema and missing usage are
explicit statuses, not valuations. An incomplete/invalid output can still cost
money; usage is recorded before parsing. Hidden server work after a timeout may
continue even though this client returns an error.

## Five-card experiment

The frozen selection is in [the manifest](../experiments/ai-five/manifest.json):

| Case | Exact raw printing | Condition |
|---|---|---|
| Modern common | Charmander, Obsidian Flames 26/197, English, standard, non-holo | NM |
| Modern chase | Charizard ex, 151 199/165, English, standard, holo | NM |
| Vintage holo | Charizard, Base Set 4/102, English, Unlimited, holo | LP |
| First Edition | Gengar, Fossil 5/62, English, First Edition, holo | LP |
| Foreign language | Charizard ex, Pokémon Card 151 201/165, Japanese, standard, holo | NM |

Catalog links in the manifest are review pointers. Independent identity review
and market-liquidity confirmation remain pending; tier/category labels are
sampling choices, not claims about observed sales volume or value.

### Offline plan — safe to run now

```bash
python -m cardscan.ai.experiment --as-of 2026-10-24
```

No key, SDK client or paid API call is required. The committed `plan.json` marks
all five cases **not run**, with no invented prices, evidence counts, costs or
latencies. The cost illustration is labeled as an assumption.

### Paid experiment — only after explicit user authorization

**Do not run this command until that authorization is given.** Both flags are
required; merely having an API key does not enable execution.

```bash
python -m cardscan.ai.experiment --as-of 2026-10-24 \
  --settings experiments/ai-five/settings.json \
  --execute --authorize-paid --verify-ebay \
  --output local-evidence/ai-five/run-1
```

Omit `--verify-ebay` to collect model research candidates only; no formal price
will be issued until independent review is supplied. Each case saves target,
sources found, accepted/rejected evidence and reasons, references, active asks,
usage/cost, latency and provider status. `summary.json` summarizes the attempts.
Actual model payloads and original API responses are retained in the local
SQLite ledger. Search can consult multiple sources but cannot guarantee access
to any particular marketplace or its complete sales history.

### Review and revalue without another paid call

For each candidate, inspect its original evidence and save a permitted artifact.
Check all identity attributes, condition, sold/date status, original currency,
actual paid item price, genuine transaction ID and single-card/raw status. Use
its emitted `claim_id` as the key in a local review file. A schema illustration:

```json
{
  "<actual claim_id from result>": {
    "reviewer": "<actual human reviewer>",
    "reviewed_on": "<actual ISO review date>",
    "artifact_sha256": "<actual 64-character lowercase SHA-256>",
    "substantiates": true
  }
}
```

These placeholders are not valid review evidence. Human reviews are attestations,
not authenticated identities. Changed claims invalidate existing attestations.
Do not mark an inaccessible page or a snippet that omits the price as substantiated.

```bash
python -m cardscan.ai.experiment --as-of 2026-10-24 \
  --revalue local-evidence/ai-five/run-1 \
  --reviews local-evidence/claim-reviews.json \
  --output local-evidence/ai-five/reviewed
```

This path never calls OpenAI. It uses saved research and existing deterministic
valuation logic. Cache TTL defaults to an hour; keys include full card/name,
condition, language, edition, finish, graded state, cutoff, model, prompt/schema
version, rate version and settings. Cached **research**, not reviewed valuations,
is reused, so verifier/review changes are reflected on each valuation.

## Independent accuracy scoring

Copy `independent-reviews.template.json` to a local path. A **separate human
reviewer** must confirm each target identity and annotate claimed price URLs and
accepted comps. Each `labels` entry is keyed by the original candidate's `claim_id`
and contains exactly the factual booleans `printing_matches`, `condition_matches`
and `source_supports_claim`. Missing labels remain unaudited.

For each case, collect at least three **disjoint** reference sold comps, use the
same Candidate schema as the result, and put them in `references`. Their own
claim hashes get independent attestations in that case's `reviews` map. The case's
`reviewer` must match reference reviewers, differ from the research verifiers,
and not be the model. Review dates/artifacts must be actual. Avoid different
URLs for the same syndicated/relisted sale; automated URL/record overlap checks
cannot establish cross-marketplace independence alone.

```bash
python -m cardscan.ai.score local-evidence/ai-five/reviewed \
  local-evidence/independent-reviews.json
```

The scorer reports exact-printing and condition accuracy on independently audited
accepted comps; source-URL substantiation and its review coverage; sufficient
comps across all five planned cases; median absolute percentage pricing error;
within-10% rates on independently scored cards and success across the full cohort;
average/maximum incremental estimated API cost; and average end-to-end latency.
Unreviewed URLs do not count as verified; the all-URL substantiation percentage is
null until coverage is complete. Missing costs remain unknown, not zero. Costs
of cached revaluation are explicitly incremental; consult the original run to
measure initial research costs. Inaccessible, unreviewed, mismatched, insufficient
and unsubstantiated valuations do not count as successful.

A five-card pilot cannot establish broad ±10% accuracy, calibrated confidence,
commercial reliability or liquidity across Pokémon. All real metrics remain
**unmeasured** until paid execution and independent review are authorized and done.

## Verification performed

- Full automated suite: **90 tests passed**, using mocked research/verification.
- Official OpenAI Python SDK **2.54.0** against an in-memory `httpx.MockTransport`:
  request serialization and response parsing passed; no network or paid calls.
- Existing synthetic demo, compile checks and whitespace checks pass.
- Offline five-card plan runs with no key and no API calls.

The SDK mock proves local integration behavior, not that the live model accepts
this request/tool/schema combination or finds adequate evidence. Rate limits,
response shapes, citation coverage, source access and paid economics need the
explicitly authorized pilot. No test result above is a real market-accuracy result.

## Primary OpenAI references

Reviewed 2026-10-24:
- [Responses creation and max_tool_calls](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Web search and source inclusion](https://developers.openai.com/api/docs/guides/tools-web-search)
- [Responses structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [GPT-5.4 mini capabilities and rates](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
- [Published tool pricing](https://developers.openai.com/api/docs/pricing)
