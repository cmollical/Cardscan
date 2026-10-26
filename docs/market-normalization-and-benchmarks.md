# Lossless evidence normalization, offline replay and independent benchmarks

Completed 2026-10-26. **No additional OpenAI API requests were made.** The research
prompt, model output schema, strict verified-sales evaluator and source-verification
requirements are unchanged. This work changes experimental post-processing and
review, not the reported source facts or the model's proposed prices.

## Result: formatting mattered, but it was not the whole problem

| Card / requested condition | Original AI proposal | Original outcome | Revised outcome | Numeric display for review |
| --- | ---: | --- | --- | --- |
| Charmander, Obsidian Flames 26/197, English standard non-holo NM | $0.35 | invalid_estimate | insufficient_evidence | none |
| Charizard ex, 151 199/165, English standard holo NM | $345 | invalid_estimate | provisional_estimate | $345, range $320–$370 |
| Charizard, Base Set 4/102, English Unlimited holo LP | $365 | invalid_estimate | insufficient_evidence | none |
| Gengar, Fossil 5/62, English First Edition holo LP | $320 | invalid_estimate | provisional_estimate | $320, range $275–$470 |
| Charizard ex, Pokémon Card 151 201/165, Japanese standard holo NM | $390 | invalid_estimate | provisional_estimate | $390, range $380–$405 |

**0 usable, 3 provisional, 2 insufficient.** No accepted valuation or approved
inventory price was created for these five cards. Displayable provisional values
remain the original AI proposals after lossless formatting conversion, not new
calculations, verified source quotes or independently measured accurate prices.

| Metric | Original | After normalization |
| --- | ---: | ---: |
| Model proposals | 5 | 5 |
| Structurally parseable with original schema | 5 | 5 |
| Complete decimal-parsed proposal and range | 3 | 5 |
| Retained evidence rows | 20 | 20 |
| Decimal-parsed source prices | 6 | 20 |
| Usable estimates | 0 | 0 |
| Provisional estimates | 0 | 3 |
| Explicit insufficient-evidence outcomes | 0 | 2 |
| Invalid-estimate outcomes | 5 | 0 |

The old five invalid outcomes were validation failures, not explicit model
abstentions. They are not retroactively relabeled as insufficient-evidence
decisions. The old validator did not produce a comparable count of substantive
conflicts. The normalized audit finds **three contradictory rows**, **one
cross-source price-spread conflict**, and **one known condition-mismatch row**.
No independently measured matching-accuracy claim follows from these counts.

Detailed outputs:

- [Before/after and every row](../research/results/normalized-market-replay-2026-10-26.md)
- [Full transformations and decisions](../research/results/normalized-market-replay-2026-10-26.json)
- [Benchmark evaluation, currently unmeasured](../research/results/benchmark-evaluation-2026-10-26.json)

## Original evidence and reproducibility

The local original artifact was available and its ZIP hash matched
`8a7170f5709007caead30a5669e9468ef003627d1798a3216332b94fb2b76a5a`.
Its SQLite `requests.audit.response` records contain the exact final model text.
Those strings were extracted directly, not reconstructed from the summary report.

[raw-final-texts.json](../research/evidence/market-ai-2026-10-25/raw-final-texts.json)
preserves all five unchanged final `output_text` strings, per-text UTF-8 SHA-256,
response IDs, requested targets, API-returned source URLs, original errors,
retrieval times, token usage, latency and original cost estimates. The original ZIP,
SQLite and result JSON remain unchanged under ignored `local-evidence/`.
Opaque reasoning payloads, credentials and full marketplace pages are not published.
This bundle preserves final model text, not a claim to reproduce original HTTP
wire encoding or independently captured marketplace content.

Replay checks every text hash, parses the original strict schema and reruns the
unchanged original validator, requiring exact equality with its recorded errors.
The old `market_policy.py` remains the historical baseline. All new transformations
operate on separate copies; raw evidence and the original proposal remain available.
Output is deterministic: no new timestamps, randomness, model calls or source-price
retrieval. The raw bundle digest and artifact digest identify replay inputs.

```bash
python -m cardscan.ai.market_replay \
  --output local-evidence/normalized-replay.json
```

This writes JSON plus an adjacent Markdown report. Repeating it with the same
bundle/code gives identical reports. The committed reports can be regenerated with
the corresponding path under `research/results/`.

## Monetary normalization

`normalization.normalize_money` retains raw value/currency, canonical decimal text,
currency, applied rules and errors. It supports bare decimals, `$365`, `USD 365.00`
and correctly grouped `1,250.00` forms. It uses Decimal, preserves decimal precision
and never performs float arithmetic, FX, rounding, shipping subtraction or tax
inference. Int inputs are exact; floats and booleans are refused.

