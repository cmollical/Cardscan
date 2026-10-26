# Local Pokémon pricing backend and mandatory history

Implemented October 26, 2026. Personal research only; commercial/upstream
redistribution rights remain unresolved. No paid calls, OpenAI Web Search,
TCGplayer scraping or provider requests were made for this assignment. Existing
provider responses were replayed. Existing AI experiments, strict sales engine,
source-verification adapters and original evidence remain unchanged.

## Actual validation

Replayed **20 retained full provider exports** covering five sets: **1,209
products**, **7,625 SKUs**, **9,217 price observations**. This is a working local
SQLite database, not a complete Pokémon catalog. The execution workspace database
is `local-evidence/pokemon-pricing-complete.sqlite`; the default
`local-evidence/pricing.sqlite` also contains a backup of this validated database.
Databases/full responses stay ignored by git. A portable minimum real-evidence
seed for five products is committed for a new checkout.

| Provider SKU ID | Requested target | Saved USD market reference | Local SKU lookup |
|---|---|---:|---|
| 7335315 | Charmander, Obsidian Flames 26/197, EN non-holo NM | 0.32 | exact_match |
| 7436747 | Charizard ex, English 151 199/165, holo NM | 294.42 | exact_match |
| 2999653 | Charizard, Base Set 4/102, EN Unlimited holo LP | 527.70 | exact_match |
| 2995236 | Gengar, Fossil 5/62, EN First Edition holo LP | 458.05 | exact_match |
| 8115821 | Charizard ex, Japanese 151 201/165, holo NM | 388.35 | exact_match |

These are **dated provider-reported references**, not independently authenticated
transactions/current quotes or proof of broad accuracy. Decimal strings preserve
the source amount; `527.7` and `527.70` have equal value. Shipping/tax basis remains
unconfirmed and neither is added. Every response has `approved_inventory_price=false`.

An exact **SKU ID** unambiguously retrieves that reference even if some printing
metadata is missing. It does not establish those missing facts. Three modern
cards have unknown source edition: a full-attribute request requiring `standard`
returns `ambiguous_match`, with the reference exposed only inside a clearly
identified candidate. It does not assert a confirmed standard edition. Vintage
Unlimited/First Edition is explicit in the saved source. Raw/graded is classified
as raw-reference scope using the existing adapter contract/condition scale, not
an observation of the user's physical card or a fabricated source boolean.

The full catalog can contain multiple products with the same set/collector number
(for example normal versus error Charizard). The lookup keeps those ambiguous.
Pass the optional **TCGplayer product ID** after exact identification to isolate a
specific product; never choose one by similar name. Missing edition or multiple
providers are not silently resolved. Known mismatched language/condition/edition/
finish is excluded; unknown relevant attributes remain candidates for review.

[Five-card output](../research/results/local-pricing-five-card-validation-2026-10-26.json)
records exact SKU output and separate attribute-lookup outcomes.
A real uvicorn loopback request also passed: [HTTP smoke result](../research/results/local-pricing-http-smoke-2026-10-26.json).
No hosted service was deployed.

## Local setup

Python 3.12 was used. From the repository root:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-local.txt -r requirements-history.txt
python -m cardscan.local_pricing.cli init
python -m cardscan.local_pricing.cli seed
uvicorn cardscan.local_pricing.api:app --host 127.0.0.1 --port 8000
```

Seed imports the committed minimum original-response excerpts, **5 products and
35 variants**, including unpriced/mismatched-condition rows. It does not generate
synthetic market values or re-download data. Repeated imports are idempotent.
Use `--db PATH` before the CLI subcommand and set `CARDSCAN_PRICING_DB=PATH` for the
API when selecting another database. The API never creates/migrates a database.

In this execution workspace, the complete retained responses can be replayed:

```bash
python -m cardscan.local_pricing.cli --db local-evidence/full-pricing.sqlite replay \
  --documents local-evidence/provider-investigation
