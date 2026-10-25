# Experiment 2: two-card reference-first comparison

Status: **design only; not authorized; no paid requests executed**.
Spending target: $0.15 total, not an authorization or guaranteed maximum charge.
Do not run the existing five-card Actions workflow for this experiment.

## Fixed targets

| Case | Exact raw printing | Condition |
| --- | --- | --- |
| modern-common | Charmander, Obsidian Flames 26/197, English, standard, non-holo | NM |
| modern-chase | Charizard ex, Pokémon 151 199/165, English, standard, holo | NM |

Use the corresponding existing five-card manifest targets without changing finish,
edition, language or condition. Independently review product mappings first; a
manifest target is a request, not evidence that a source matches it. Preserve the
same as-of cutoff within a paired comparison. Independent controls must verify
non-holo versus reverse holo and exact special illustration printing.

## Stage A: offline control, zero API cost

Freeze the original pilot ZIP hash and extraction. For these two cases the original
transaction-first control has ten retained sale claims, zero qualified sales and
zero valuations. Original reported request estimates total $0.07398250; the
search-action diagnostic estimate is $0.05398250. Mean case latency is 10.478904504
seconds. These are historical control measurements, not new Experiment 2 results.

Replay classification/support gates against the same ten claims. The reference arm
may identify discovery URLs but cannot convert a sale row into a published
benchmark. No verified reference is present; reference coverage on this frozen
extraction is also zero. This tests category discipline and abstention, not whether
a different search prompt would find benchmarks. Record proposed-arm live results
as null/not_run, not zero-cost live success.

Add synthetic fixtures (clearly labeled synthetic) for an explicit NM reference,
generic ungraded guide, asking-price statistic, wrong printing/condition, stale
reference, conflicting benchmarks, missing field support and contradictory condition.
Test-only specification is not a production replacement or evidence of accuracy.

## Stage B: source feasibility, zero paid OpenAI cost

A future source-verification implementation/reviewer should inspect permitted
public source pages or user-provided independently captured evidence. First try
TCGplayer exact product + finish + NM scope, then a suitable published reference
with known semantics. Keep other-condition/ungraded guides as context. Do not
access gated sales history or bypass challenges. Document permission constraints.

Retain minimal permitted source content, retrieval timestamp, hash, selector or
location, price label, exact product ID, active variant/condition selection, currency,
price basis and methodology definition. Verify that changing a URL query actually
changes the displayed benchmark, rather than only filtering seller asks.

If neither card has a verifiable condition-specific benchmark, stop and record the
failure. Do not spend API money on a reference extraction that lacks verifiable
condition semantics. This feasibility stage was designed, not executed here.

## Stage C: future paid research comparison, gated

Preferred full design: two cards × two arms = four independent requests. Arm A
uses frozen transaction-first instructions; Arm B asks for explicit-condition
published benchmarks first, then separately labeled sold corroboration and asks.
Same model snapshot, token/tool limits, source restrictions, cutoff, verifier,
cache policy, valuation policy and time block. Randomize arm order within card;
keep discovery caches separate. Do not let one arm see the other's output.
Freeze prompts/settings/hashes before dispatch and report any incomplete pair.
Current provider is not replaced; this requires a separately reviewed experiment
adapter and authorization after the verification/accounting work.

At 10k uncached input tokens, 1k output tokens and one search action, an illustrative
request costs $0.022; four cost $0.088. At 15k/2k/two searches, four cost $0.161.
These are scenarios, not caps or promises. The pilot's original conservative
five-card average would imply about $0.154 for four requests; action-based average
would imply about $0.114. Neither average provides a reservation guarantee.

The existing conservative default reserve is $0.3335/request. It exceeds the entire
$0.15 target. Even assuming only 128k search context (which does not itself bound
all model input) would not justify four requests under $0.15. **Paid dispatch must
remain blocked** until a defensible bound or an explicitly approved different
budget/risk policy exists. A post-response stop cannot prevent overspend by the
request already in flight. Do not claim hard enforcement from max_tool_calls or
small output limits alone.

