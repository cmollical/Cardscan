# Alternative Pokémon pricing APIs: actual investigation, 2026-10-26

CardScan retrieved condition-specific, printing-specific price references for all
five targets from **TCGTracking's documented Open TCG API**, without a key or
TCGplayer developer access. The LP Base Set Charizard reference was **$527.70**,
exactly matching the user's October 26 manual observation. This is a successful
retrieval demonstration, not a five-card accuracy validation or a conclusion that
TCGTracking has unrestricted upstream redistribution rights.

The strongest immediately testable personal-research option is TCGTracking;
JustTCG is the best documented next option with an explicit paid commercial license
and free condition-aware evaluation access. No JustTCG key is configured, so its
accuracy/coverage remains untested here. TCGCSV is a useful catalog and baseline
export, **not a condition-price provider**. No paid API, OpenAI call, account
creation, TCGplayer access application, internal marketplace endpoint, CAPTCHA
handling, or anti-bot bypass was used.

## Evidence and terminology

- **W**: working in an actual response in this investigation.
- **D**: documented first-party capability, not tested with authenticated data.
- **N**: not supported by the reviewed endpoint/plan.
- **?**: unknown or unresolved; absence of a published limit is not unlimited use.

[Main audit](../research/results/structured-prices-2026-10-26.json) contains ten
parsed observations, selected original SKU/product-price rows, precise monetary
strings, field pointers, document hashes, retrieval times and limitations.
[Other observations](../research/results/additional-provider-observations-2026-10-26.json)
contain TCGdex/Pokémon TCG API results, explicit untested outcomes for every card
on gated providers, and the separate user-supplied dated TCGplayer observation.
[Source manifest](../research/results/provider-source-manifest-2026-10-26.json)
records URLs, HTTP outcomes and source hashes. Raw responses are retained locally
under ignored `local-evidence/provider-investigation/`; full pages and bulk exports
are not republished. A document hash binds received bytes, not upstream truth.

A field can be directly retrieved from an aggregator without being independently
verified against its upstream marketplace. Our new records expressly distinguish
those facts. No record is a verified individual transaction. No record is an
approved automatic inventory valuation. Currency attribution to TCGplayer USD
conventions is marked documentation-based/inferred when absent from the response.
Shipping and taxes are never added; market-field shipping/tax semantics remain
unknown where the source does not define them. These fields must be clarified
before claiming a fully substantiated item-only valuation.

## Provider comparison