```

This command verifies original response hashes and imports the full five set
exports offline. Full exports are not redistributed in git. The portable excerpts
retain original source hashes, retrieval timestamps and original catalog indices;
new hashes identify the excerpts themselves. JSON pointers in the seed refer to
excerpts, not falsely to byte-identical full original documents.

## Schema and migrations

`cardscan/local_pricing/schema.sql` creates schema version 1. Numbered migrations
002/003 add quality/sync controls and mandatory append-only history. Migration
steps run transactionally and reject a database newer than supported version 3.
Existing observations receive snapshot metadata before append-only triggers are
installed. Foreign keys and WAL are enabled. API connections are read-only and
close after each request; sync writes use atomic provider/set transactions.

| Tables | Purpose / important constraints |
|---|---|
| games, provider_categories | Internal game identity, exact provider category mappings; currently Pokémon categories 3/85 |
| sets, set_mappings, set_aliases | Internal set, provider category/group IDs, release/catalog timestamps; literal reviewed aliases only |
| products, product_sources | Exact TCGplayer product ID joins, full collector number, catalog metadata and document pointers; no name-only joins |
| skus | Separate internal/provider SKU IDs, product FK, condition/language/edition/finish/raw scope, source row and completeness/provenance; provider+SKU unique |
| observations | Append-only SKU **or** generic product benchmark; decimal TEXT, provider, currency basis, metric type, source/retrieval/snapshot times, subtype, evidence, uncertainties |
| documents | Source URL, exact retained bytes, retained/original hashes, original-versus-excerpt marker, retrieval/check times; full originals remain local |
| endpoints, sync_state | Persisted request cooldowns, headers, source version, attempts/success/errors/request counts, retry eligibility, future priority/refresh/event fields |
| quality_issues | Exact-ID join gaps, including SKU products absent from the cards-only catalog; skipped pricing remains flagged |
| archive_imports, archive_members | Resumable immutable archive/member ingestion state and hashes |
| historical_unmatched | Generic dated archive rows whose exact product/set is absent from current catalog, retained for later review/resolution |

Product IDs are not SKU IDs. Observations have a trigger rejecting SKU/product
mismatches. Uniqueness prevents duplicate provider SKUs and repeat import records.
Indexes cover provider SKU identity, product+set+number, condition/printing
selection, and dated SKU/product-subtype history. No binary-float pricing math.

The batch importers reuse the existing reviewed variant/language maps, exact
number normalization and decimal validation from `structured_prices.py`. The
original single-target proof-of-concept adapters remain usable and unchanged.
The database never converts a market reference into a `Sale` object.

## Mandatory append-only history

History is **mandatory for both providers**, including unchanged daily prices:

- `source_updated_at`: provider export update, nullable; not a last-sale date.
- `retrieved_at`: timestamp of the actual source response retained/reused.
- `snapshot_date`: UTC daily snapshot date, or the original archive date.
- `captured_at`: when the observation/snapshot was ingested.
- `capture_kind`: original import, daily snapshot or historical archive.

The same cached/revalidated export can yield a new daily snapshot with an
unchanged price and unchanged retrieval/provider timestamps. It is not relabeled
as a new transaction or a freshly observed individual price. Same-source same-day
replay is idempotent; a genuinely changed source response is retained separately.
Snapshot identity uses the source version and exact SKU/product-subtype identity,
not the excerpt's row position.

Database triggers refuse normal `UPDATE` and `DELETE` of historical observations.
Missing latest prices are stored as NULL, never zero; prior prices remain visible
in history but are not silently returned as the current available quote. Removed
SKU rows in complete original exports become inactive (partial seed excerpts never deactivate other SKUs), with old history retained. Provider failure leaves
previously committed data intact. Generic histories always have `sku_id=NULL`
and an explicit subtype; they cannot enter condition-SKU lookup/history.

7/30/90-day comparisons are implemented for an exact series using **actual exact
snapshot dates**, with Decimal percentage change. Missing dates/values return
`insufficient_history`; no interpolation, forecast or price prediction. A
comparison is a provider-reference movement, not an accuracy/confidence measure.
Historical imports cannot displace newer snapshots merely because they were
retrieved later.

## Read-only HTTP API

Interactive OpenAPI documentation is at `/docs`; JSON schema is `/openapi.json`.
No authentication complexity or sync/admin mutation endpoints are exposed.
Bind to loopback; this is not hardened for public deployment.

| Endpoint | Behavior |
|---|---|
| GET /health | Database/schema health; 503 `database_unavailable` if unavailable |
| GET /cards/search?q=Charizard&limit=25&offset=0 | Paginated catalog discovery, maximum 100 rows; substring search is not identity matching |
| GET /cards/{card_id} | Catalog identity, variants and separately labeled generic references |
| GET /prices/lookup | Structured exact identity lookup, optional exact TCGplayer product ID |
| GET /prices/sku/{provider_sku_id} | Explicit provider SKU reference retrieval; incomplete attributes remain marked |
| GET /prices/history/{internal_sku_id} | Paginated condition-specific stored history, max 500 rows |
| GET /prices/product-history/{card_id}?subtype=Holofoil | Separate generic product/subtype history |
| GET /prices/comparisons/{internal_sku_id} | Exact-date 7/30/90-day SKU comparisons |
| GET /prices/product-comparisons/{card_id}?subtype=Holofoil | Separate generic exact-date comparisons |
| GET /sync/status | Per-provider/set success, failures, retry eligibility and freshness context |

Example price request:

```text
/prices/lookup?game=pokemon&set_name=base%20set&number=4%2F102&language=english&edition=unlimited&finish=holo&condition=LP&graded=false&tcgplayer_product_id=42382
```

Statuses are `exact_match`, `ambiguous_match`, `price_unavailable`, `stale_price`,
`not_found`. A stale reference remains explicitly labeled, with its value/times;
an ambiguous result has no top-level accepted price. Default freshness window is
48 hours from set-export update, falling back to retrieval when unavailable;
individual price age remains unknown. Fresh data does not imply verified accuracy.

Invalid inputs return 422, unknown internal card/SKU IDs return clear 404 codes,
and database failures return JSON 503. Normal lookups make **zero external calls**.
Currency convention, shipping/tax uncertainty, source provenance, identity
completeness and inversion flags remain visible. Active listing counts are never
converted into sold counts or liquidity scores.

## Controlled synchronization

```bash
# Five researched sets, bounded request budget, no automatic retries:
python -m cardscan.local_pricing.cli sync --execute --max-requests 40

