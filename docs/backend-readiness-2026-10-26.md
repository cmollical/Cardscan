# Historical access, bounded catalog expansion and backend readiness

Completed October 26, 2026, starting from `167b25d`. The catalog expansion and
backend work succeeded. **Real historical archive ingestion could not be
validated: TCGCSV has temporarily withdrawn the archive download.** This is a
confirmed provider response, not a resource-limit guess. No alternate dates,
mirrors, undocumented routes or access-control workarounds were tried afterward.
No full-year/full catalog download, paid API, OpenAI Web Search, scheduler, PWA,
camera or identification system was executed/built. Personal research only;
commercial/upstream rights remain unresolved.

## 1. Actual historical archive test

The [documented FAQ](https://tcgcsv.com/faq) and [usage guidelines](https://tcgcsv.com/docs)
were reviewed from the original October 26 retained source responses before the
attempt. They describe immutable daily `prices-YYYY-MM-DD.ppmd.7z` files, custom
User-Agent, conservative request spacing and downloading each archive only once.
No `.7z` historical archive already existed locally. Free workspace disk was
**31,897,780,224 bytes (~29.7 GiB)**.

Selected representative date: **2026-09-26**, one month before the current
snapshot. URL:

```
https://tcgcsv.com/archive/tcgplayer/prices-2026-09-26.ppmd.7z
```

HEAD returned HTTP 403, so advertised size could not be obtained. Because the
published download method is GET, exactly one ordinary bounded GET was attempted
for the **same URL**, with an identifiable custom User-Agent and no authentication,
challenge processing or retries. It also returned HTTP 403 with a plain-text
operational notice. The provider says the archive was temporarily removed due to
server costs/moderation burden and awaits clarification from TCGplayer plus
reliable cost coverage; it recommends individual category/group/price exports for
current daily pricing instead. This is not evidence of an anti-bot challenge or
proof that an API key would restore access.

[Recorded response/preflight](../research/results/backend-readiness-2026-10-26/archive-access.json).
The response prefix is retained as minimal operational evidence, not a successful
archive. The GET attempt took **0.253 seconds**. It downloaded **zero archives**.

| Requested real archive metric | Actual outcome |
|---|---|
| Compressed size / total uncompressed size | Not measurable; access withdrawn |
| Pokémon extracted bytes / English / Japanese records | Unmeasured; no archive contents received |
| Parsing / import duration | Unmeasured; no historical import performed |
| Peak temporary extraction disk / import memory | Unmeasured; no historical extraction/import |
| Archive-induced SQLite growth / historical rows imported | **0 bytes / 0 rows**, because no archive was ingested |
| Import same real archive twice | Not possible; no real archive available |

Do not interpret these unavailable metrics as a successful zero-size archive.
The real-archive portion remains **blocked**, not complete. Available workspace disk is sufficient for this bounded snapshot expansion but below the previous minimum full-year planning allowance.

## 2. Selective streaming implementation and integrity

`archive_stream.py` implements per-member streaming with py7zr **>=1.1.4**.
The compressed 7z file is downloaded incrementally to an immutable local file:
7z requires seekable input, so direct one-pass HTTP decoding is not promised.
Selected members stream through bounded spools into parsing/SQLite ingestion;
unrelated game data is **never materialized to disk**. A member larger than
1 MB may spill to a temporary spool, capped at 5 MB per member. Aggregate selected
size/path/member-count bounds remain enforced. No whole archive `read_bytes()`
is needed for hashing/header validation. Solid PPMd blocks may still require CPU
decoding of unselected data.

Only exact paths `YYYY-MM-DD/3/{group}/prices` and
`YYYY-MM-DD/85/{group}/prices` are accepted. The library's successful-member
completion hook runs after CRC verification. Failed CRC/decompression must not
commit that member. Successfully committed earlier members remain resumable;
archive/member hashes and idempotent fingerprints prevent duplicate history.
Temporary spools are closed after success or failure.

Automated tests use locally generated **synthetic** PPMd archives with English,
Japanese and unrelated-game members. They verify selection, no unrelated files,
CRC failure rejection, original snapshot dates, distinct retrieval dates, precise
decimals, generic/SKU separation and second-import idempotency. These prove
software behavior, **not actual TCGCSV archive ingestion or pricing accuracy**.

The database's original **9,217 observations are byte-identical** after expansion,
migration and cached re-import. Append-only triggers remain active. Historical
query endpoints now accept `order=asc|desc`; descending remains the compatible
default. No older historical snapshot can replace a newer current snapshot by
virtue of being retrieved later.

## 3. Backfill projections: measured versus assumed

There is **no usable real sample** from which to calculate grounded historical
projections. The prior documentation's 2–4 MB/day figures can still provide
explicitly unvalidated planning bounds:

| Days | Compressed planning bounds | Prior linear disk allowance, unvalidated | Measured processing / peak memory |
|---:|---:|---:|---|
| 30 | 60–120 MB | ~3.3–12.3 GB | Unavailable |
| 90 | 180–360 MB | ~9.9–37.0 GB | Unavailable |
| 180 | 360–720 MB | ~19.7–74.0 GB | Unavailable |
| 365 | 730 MB–1.46 GB | ~40–150 GB | Unavailable |

Disk allowances merely scale the previous conservative estimate; archive entry
counts, source payload/index cost and SQLite/WAL growth are **not measured**.
Peak extraction memory and temporary disk cannot responsibly be projected from a
403 notice or a tiny synthetic archive. Current-catalog import timings below are
not historical PPMd benchmarks.

[Machine-readable projection limitations](../research/results/backend-readiness-2026-10-26/history-projections.json).
Full-year backfill is **not currently actionable** while downloads are withdrawn.
After provider restoration or availability of an authorized retained original,
validate one real archive before authorizing any multi-archive download. Meanwhile,
retain CardScan's own permitted daily generic and condition snapshots. TCGCSV
archives would only backfill **generic** product/subtype prices, never NM/LP data.
No historical TCGTracking endpoint was documented in the previously reviewed
current-export documentation, and none was invented/probed here.

## 4. Metadata-only catalog discovery

Reused already-downloaded same-day TCGCSV/TCGTracking metadata and fetched only
the previously uncached documented Japanese TCGTracking set index. No existing
TCGCSV export was downloaded twice within 24 hours.

| Catalog category | TCGCSV sets | TCGTracking sets | Shared exact set IDs | TT-reported products | TT-reported SKUs |
|---|---:|---:|---:|---:|---:|
| English Pokémon (3) | 220 | 287 | 220 | 32,882 | 223,155 |
| Japanese Pokémon (85) | 461 | 461 | 461 | 30,741 | 182,508 |
| Combined | 681 | 748 | 681 | 63,623 | 405,663 |

Counts are metadata reports, not independently counted downloaded full-catalog
products. TCGTracking has 67 English set IDs absent from TCGCSV's index; their
availability is preserved rather than pretending both providers cover all sets.
Names are not fuzzy-joined across providers or languages.

A complete initial union would require **2,858 set-export requests** plus about
five metadata requests: 681 shared sets × four exports + 67 TT-only sets × two.
TCGCSV's portion is approximately 1,365 calls including metadata, below its
published 10,000/day ceiling, but daily cadence, bandwidth and throttling still
matter. No numeric TCGTracking quota was found; lack of one does not mean unlimited.

From the actual non-random ten-set sample, rough **current snapshot** projections
are ~215 MB of accepted export bodies, ~1.03 GB SQLite storage and ~23 minutes for
full coverage. These extrapolate observed bytes per added product and elapsed
seconds per request; they are **not full-catalog measurements or guarantees**.
They exclude accumulated daily history and do not establish pricing coverage for
every reported SKU. The 150ms spacing alone implies ~7.1 minutes for 2,858 requests.
Bounded resumable batches remain preferable to a single large run.

[Discovery/projection evidence](../research/results/backend-readiness-2026-10-26/catalog-discovery.json).

## 5. Controlled ten-set expansion

Exactly ten additional set scopes were selected, five English and five Japanese,
covering vintage and modern releases. No other price/catalog set was fetched.

| Category | Set ID | Set | TCGCSV import | TCGTracking import |
|---|---:|---|---|---|
| English | 635 | Jungle | Success | Success |
| English | 1373 | Team Rocket | Success | Success |
| English | 1396 | Neo Genesis | Success | Success |
| English | 2848 | Evolving Skies | Success | Success |
| English | 23120 | Paldea Evolved | Success | Success |
| Japanese | 23601 | Shiny Treasure ex | Success | Success |
| Japanese | 23645 | VSTAR Universe | Transport validation failed | Success |
| Japanese | 23722 | Pokémon Jungle | Success | Success |
| Japanese | 23723 | Mystery of the Fossils | Transport validation failed | Success |
| Japanese | 23909 | Terastal Fest ex | Success | Success |

**18/20 provider-set imports succeeded**, including TCGTracking for all ten.
The previous transport retained only `ValueError` for two failed TCGCSV requests;
the exact failed validation stage/body was not preserved, so its cause is **not
invented**. No immediate retry was made. Diagnostics now retain safe validation
reasons for future failures, without processing challenge pages.

Measured initial expansion:

- **38 export requests**, plus **one** new metadata request for discovery.
- **7,754,367 bytes** of accepted export response bodies. Failed/HTTP-header bytes
  are not included in that measurement.
- **18.657 seconds** elapsed for exports/imports combined; 2,300 added products,
  about **123 added products/second** end-to-end. This is not pure SQLite throughput.
- Process peak RSS **58,180 KiB (~56.8 MiB)** for the expansion worker.
- Final **15 sets / 3,509 products / 21,735 SKUs / 25,812 observations**.
- **57,970,688 bytes (~55.3 MiB)** SQLite file after schema 4 and WAL checkpoint,
  versus baseline 20,561,920 bytes. Prior databases/evidence were retained.

A resume invocation skipped the 18 successful provider/set checkpoints and
reported the two provider failures still in cooldown: **zero HTTP requests and
zero new observations**. An offline replay of 28 complete cached provider/set
pairs likewise kept all observations unchanged.

[Actual expansion](../research/results/backend-readiness-2026-10-26/expansion.json),
[resume](../research/results/backend-readiness-2026-10-26/resume.json),
[integrity](../research/results/backend-readiness-2026-10-26/integrity.json),
[source hashes](../research/results/backend-readiness-2026-10-26/source-manifest.json).
Full original exports remain local in SQLite documents, not republished as a feed.

Data coverage is not universal pricing coverage: **8,172 of 21,735 SKU references
have no reported market price**; **27 of 4,077 generic observations** are NULL.
No missing value became zero or another condition's price. All SKU conditions and
languages were explicitly mapped, but **2,520 finishes and 18,525 editions remain
unknown**. Most unknown editions are modern source rows that do not state one.

Migration 004 records an audit of **2,520 literal edition enrichments**: raw
`1st Edition`/`Unlimited` labels previously retained but not normalized now establish
edition. **Finish stays unknown** when the label does not establish it. This
changes no price observations and does not infer edition from holofoil status.
Those vintage variants still require review for finish-specific requests.

## 6. Discovery, planning, synchronization and resume commands

Initialize/migrate with the existing CLI. Optional dependencies remain
`requirements-local.txt`, `requirements-history.txt`, plus `requirements-ai.txt`
for the complete legacy test suite. No API key is needed for these providers.
The expanded execution workspace database is
`local-evidence/backend-expansion/pricing.sqlite`. Select it with `--db` or
`CARDSCAN_PRICING_DB` for the API; the original five-set database is preserved.

```bash
# Metadata only. Cached URLs respect the persisted 24-hour cooldown:
python -m cardscan.local_pricing.cli --db local-evidence/pricing.sqlite \
  discover --fetch-metadata --max-requests 4

# Entire documented scope planning ONLY; no imports or network:
python -m cardscan.local_pricing.cli --db local-evidence/pricing.sqlite \
  sync --all-pokemon --max-sets 748 --max-requests 1000 --dry-run

# A separately authorized bounded batch, not executed by the dry-run command:
python -m cardscan.local_pricing.cli --db local-evidence/pricing.sqlite \
  sync --all-pokemon --max-sets 20 --max-requests 100 --execute --resume --progress

# Explicit small selection:
python -m cardscan.local_pricing.cli --db local-evidence/pricing.sqlite \
  sync --set 3:635 --set 85:23722 --max-sets 2 --max-requests 12 --dry-run
```

`--execute` is now required for actual sync; old bare `sync` instructions must be
updated. Dry runs use cached discovery metadata and do not migrate/write the
existing database. Fetch metadata explicitly first if absent. Set selection is
bounded and provider availability is explicit. Future full runs require fresh
user authorization and should proceed in checkpointed batches.

Success checkpoints skip already completed provider/set imports within the same
UTC day. An interrupted partially fetched pair reuses complete cached documents.
Request-budget exhaustion now yields **deferred_budget**, stops remaining work,
and permits immediate resume with a new request budget; it is not mislabeled as
a provider failure or subjected to a false 24-hour error cooldown. Genuine failed
endpoints retain daily cooldown/Retry-After and previous committed prices. Progress
is per-provider/set JSON on stderr, with a final JSON summary on stdout. Existing
file locking, atomic set transactions and WAL readers remain intact.

## 7. API improvements for eventual candidate identification

The API still performs **no live provider requests**. Added:

- `GET /cards/search` optional `set_name`, full `number`, `language`, and exact
  `tcgplayer_product_id` filters alongside paginated name discovery.
- `GET /cards/product/{tcgplayer_product_id}` resolves a known product to its
  local identity, available SKU variants and separately labeled latest generic references. Full generic history remains paginated on its dedicated endpoint.
- Both history endpoints accept `order=asc|desc` for deterministic chronology.
- Collector normalization supports explicit prefixed full numbers such as
  `TG01/TG30` → `TG1/TG30`, preserving prefixes and denominators. Missing denominators
  stay missing; no fuzzy completion.

Candidate searches never approve an identification. Unknown edition/finish stays
unknown; multiple possible printings remain candidates. Exact SKU lookup remains
available; stale/missing prices and generic/SKU distinctions are unchanged.
Existing OpenAPI docs describe the additions. No camera, model identification,
PWA, inventory operations, public sync endpoint or authentication system was added.

## 8. Performance, reliability and tests

Measured on the same Linux/Python 3.12 environment, warm OS cache, including
per-lookup read-only SQLite connection and result decoding. No camera/AI/HTTP
latency is included.

| Workload | Median ms | P95 ms | Maximum ms | Correct |
|---|---:|---:|---:|---:|
| 1,000 exact SKU lookups, original baseline | 0.530 | 0.854 | 7.721 | 1,000/1,000 |
| 1,000 exact SKU lookups, expanded | 0.586 | 0.818 | 1.866 | 1,000/1,000 |
| 1,000 repeated same card | 0.581 | 0.826 | 1.940 | 1,000/1,000 |
| 100 name searches | 2.514 | 3.022 | 3.693 | 100/100 |
| 100 set+number searches | 0.994 | 1.360 | 2.182 | 100/100 |
| 100 historical queries | 0.478 | 0.629 | 0.870 | 100/100 |
| 400 reads, four readers during cached imports | 5.681 | 7.632 | 17.099 | 400/400 |

The concurrent test included **28 cached provider/set imports**, took **3.964
seconds** combined, issued zero network requests and preserved observation count
and content hash. No material lookup degradation justified additional indexing or
search infrastructure. These are small-catalog measurements, not guarantees for
all 405,663 reported SKUs or a year of history.

Reproduce with retained local responses already stored in the database:

```bash
python -m cardscan.local_pricing.readiness_benchmark \
  --db local-evidence/backend-expansion/pricing.sqlite \
  --output local-evidence/readiness-benchmark.json
```

[Detailed measured output](../research/results/backend-readiness-2026-10-26/performance.json).
Full suite: **251 tests passed**, baseline **239**. Tests add streaming/CRC checks,
chronological history, exact product/number/language filters, multi-set sync,
interruption and budget resume, read-during-import behavior, large synthetic
catalog pagination, and schema-3-to-4 compatibility/audited edition enrichment.
No test is independent market-pricing accuracy evidence. Legacy AI prompts,
verified-sales logic and paid-call authorizations were not modified.

## 9. Remaining readiness boundary and next milestone

The backend supports fast candidate discovery, exact SKU retrieval and bounded
resumable expansion. It is **not fully validated for historical backfill** while
real archives are unavailable. The two TCGCSV validation failures, missing prices,
unknown attributes, upstream accuracy and commercial rights also remain explicit.

Next: accumulate permitted daily local snapshots and independently check the
expanded SKU references; diagnose the two export failures on their next eligible
attempt. Obtain one restored/otherwise authorized original historical archive and
measure real row counts/resources before any bulk historical backfill. Do not
start the PWA or represent the blocked archive milestone as complete.
