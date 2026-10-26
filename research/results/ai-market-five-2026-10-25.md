# First AI market-estimation experiment: actual results

Run: https://github.com/cmollical/Cardscan/actions/runs/40231931432
Approval/code commit: `6f4c542c02f0ef493b6e18d58ac4d324c29537ec`.
Artifact: https://github.com/cmollical/Cardscan/actions/runs/40231931432/artifacts/12613078251
ZIP SHA-256: `8a7170f5709007caead30a5669e9468ef003627d1798a3216332b94fb2b76a5a`.
Full extracted proposals, source claims, validation errors, response IDs, usage and
latencies: [machine-readable report](ai-market-five-2026-10-25.json).

## Outcome

The user authorized one five-card experiment with a $2 total application budget.
All five API requests completed. **The model proposed five estimates; the validator
accepted zero.** This is different from the agent finding no useful price information.
No additional paid requests or retries were made. The approval file is now marked
consumed and disabled. No independent collector/shop reference values were supplied,
so accuracy, MAPE and within-10% success remain unmeasured.

The following amounts are **unvalidated AI proposals**, not verified card values or
independently substantiated source quotes. Dollar signs are displayed as currency
formatting here; the original raw strings are retained in the JSON report.

| Exact raw target | Condition | AI proposal USD | AI range USD | Conservative cost USD | Seconds |
| --- | --- | ---: | --- | ---: | ---: |
| Charmander, Obsidian Flames 26/197, English standard non-holo | NM | 0.35 | 0.25–0.60 | 0.02658250 | 15.80 |
| Charizard ex, Pokémon 151 199/165, English standard holo | NM | 345 | 320–370 | 0.02327050 | 14.37 |
| Charizard, Base Set 4/102, English Unlimited holo | LP | 365 | 345–460 | 0.04368300 | 16.78 |
| Gengar, Fossil 5/62, English First Edition holo | LP | 320 | 275–470 | 0.04751325 | 21.66 |
| Charizard ex, Japanese Pokémon Card 151 201/165, standard holo | NM | 390 | 380–405 | 0.04576050 | 16.75 |

Total conservative API estimate: **$0.18680975**; mean **$0.03736195/request**.
Separate completed-search-action estimate: **$0.12680975** total.
These are usage-derived estimates, not reconciled invoices. Mean latency was
**17.0711 seconds**, compared with 9.5966 seconds in the historical strict pilot.
Cost per accepted usable estimate is undefined because none was accepted.

Twenty model source rows: seven published-reference claims, eleven completed-sale
report claims, and two asking-price claims. All remain unverified AI extractions.
Names included TCGplayer, PriceCharting, eBay, ValueMyCard, Cardflip, PokeValues,
LastSold, Bill's Archive, CollectAIO and The Lab TCG. These are reported source
locations, not an endorsement of data accuracy, independent provenance or commercial
permission. Several sources mirror the same marketplaces.

## Why the proposals were rejected

Some failures are avoidable interface design problems, not evidence scarcity:

- Money fields accept arbitrary strings in the API schema, but the parser expects
  bare decimal strings. The model returned `$320`, `$365` and dollar-prefixed source
  amounts. A constrained decimal schema or lossless USD formatting normalization
  should prevent this mismatch.
- `observed_identity.condition` is free text, but policy expects canonical `NM`/`LP`.
  The model supplied `Near Mint`/`Lightly Played`, even alongside matching source
  labels. Preserve the original text and map explicit labels to canonical values.
- Literal comparison rejects source labels such as Holofoil versus holo, 1st Edition
  versus First Edition, EN versus English, and expanded set names versus 151.
  Reviewed source-specific aliases would improve representation without inventing
  missing observations. A bare collector number must not acquire a denominator
  merely from the request.
- The model used a page URL as a source row ID. Several distinct reported rows on
  the same page consequently had duplicate IDs. IDs should be unique row handles;
  page identity and transaction independence are separate matters. Do not invent
  marketplace sale IDs or count duplicated rows as independent sources.

There are also substantive reasons not to issue these as established values:

- Charmander mixes a generic guide with purported NM sale rows whose finish is
  unknown; its stated supporting ID points to the generic page rather than uniquely
  identifying the sales it says it weighted.
- English Charizard ex has potentially relevant NM reference claims, but editions
  are unstated, some source language is missing, and full price support has not
  been independently checked. Complete-condition-specific labeling is overconfident.
- Base Set Charizard includes an MP sale in the supporting IDs even though the
  rationale calls it adjacent context only. Some LP rows admit shipping-exclusion
  uncertainty despite item-only flags; the upper report has offer-price uncertainty.
- Gengar's apparent LP references disagree substantially, and some evidence lacks
  dates or transparent methodology. Normalizing labels would not resolve the conflict.
- Japanese Charizard asserts explicit Near Mint scope for one source while leaving
  observed condition null; another raw aggregate has RAW in condition/finish fields.
  Generic raw pricing cannot establish NM, and the requested edition remains unstated.

The initial output has not been reclassified, normalized or silently promoted to
accepted output after the fact. Full original proposals and policy decisions remain
available in the report and artifact. No claim is made that normalizing formatting
alone would make all five defensible estimates.

## Interpretation and next step

The experiment demonstrates that the agent can synthesize numerical proposals at
a few cents per request. It does **not** demonstrate that they are correct or useful
enough for shop pricing. Unlike the first pilot, failure is clearly influenced by
our representation/normalization contract as well as the quality of evidence.

Next engineering step: lossless monetary/label normalization and stable source-row
handles, tested by replaying these exact saved responses offline. Preserve unknown
fields, disagreements, shipping restrictions, adjacent-condition exclusions and
provisional labels. Evaluate any coverage changes separately from independent
pricing accuracy. This offline replay requires no new paid API requests.

The GitHub runner passed **156 mocked automated tests** before execution. Its
successful workflow status means the experiment ran, not that the proposed prices
passed validation. The results show why synthetic happy-path tests alone cannot
establish compatibility with real model output or pricing quality.