An optional smaller design uses the historical control plus two new reference
requests. It reduces paid requests, but is a temporally confounded feasibility
comparison, not a controlled causal A/B study; label it accordingly. Its conservative
preflight is also blocked at the current $0.15 target.

## Required stop rules

- No paid dispatch without new explicit authorization covering this experiment.
- Durable experiment-wide $0.15 ledger and one-time request slots across restarts,
  UTC dates and runners. Restore ledger before dispatch; absence/restore failure
  blocks execution. No push-triggered automatic paid run or automatic retries.
- Before each sequential dispatch: measured/unknown committed cost + conservative
  next-request reservation + safety margin must fit remaining authorization.
  If not, stop, even if coverage is zero or a comparison pair remains incomplete.
- Missing/invalid usage, timeout, counter discrepancy, unexpected model/service
  tier, unknown search action, or failed artifact write stops further dispatches.
  Hold the full reservation. Do not retry to obtain a nicer outcome.
- Proposed soft early-stop thresholds, subordinate to conservative preflight:
  stop after a request estimate exceeds $0.04 or cumulative estimate reaches $0.10.
  Stop if no independently verifiable explicit-condition reference survives the
  first reference request. These do not cap the request already executing.
- Save partial results and aborted pairs; count aborted/insufficient cases in the
  coverage denominator. Never charge a new run under the previous five-card approval.

## Frozen evaluation and independent review

For every arm/case retain exact target, model/prompt/settings hashes, timestamps,
candidate and rejection counts, evidence URLs, field-support locators, verifier
decisions, source dependencies, tier-specific values, selected method, limitations,
usage by action and status, token categories, cost estimates and latency. Preserve
all candidates even if response-level validation fails; mark them quarantined.

Reviewers inspect source material independently and are blinded to arm and any
computed value where practical. Independent target matching is required. For
accuracy, assemble a disjoint set of independently reviewed current condition-
matched sold controls (minimum three per card), excluding any transaction/underlying
evidence used in valuation. If unavailable, report pricing error as unmeasured.
Verifying a benchmark against its own page tests extraction, not valuation accuracy.

| Metric | Definition |
| --- | --- |
| Exact-card matching | Correct independently reviewed full-printing claims / reviewed identity claims; show review coverage |
| Classification | Correct independently reviewed sale/reference/ask/unknown labels / reviewed candidates |
| Condition integrity | Explicit correctly mapped requested condition / condition-specific claims; unknowns reported separately |
| Price substantiation | Price + semantics + printing + condition supported by retained source / reviewed priced claims |
| Sold corroboration | Distinct independently verified qualified sales per case, separate from benchmark count |
| Unsupported rejection | Rejected unsupported/contradictory controls / all such reviewed controls; any unsupported issued value is failure |
| Usable coverage | Cases with independently verified condition-appropriate selected value / both planned cases per arm |
| Pricing accuracy | APE/MAPE and within ±10% only against disjoint verified controls; otherwise null with count |
| Cost | Original estimator, search-action estimate and invoice reconciliation separately; unknown never zero |
| Latency | Per request discovery, verification and total wall time; offline replay is not live latency |

Usable coverage requires an actual independently substantiated value, not merely a
well-formed response or a cited source. Improvement requires reference-first to
increase that coverage without introducing any unsupported valuations or condition
errors in the reviewed cases. With two cards, even success demonstrates feasibility
only; it does not validate commercial accuracy or the ±10% target generally.

## Readiness checklist

All live results are pending. Before authorization: independently verify one exact
condition-specific benchmark, implement/prove accounting and durable budget guards,
review condition contracts, freeze prompts and thresholds, and inspect a concrete
reviewable experiment runner. No request to authorize is made by this design.