| Provider | Free personal access / key | Condition pricing | Exact printing and languages | Price meaning | Freshness / history | Commercial rights |
|---|---|---|---|---|---|---|
| **TCGTracking Open TCG API** | **W** free, no key | **W** requested condition priced 5/5; NM/LP/MP/HP/DMG rows | **W** product + full collector number + SKU language/variant; EN and JP tested; modern edition unspecified | **W** `mkt`, described by provider as TCGplayer SKU market price; `low`/`hi` are separate asking fields. Upstream not authenticated | **W** selected SKU exports updated Oct 25; **D** daily. Individual last sale/price age and historical endpoint **?** | Explicit invitation to use open API supports this limited research test; separate commercial license/upstream authority **?** |
| **TCGCSV** | **W** free, no key | **N** product/subtype only | **W** English and Japan categories, TCGplayer product IDs, full card numbers; finish/edition may be subtype; price-language not explicit | **W** market benchmark; low/mid/high are listings, not sales | **D** daily builds + immutable daily history from Feb 8, 2024; **W** Oct 25 current export | Own FAQ grants implicit permission; upstream pricing/image commercial rights **?** |
| **TCG API (`tcgapi.dev`)** | **D** free key, 100/day; **W** keyless games endpoint | **N** on Free; **D** Pro+ condition listing floors/median, not condition market-price field | **D** TCGplayer IDs, EN/Japan game catalogs, printing; condition docs show language but wider condition-language coverage untested | Product market price separate from condition **active listings**; median includes shipping and is unsuitable for our item-only market metric | **D** top nine games daily, rest every three days; Free 7-day history; stale price dates explicit | Free/Hobby/Starter noncommercial; Pro $49.99/month and Business commercial, subject terms |
| **JustTCG** | **D** free own key, 1,000/month, 100/day, 10/min, 20-card batches | **D** condition × printing with SKU mapping and current USD price | **D** language, condition, printing, stable variant IDs; raw + graded via separate v2 schema | Provider benchmark; currently described as multiple-marketplace/partner-sales blend, **not necessarily identical to TCGplayer Market** | **D** observation timestamps, history/statistics; high-value stale variants can expire; no guaranteed same-day price per card | Free personal/noncommercial. Paid Starter **$19/month + tax** explicitly permits app display, derived analytics, storage and lawful data combination; raw feed/resale forbidden |
| **TCGdex** | **W** free keyless | **N** reviewed prices have no requested-condition scope | **W** multilingual catalog 5/5; exact marketplace price mapping has documented known defects; edition flag is availability, not price edition | Generic TCGplayer USD / Cardmarket EUR benchmarks; never NM by inference | **W** TCGplayer Oct 14 (~12 days old); Cardmarket Oct 25; history not in reviewed card response | Open-source metadata/code does not establish third-party-price commercial rights |
| **Pokémon TCG API (`pokemontcg.io`)** | **W** keyless; **D** optional free key | **N** product/finish prices | **W** one English lookup; other three English attempts HTTP 500; no documented Japanese target ID | Generic TCGplayer/Cardmarket benchmark | **W** successful TCGplayer Oct 15, Cardmarket Nov 18, 2025; not current daily data in this sample | API/code/database openness is not a warranty of upstream pricing/image rights |
| **PriceCharting** | **N** free price API; token + Legendary subscription **$49/month** | **N** NM/LP/MP/HP/DMG; raw/ungraded and numeric grade buckets differ | **D** product/set/edition and Japanese products; grade-specific pricing | Aggregated completed-sale-based guide, not individual authenticated sale | **D** current price guide, historical chart on site; price API not a full sale history | Subscription required; integration rights are purpose/terms bound, not unrestricted resale |

No broad reliability/uptime percentage or pricing-accuracy score is inferred from
these small samples. TCGTracking and TCGCSV may share an upstream source: agreement
between them is not two independent market observations.

## Exact five-card results

All amounts below are source-reported USD conventions, retrieved October 26,
2026, approximately 15:29–15:30 UTC. API references are **dated observations**.
The AI column contains prior unvalidated proposals, not ground truth.

| Exact target | TCGplayer product ID | TCGTracking SKU ID | Requested-condition `mkt` | TCGCSV generic `marketPrice` | Previous AI proposal |
|---|---:|---:|---:|---:|---:|
| Charmander, Obsidian Flames 26/197, EN, standard non-holo, raw NM | 509703 | 7335315 | **$0.32 NM** | $0.31 Normal | $0.35 |
| Charizard ex, English 151 199/165, standard holo, raw NM | 517045 | 7436747 | **$294.42 NM** | $294.42 Holofoil | $345 |
| Charizard, Base Set 4/102, EN Unlimited holo, raw LP | 42382 | 2999653 | **$527.70 LP** | $954.65 Holofoil | $365 |
| Gengar, Fossil 5/62, EN First Edition holo, raw LP | 106521 | 2995236 | **$458.05 LP** | $374.66 1st Edition Holofoil | $320 |
| Charizard ex, Japanese Pokémon Card 151 201/165, standard holo, raw NM | 566544 | 8115821 | **$388.35 NM** | $388.35 Holofoil | $390 |