# Explicit set/category (repeat --set to select more):
python -m cardscan.local_pricing.cli sync --execute --set 3:604 --set 85:23599

# Bounded incremental catalog expansion; least recently synced sets first:
python -m cardscan.local_pricing.cli sync --execute --all-pokemon --max-sets 20 --max-requests 100

python -m cardscan.local_pricing.cli status
```

No live sync was executed during this assignment. Seeded excerpts register known
collection times but are **not** treated as complete cached set exports: a live
sync within their 24-hour cooldown can report unavailable while preserving local
prices. Original-response replay registers the complete export for reuse.

A file lock rejects overlapping jobs. Scopes are grouped/deduplicated by set.
Endpoint attempts are persisted **before** requests; restarts cannot reset the
24-hour cooldown. Custom User-Agent, 150ms spacing, bounded timeout/body size,
endpoint allowlist, redirect/HTML refusal, conditional ETag/Last-Modified requests,
and bounded request count are enforced. An unchanged TCGCSV global build marker
allows reuse of retained exports; same-day data are never polled repeatedly.
429 honors Retry-After if longer than the normal daily cooldown. Failed endpoints
are not automatically retried. Partial provider/set failures are recorded.

Future priority/refresh/event columns accommodate new-set/volatility/reprint
policies, but no detection, forecasting or recurring hosted scheduler is built.
Set-level export granularity remains the refresh unit.

## 365-day historical backfill: plan before downloads

First-party references: [TCGCSV FAQ](https://tcgcsv.com/faq),
[usage/docs](https://tcgcsv.com/docs). Reviewed October 26 retained documentation
permits intended export/archive downloads, describes daily compressed archives
from **2024-02-08**, and emphasizes downloading immutable archives **once**. It
describes archives around **2–4 MB each**, across all games.

For the last 365 completed days (2025-10-26 through 2026-10-25):

- **Estimated download:** 730 MB–1.46 GB decimal, not measured by downloading a
  year. No documented Pokémon-only archive URL or server-side selective download.
- **Estimated history rows:** approximately 23.2–46.4 million using today's 63,623
  EN+Japan catalog products and an assumed 1–2 generic subtypes/product. Historical
  catalog size varies; this is a capacity estimate, not a counted archive total.
- **Estimated SQLite observations/index storage:** roughly 24–95 GB assuming
  1–2 KiB/observation. Including retained price-entry evidence, archive files and
  WAL/headroom, plan for **roughly 40–150 GB free disk**, then refine from one real
  archive. Compressed download size is not a database-size estimate.
- **Processing time:** actual provider PPMd decoding/ingestion is **unmeasured**.
  Allow hours, potentially a day; benchmark one actual archive before authorizing
  bulk work. Formula: 365 × (download time + PPMd decode time + inserts). The
  current snapshot's full catalog import time is not a PPMd backfill benchmark.

The machine-readable [capacity plan](../research/results/history-backfill-plan-2026-10-26.json)
contains assumptions and bounds. **No real historical archive was downloaded**.
A locally generated PPMd archive tested the extraction/import mechanism only; its
synthetic prices are not pricing evidence.

Archive URL pattern:

```text
https://tcgcsv.com/archive/tcgplayer/prices-YYYY-MM-DD.ppmd.7z
```

`py7zr` lists members, validates paths/size bounds, then extracts only
`YYYY-MM-DD/3/{group}/prices` and `YYYY-MM-DD/85/{group}/prices`. Other categories
are not extracted/stored. Solid compression may still require decoding other
entries, so selective extraction does not promise proportional CPU savings.
Links, traversal paths, unexpected formats and excessive sizes are refused.

```bash
# Safe planning only; no HTTP:
python -m cardscan.local_pricing.backfill plan --days 365