A bare `$` requires a separate explicit USD currency field, since dollar symbols
alone are not a unique currency. An explicit USD prefix can establish currency
when the field is missing; a conflicting explicit currency still rejects. Unknown
currencies, unsupported currencies, negative/zero prices, exponents, locale-style
`1.250,00`, malformed grouping, and comma-only ambiguous notation are refused.
Missing price stays null. Valid formatting does not validate the price's truth.

The original API schema and prompt remain unchanged, so the model may still return
formatted strings. The new deterministic post-processor handles their meaning
without pretending that a structurally valid response is a correct valuation.

## Reviewed attribute mappings and catalog scope

Literal mappings cover NM/LP/MP/HP/DMG labels, Holofoil/Holo/Holo Rare, First/1st
Edition, and language codes EN/JA. Raw labels are retained beside each mapping.
Case/outer-whitespace changes are recorded. No fuzzy, embedding or similarity match
establishes identity. Unknown labels remain unresolved, not defaulted.

[set_aliases.json](../cardscan/ai/set_aliases.json) contains explicit mappings for
the five experiment sets, bound to actual TCGdex set IDs, catalog names, locale,
source URLs and content hashes. Free metadata-only catalog requests on 2026-10-26
confirmed these identifiers: English `sv03`, `sv03.5`, `base1`, `base3`; Japanese
`SV2a`. This did not retrieve new pricing benchmarks. Labels such as
`SV: Scarlet & Violet 151` are engineering-reviewed aliases to that exact catalog
entry, not claims that TCGdex itself supplies every marketplace label.

Alias lookup must resolve to one known catalog entry and agree with any explicit
game/language context. Missing source language stays missing even if the set alias
is recognizable. Outside this finite registry, add a reviewed catalog mapping
before accepting a new set label. Metadata mapping is not pricing verification.

Collector zero padding can normalize (`026/197` to `26/197`); prefixes and
denominators remain material. A bare `26` or `201` never acquires a denominator
from the requested target or catalog count. Unstated edition is not Unlimited or
standard; unknown finish is not non-holo; RAW/ungraded never becomes NM.

## Row, page and transaction identity

Every row gets a stable internal ID from research response ID, original position
and original claim hash. The original reported ID and URL are preserved. A separate
canonical page ID removes only recognized URL aliases/tracking parameters.
Multiple prices on one page remain distinct records; no number of such rows proves
independent transactions or markets.

If one original support ID names several rows, replay expands it transparently to
all those internal rows and records the ambiguity. It never guesses which row was
intended or silently creates transaction IDs. Exact duplicate claims are excluded
as repeat anchors while retained for audit. Externally supplied, provenance-bearing
transaction IDs can deduplicate repeated transactions across pages. eBay `/itm/`
IDs are kept as listing IDs, not promoted to completed-transaction IDs.

## Evidence policy and the three outcomes

`market_review.review_proposal` is separate from the original verified-sales
method. It classifies unverified sale claims, unverified reference claims, asks,
generic/mixed condition context and unknown evidence. A claim-bound independent
source review can establish reviewed benchmark support; it cannot authenticate a
transaction merely by adding a flag. Original pilot rows remain unverified.

- **Usable estimate:** identifiable, condition-appropriate, consistent support
  with independently reviewed source facts and no unresolved material review
  warnings. It does not require three authenticated transactions or approve an
  inventory listing automatically.
- **Provisional estimate:** the original proposal/range can be shown for human
  review because some eligible identifiable priced evidence supports it, but
  identity gaps, unverified extraction, uncertain freshness or disagreement remain.
  `accepted_valuation` is null. It must not become an approved listing price.
- **Insufficient evidence:** no displayable scalar. The raw proposal remains in
  the forensic record but is not an accepted estimate. Invalid ranges, unsupported
  requested-condition pricing and lack of an eligible numerical anchor abstain.

For condition-specific proposals, an explicitly matching condition anchor is
required. Generic-only information can support an explicitly generic proposal,
never an automatically relabeled NM/LP estimate. The proposal's range must contain
at least one eligible relevant price. No replacement median, arithmetic average or
condition discount is computed. A greater-than-25% spread among eligible
condition-matched prices is a review trigger, not a reason to discard high prices.

Source URLs must appear in actual returned API sources/citations. Known wrong
identity or condition, invalid/unknown currency, asks, shipping-inclusive or
uncertain price basis, ambiguous paid-sale prices, and contradictory scope cannot
anchor the value. Unknown attributes remain visible; only a fully resolved printing
can progress to usable status. Source-review attestations bind to the raw claim
hash and require a non-model reviewer, review date and source-artifact hash.