The source catalog directly identifies the full numbers (with harmless leading
zeros). SKU rows directly report conditions/languages/finishes. First Edition
Gengar is explicit in its variant. Unlimited Charizard is supported by the source
product's explicit print-run sentence; **Holofoil alone never means Unlimited**.
The three modern sources do not explicitly emit `edition=standard`: that remains
missing. Raw SKU category semantics are appropriate research context; no explicit
`graded=false` field is fabricated. All strict automatic-valuation flags remain
false pending those semantic/provenance checks, particularly shipping definition.

Selected SKU-export `updated` timestamps are Oct 25 13:36:32–13:37:40 **-04:00**
(17:36–17:37 UTC), roughly 22 hours before retrieval. These are **set export**
updates, not the last sale date or individual price-observation date.

Important conflicts retained in the audit:

- English 151 Charizard: NM $294.42, LP $307.13, MP $314.65. Do not enforce a
  fabricated monotonic condition curve or average away this inversion.
- First Edition Gengar: NM $374.66 versus LP $458.05. Could reflect thin sales,
  asynchronous prices or a provider issue; the cause is **unknown**.
- Charmander has no priced HP Normal row; Japanese Charizard has no priced HP or
  DMG row. Having SKU identifiers for all conditions does not mean all have prices.
- The vintage AI Charizard proposal $365 is $162.70 below the dated $527.70
  observation and very close to the **MP** SKU $364.73. This suggests a condition
  confound, not proof of the agent's reasoning. MP must never be relabeled LP.

There are **5/5 retrieved condition references**, **5/5 generic references**,
**0 newly authenticated transactions**, and **0 newly approved valuations**.
The manual LP Charizard value matches the retrieved field exactly, but a single
user observation with no retained screenshot/date-time/transaction audit is not
an independent five-card accuracy study. MAPE and ±10% accuracy remain unmeasured.

### TCGdex and Pokémon TCG API actual comparisons

| Target | TCGdex USD `marketPrice` | TCGdex TCGplayer updated | Pokémon TCG API |
|---|---:|---|---|
| Charmander Normal | $0.24 | Oct 14 | HTTP 500 |
| English 151 Charizard Holofoil | $324.63 | Oct 14 | $323.37 generic Holofoil, updated Oct 15 |
| Base Charizard Holofoil | $954.65 | Oct 14 | HTTP 500 |
| Fossil Gengar First Edition Holofoil | $725.00 | Oct 14 | HTTP 500 |
| Japanese Charizard | No TCGplayer price; Cardmarket EUR trend **€372.09**, updated Oct 25 | Missing | No documented Japanese target lookup attempted |

All five TCGdex catalog requests succeeded. These prices have no NM/LP scope and
are not comparable condition benchmarks. EUR stays EUR: no FX conversion. The
successful Pokémon TCG API response also carried Cardmarket data dated November
18, 2025; it is retained as stale context, not a current reference. HTTP 500 is an
observed endpoint failure, not proof that the service always fails or is down.
TCG API/JustTCG/PriceCharting have no fabricated five-card results: all five are
explicitly recorded as gated/not tested in the additional observations.

## Access details and working endpoint examples