# Import one already-downloaded archive; no download unless --download is present:
python -m cardscan.local_pricing.backfill run --execute \
  --start 2026-10-25 --end 2026-10-25 \
  --archives local-evidence/tcgcsv-archives --max-archives 1
```

A later explicitly authorized sample may add `--download`. **A bulk year download
has not been authorized or initiated.** The command defaults to one archive,
uses only completed historical dates, retains immutable completed archive files,
hashes them, writes downloads atomically, and never re-downloads existing ones.
Failed attempts cool down until the next day; archived member commits make
restart/resume idempotent. Existing cached hashes are checked, including imports
without download. Normal history is never overwritten/deleted.

Exact current catalog IDs resolve historical rows; unknown/deleted products or
changed groups remain in `historical_unmatched` with original date/source/price
for review, not joined by names. Those staged rows are not yet queryable as known
card histories; resolving missing historical catalog mappings is additional work.
Every imported archive price is a **generic product/subtype reference with unknown
condition**. A dated filename is a snapshot date, not a provider publication time
or a transaction date.

Reviewed [TCGTracking documentation](https://openapi.tcgtracking.com/) lists current
set/catalog/pricing/SKU exports and daily updates, but **no documented historical
SKU-price endpoint was found**. No undocumented route was probed. Condition-level
history therefore accumulates from CardScan's own dated snapshots; TCGCSV archives
cannot backfill NM/LP/MP/HP/DMG history.

## Performance and tests

[Measured benchmark](../research/results/local-pricing-performance-2026-10-26.json),
Linux/Python 3.12.14, full five-set dataset, warm OS cache; each lookup includes
opening/closing a read-only SQLite connection, queries, decoding and freshness.
Camera/AI/HTTP latency is excluded.

| Workload | Correct | Median ms | P95 ms | Maximum ms |
|---|---:|---:|---:|---:|
| 100 sequential SKU lookups | 100/100 | 0.540 | 0.727 | 1.855 |
| 1,000 sequential SKU lookups | 1,000/1,000 | 0.530 | 0.854 | 7.721 |
| 1,000 same-card lookups | 1,000/1,000 | 0.517 | 0.784 | 2.834 |
| 100 missing-card lookups | 100/100 | 0.379 | 0.556 | 0.659 |
| 100 ambiguous-variant lookups | 100/100 | 0.756 | 1.155 | 1.835 |
| 100 full-identity + product-ID lookups | 100/100 | 0.658 | 0.989 | 2.896 |

Initial full import: **1.364 seconds**. SQLite file after WAL checkpoint:
**20,561,920 bytes (~19.6 MiB)**. These measured results beat 100ms here; they are
not a guarantee for a different machine or a 30-million-row history database.

```bash
# Portable five-product seed benchmark:
python -m cardscan.local_pricing.benchmark --output local-evidence/benchmark.json
# Repeat full retained-export benchmark where those local originals are available:
python -m cardscan.local_pricing.benchmark \
  --documents local-evidence/provider-investigation \
  --output local-evidence/full-benchmark.json
# Routine tests have no API charges:
pip install -r requirements-ai.txt -r requirements-local.txt -r requirements-history.txt
python -m unittest discover -s tests -q
```

Baseline: **204 tests**. Final: **239 tests passed**. New tests cover migration,
idempotency, exact identity isolation, missing edition, source hashes, duplicate/
wrong SKU mapping, NULL/negative/currency/date handling, actual API routes and
validation, sync cooldown/304/failure recovery/locks, unchanged daily history,
append-only triggers, generic separation, exact-date comparisons, archive resume,
PPMd category filtering, unresolved historical joins and benchmark correctness.
Compile/whitespace checks pass. A separate credential-free GitHub Actions workflow runs the full offline suite and portable benchmark; existing paid-pilot workflows/authorization files are unchanged. Mocked/synthetic tests are not pricing-accuracy
measurements. The installed newer Starlette emits an httpx TestClient deprecation
warning; tests and the actual uvicorn HTTP smoke both succeed.

## Next milestone

Independently validate the five structured SKU references and clarify benchmark
shipping/tax/methodology plus TCGTracking licensing. Then authorize **one real
historical archive** to measure actual extracted rows, processing time and disk
cost before any 365-day generic backfill. Continue collecting condition snapshots
locally at permitted daily cadence. No new AI spending or PWA work is needed.

Current follow-up: [bounded expansion, schema 4, candidate API improvements and archive withdrawal](backend-readiness-2026-10-26.md). The archive-format description above records prior documentation; actual October 26 download access is blocked.