The existing provider now calls this post-processing after receiving/validating
the original structured output. It retains original errors as legacy diagnostics,
the full normalized review, and the original model proposal separately. Its
recommendation cannot elevate a provisional output to an accepted valuation.
No research instruction, paid request, retry, budget formula or cache was changed.

## Substantive problems that remain

**Charmander:** all PriceCharting source rows report only collector number 26 and
omit finish. The generic guide remains generic. Complete-number eBay rows are asks,
not market-clearing anchors. Formatting fixes cannot establish the requested NM
non-holo 26/197 printing. No numeric estimate is displayed.

**English Charizard ex:** label aliases resolve. The $345 proposal remains
provisional because source edition is absent, one source's language is absent,
freshness/source support are incomplete, and reports are unverified. Nothing fills
those missing fields from the request.

**Base Set Charizard:** two LP rows assert item-only prices while admitting unknown
shipping exclusion. Another LP claim admits offer/closing-price uncertainty. The
MP eBay row stays MP and is excluded for LP pricing. The result abstains, despite
parseable numbers and resolved Holo Rare labels.

**Gengar:** $289.91 and $460.96 LP reference claims remain in conflict. The original
$320 proposal and broad $275–$470 range can be displayed provisionally, with no
averaging, no selected “correct” source and no source truth asserted.

**Japanese Charizard ex:** one source declares explicit Near Mint scope but has null
observed condition, and is excluded. A RAW aggregate remains generic and has only
bare collector number 201/unknown finish. Another explicit NM claim supports a
provisional $390 proposal, while missing edition and unverified source facts remain.

These are assessments of the model's retained claims, not proof that the original
marketplace pages contain those facts. Normalization does not verify a source.

## Independent benchmark workflow

Use [blank.template.json](../experiments/market-ai/benchmarks/blank.template.json)
and its [schema](../experiments/market-ai/benchmarks/schema.json). All reference
prices, ranges, dates, reviewer identities and review labels are deliberately blank.
Do not copy model proposals or unverified source summaries into the reference column.

For each reference supply exact identity, requested condition, USD value/range,
reference date, source/methodology, explicit condition scope, verification status,
reviewer/date/notes and an independence attestation. Collector/shop assessments or
independently reviewed comps/references are supported. Reviewing a benchmark against
the same underlying source may measure extraction rather than independent market
accuracy; disclose that limitation in notes. An `independently_reviewed` flag is a
human attestation, not software-authenticated truth.

Keep files under ignored `local-evidence/`. Set `verification_status` to
`independently_reviewed` only after review, `independent_of_ai=true`, and
`used_ai_proposal_as_ground_truth=false`. Review printing/condition/unsupported
claims independently. A price may be entered manually, but that alone does not
make it an eligible benchmark. Exact canonical target keys are prefilled.

```bash
python -m cardscan.ai.benchmarks \
  --replay local-evidence/normalized-replay.json \
  --benchmarks local-evidence/independent-benchmarks.json \
  --output local-evidence/benchmark-results.json
```

Reference dates must match the pilot cutoff by default. If a different-date
comparison is intentionally desired, use `--max-date-difference-days N`; that
tolerance is reported explicitly. Never backdate a newly observed price.

Reports separate usable and provisional APE, median APE, ±10% and ±20% rates,
range containment and absolute dollar error (including inexpensive cards), plus
coverage, abstention and matching-failure/review counts. Known wrong/unsupported
reviewed outputs are not removed to improve the error denominator. A separate
validated-success flag requires correct printing/condition and no unsupported
claims. Rejected raw proposals are not treated as accepted estimates.

No genuine independent benchmarks were supplied for these exact conditions and
cutoffs. The committed empty-benchmark evaluation has null accuracy metrics,
60% provisional coverage, 0% usable coverage and 40% abstention. Policy condition
failure counts are distinct from independently reviewed matching accuracy, which
remains unmeasured. Synthetic test benchmarks are not market evidence.

## Validation and next milestone

The complete suite passes **188 tests**. It includes original pilot formatting and
contradiction regressions, exact response hashes, deterministic replay, duplicate
page/transaction handling, known aliases/unknown attributes, monetary precision,
benchmark arithmetic and unavailable references. All existing strict-engine tests
still run. Prompt and strict-verifier hashes are checked to guard the stated scope.

The evidence answers the central question: representation failures prevented all
five monetary proposals from being processed consistently, but correcting them
recovers only three reviewable proposals, not five usable prices. The next
milestone is independent source and collector/shop benchmark review for those
three cases, followed by measured accuracy. This needs no new paid research run.