**TCGCSV**: [docs](https://tcgcsv.com/docs), [FAQ](https://tcgcsv.com/faq).
Category 3 is Pokémon; category 85 Pokémon Japan. Groups/sets: 23228 Obsidian
Flames, 23237 English 151, 604 Base Set, 630 Fossil, 23599 Japanese 151. Product IDs
are TCGplayer IDs, **not SKU IDs**. Join prices by `(productId, subTypeName)`, not
product ID alone. `lowPrice` excludes shipping but is an asking floor; `midPrice`
is the median listing price; `highPrice` can be inflated price parking;
`marketPrice` is a product benchmark mixing conditions, and can be null.

Working GET examples:

```
https://tcgcsv.com/tcgplayer/categories
https://tcgcsv.com/tcgplayer/3/groups
https://tcgcsv.com/tcgplayer/85/groups
https://tcgcsv.com/tcgplayer/3/604/products
https://tcgcsv.com/tcgplayer/3/604/prices
https://tcgcsv.com/tcgplayer/85/23599/prices
https://tcgcsv.com/last-updated.txt
```

Last build observed: `2026-10-25T20:05:50+0000`. Official guidelines: sync once per
24h, check last-updated before a future sync, custom User-Agent, at least 100ms
between requests, do not re-download immutable archives; >10,000 requests/day can
be banned, excessive rate can incur 10-minute throttling. Exact burst threshold
is unspecified. Server-side downloads are intended; restrictive CORS rules out
live browser pricing fetches. We made one bounded download per needed export,
then did repeated parsing offline. We did not download history archives or build
a cache/scheduler. FAQ permits use/retrieval implicitly and does not require
attribution; that is not proof of all upstream redistribution rights. There is
**no documented condition/SKU endpoint**; none was guessed or probed.

**TCGTracking**: [official Open API docs](https://openapi.tcgtracking.com/),
[parent site](https://tcgtracking.com/). Working examples:

```
https://openapi.tcgtracking.com/v1/categories
https://openapi.tcgtracking.com/v1/3/sets
https://openapi.tcgtracking.com/v1/3/sets/604/cards
https://openapi.tcgtracking.com/v1/3/sets/604/skus
https://openapi.tcgtracking.com/v1/3/sets/630/skus
https://openapi.tcgtracking.com/v1/85/sets/23599/skus
```

The documented SKU shape nests product ID → genuine provider-reported SKU ID →
`cnd`, `var`, `var_a`, `vid`, `lng`, `mkt`, `low`, `hi`, `cnt`. `cnt` is active
listing context, **not sold count or liquidity proof**. EN/JP rows worked.
Documentation also lists other language codes; actual other-language pricing was
not tested. Daily update recommendation is ~9:35 AM ET, with HTTP caching headers.
No numeric request quota, SLA, explicit Open-API commercial agreement or precise
`mkt` calculation was found. Use conservative daily bounded research fetches;
no unlimited-use claim. Research access is explicitly invited, but provider
permission does not establish its upstream sublicensing rights. The parent
shipping-service disclaimer does not supply the missing pricing-data license.

**TCG API**: [cards/conditions docs](https://tcgapi.dev/api/cards/),
[pricing](https://tcgapi.dev/pricing/), [auth](https://tcgapi.dev/authentication/),
[terms](https://tcgapi.dev/legal/terms/), [licensing](https://tcgapi.dev/legal/licensing/).
`GET https://api.tcgapi.dev/v1/games` worked without a key. Create an account at
[signup](https://tcgapi.dev/signup/) for a free key; send `X-API-Key` server-side.
No credentials were requested since a keyless working alternative was found.
Free offers 100/day and seven-day history; history retention increases by plan.
`/v1/cards/tcgplayer/{productId}` supplies product mapping.
`/v1/cards/{id}/prices/conditions` requires **Pro+**, starting $49.99/month.
Its `low_price` is a condition listing floor; `lowest_with_shipping` and
`median_with_shipping` include shipping. **No condition market-price field is
shown in that schema.** This endpoint cannot be treated as equivalent to TCGplayer
condition Market, and shipping-inclusive medians must not enter CardScan's
item-only market price. Free pricing access was not tested without a key.
Top-game daily refresh, per-price market-as-of fields and paid eBay summaries are
promising but untested. Paid x402 access was not used; a blanket “from $0.005”
advertisement does not establish condition-endpoint access. Limits reset at UTC
midnight; HTTP 429/header limits should stop callers rather than trigger loops.

**JustTCG**: [quickstart](https://justtcg.com/docs/quickstart),
[variant schema](https://justtcg.com/docs/schema/variant),
[cards endpoint](https://justtcg.com/docs/api/cards),
[rate limits](https://justtcg.com/docs/rate-limits),
[pricing](https://justtcg.com/pricing), [terms](https://justtcg.com/terms).
Free signup/key requires no credit card. Documented example lookup:
`GET https://api.justtcg.com/v1/cards?tcgplayerId=42382`, `x-api-key` header.
Keep a future `JUSTTCG_API_KEY` in backend/GitHub Actions secrets; never chat,
repository, URL query strings or browser code. No account/key created/read here.
Price is a provider USD benchmark per condition/printing, with SKU ID/language
and observation timestamp; `priceStatus=expired`/`unpriced` must not become a
current quote, and `lastKnownPrice` is historical. Missing v1 language is documented
as English; a future adapter must record that **schema default** explicitly, not
pretend it was observed. Current terms (Oct 14) grant paid app use/analytics/data
combination, with restrictions on raw redistribution and competing pricing feeds;
free use is personal/noncommercial. Source blended methodology means it is an
alternative benchmark, not guaranteed reproduction of TCGplayer's figure.

**TCGdex**: [API/prices](https://tcgdex.dev/markets-prices),
[FAQ](https://tcgdex.dev/faq), [metadata source](https://github.com/tcgdex/cards-database).
Keyless endpoint `https://api.tcgdex.net/v2/en/cards/sv03.5-199`; Japanese
`https://api.tcgdex.net/v2/ja/cards/sv2a-201`. No published hard rate limit;
considerate downloads advised. FAQ explicitly acknowledges some wrong external
marketplace-ID mappings and upcoming variant-level improvements. Metadata/code
licensing is not a license to all third-party prices/images. Existing verifier
is preserved; these results do not bypass it.

**Pokémon TCG API**: [auth](https://docs.pokemontcg.io/getting-started/authentication/),
[limits](https://docs.pokemontcg.io/getting-started/rate-limits/),
[card schema](https://docs.pokemontcg.io/api-reference/cards/card-object/).
`https://api.pokemontcg.io/v2/cards/sv3pt5-199` worked. Keyless documented allowance
is 1,000/day, 30/min; free key defaults to 20,000/day. This is not
`pokemontcgapi.com`, a different service. No NM/LP breakdown in the reviewed schema,
no freshness guarantee inferred from daily marketing elsewhere. Product metadata
`legalities.unlimited` concerns play legality, not Unlimited printing.

**PriceCharting**: [API docs](https://www.pricecharting.com/api-documentation),
[current subscription page](https://www.pricecharting.com/pricecharting-pro).
Legendary $49/month includes pricing API; Collector $6/month does not. Prices use
integer pennies and generic ungraded/graded buckets, not the five raw conditions.
API docs recommend at most one price request per second; avoid downloading the
whole price database per item. No subscription/token/free pricing API test made.
Marketplace offer APIs/condition identifiers are not NM-specific market benchmarks.

## TCGplayer consumer website

The product page inspected through ordinary research page access returned only a
JavaScript-required shell; no condition-price or sales-history payload appeared
in that initial content. This establishes dynamic rendering for this retrieval,
not that every browser response always omits all prices. Search queries did not
produce a substantiated indexed LP $527.70 snapshot. This is not proof that no
search engine can ever index such data. Prior retained work observed an internal
sales-history request returning 403; it was not retried or bypassed.

The [official SKU API docs](https://docs.tcgplayer.com/reference/pricing_getproductconditionprices-1)
do describe equivalent SKU `marketPrice` alongside separate listing/shipping
fields, but require approved developer access; we did not apply. Seller CSV tools
can expose SKU market fields to authorized sellers, which does not authorize
arbitrary consumer-site extraction. Public sales history represents TCGplayer's
own marketplace sales; it is not established as an eBay transaction feed.

[TCGplayer's published API terms](https://help.tcgplayer.com/hc/en-us/articles/360061115874-TCGplayer-API-Terms-Conditions)
restrict automated site collection and upstream automated-data redistribution.
Personal use does not create an express scraping exception. An internal endpoint
is not a documented authorized public API; robots visibility is not a license.
No website scraper was built. An API vendor's invitation/license and its upstream
authority are separate questions; this report does not assert that TCGTracking,
TCGCSV or any other vendor has TCGplayer approval. Commercial diligence remains
necessary even when our bounded personal research requests are invited.

## Implementation and repeatable use

`cardscan/structured_prices.py` adds the separate `StructuredPriceProvider`
contract, `CatalogBinding`, `PriceObservation`, bounded public export transport,
and TCGCSV/TCGTracking adapters. It reuses the existing `SourceDocument`,
`FieldEvidence` and redirect refusal machinery. Deterministic joins, reviewed
variant/language maps, full-number matching, Decimal parsing and per-field
provenance are explicit. A reference is never converted to a `Sale`.

`experiments/structured-prices/targets.json` contains the exact five manifest
identities and reviewed source catalog bindings. No fuzzy matching or denominator
completion. `cardscan/structured_price_experiment.py` requires either retained
original documents or explicit `--live`; it refuses output overwrite, records
errors separately, spaces live requests, and refuses duplicate endpoint requests
within an invocation. It is a small research harness, **not** a refresh scheduler,
a cache or a full inventory database. These five bindings use distinct sets; a
future larger manifest must group cases by set to avoid re-downloading endpoints.

Offline reproduction in this execution workspace:

```bash
python -m cardscan.structured_price_experiment \
  --documents local-evidence/provider-investigation \
  --output local-evidence/structured-prices-replay.json
```

A new permitted daily retrieval (20 free GETs, no credentials, no model calls):

```bash
python -m cardscan.structured_price_experiment --live \
  --output local-evidence/structured-prices-new-observation.json
```

Do not repeat TCGCSV downloads on the same day. Reanalysis uses original local
responses; repo audit is minimal evidence, not a substitute full-price feed.
The CLI writes new evidence only; retained original research responses stay
unchanged. If an endpoint fails, the harness preserves a retrieval failure and
continues other providers; no retries or substituted asking prices.

Validation: baseline **188** tests passed; final **204** tests passed (16 new
test methods, many table-driven cases). Compile checks and diff whitespace checks
passed. Tests cover precise decimals, full numbers, wrong card/set/language/
condition/finish/edition, graded exclusion, duplicate products/SKUs, missing prices,
no listing-price substitution, timestamps/inversions, provenance/permission gates,
network failures/429, redirects/HTML/size/JSON guards, source-hash replay and actual
minimal observation regression. Tests establish software behavior, not market
accuracy. No existing AI prompt, strict sales engine, budget safeguards, source
verifier or previous evidence was changed. API cost of this investigation: **$0**.

## Recommended architecture and next milestone

Use four separate contracts: catalog metadata/crosswalk; generic baseline
references; condition/printing/language SKU references; and the existing AI
research fallback. Shared identity includes game, source product, set, full number,
language, edition, finish and grading. Observation includes exact source SKU ID,
metric type, condition scope, currency/basis, update/retrieval times, provenance,
missing fields and provider errors. Other games can supply their own reviewed
catalog/variant maps through the same interface. Do not combine product guides,
condition market benchmarks, asks and sales into one median.

For this personal prototype: TCGCSV's catalog/daily baseline + TCGTracking's
condition references is demonstrably workable; use TCGdex for multilingual
metadata with reviewed crosswalks. Catalog identity must remain independently
checked, especially error variants and vintage editions. Preserve source-specific
values and conflicts. Existing strict sales logic remains available for genuinely
verified transactions; AI is labeled fallback, not a substitute structured quote.

**The next milestone is an independent SKU validation pass**, starting with these
five returned SKU IDs and condition inversions: compare dated source-page/manual
observations to the retrieved references, establish shipping/tax and `mkt`
methodology, and measure actual error/coverage in the existing benchmark workflow.
Confirm TCGTracking's upstream and app-use license before commercial reliance.
If that remains unresolved, evaluate JustTCG with its free personal key, then its
explicit $19/month commercial tier only after separate payment authorization.
No additional AI spending is needed to do this first validation.
