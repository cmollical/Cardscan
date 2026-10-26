# TallyBinder first mobile MVP — October 26, 2026

Implemented as an additional application layer; no existing pricing engine or
source-evidence requirement was replaced. The repository name and historical
CardScan experiment records are preserved. No paid AI calls, provider price requests,
archive downloads, catalog expansion, deployment, or Square integration were executed.

## Working behavior

Eight mobile screens connect camera/library capture, catalog identification review,
condition confirmation, exact-SKU pricing, editable listing approval and persistent
inventory. IndexedDB stores unsent photo blobs and draft details; SQLite stores
uploaded media references, intake revisions, AI job records and inventory audit.
Users can queue the next card while prior cards upload or undergo optional research.
The fully manual workflow requires no AI credentials.

Vision providers use the official Responses API with image input and structured
outputs. They are **implemented and mock-tested, not validated on real AI requests**.
Identity results are cross-referenced against the local catalog and require explicit
confirmation. Condition results are preliminary; contradictions such as an NM
proposal alongside “condition is unknown” withhold the recommendation. Requested
condition is never supplied as an observed fact. Image interpretation does not fetch
prices. Exact pricing remains local and provider-reported, not authenticated sales.

The frontend includes manifest/icons, standalone metadata, safe areas, touch controls,
HTTPS camera access, retakes, image compression and a public offline fallback.
Full cold-start offline use is not implemented. Real iPhone/Safari installation,
photo-library decoding and physical camera acceptance remain device tests.

## Actual validations

| Check | Observed result |
| --- | --- |
| Full Python suite | 272 passed; 251 prior tests plus 21 app tests |
| Frontend unit suite | 14 passed across 3 files |
| TypeScript | `tsc --noEmit` passed |
| Next.js production build | Passed; Next 16.4.3, React 19.2 |
| Mobile Chromium end-to-end | 3 passed |
| Paid AI requests | 0 |

Browser tests use synthetic JPEGs and an isolated temporary database seeded from
retained October 26 source excerpts. They exercised:

1. Front/back upload → manual Base Set Charizard selection → LP exact reference
   **$527.70** → explicit selling price **$500** → inventory save → page reload → CSV
   download → selling price edit **$480** → confirmed deletion.
2. Two consecutive captures → reload → preserved review queue/photos → LP reference
   → change condition to MP → LP quote disappears → exact MP reference **$364.73**
   → camera capture remains available.
3. Mobile overflow check, manifest/apple icon, camera-denial upload fallback and
   a simulated backend inventory failure.

These values are dated provider fixtures, not new live observations. The tests
validate behavior and exact-condition isolation, not independent market accuracy.
They exposed and fixed a badge-dependent navigation label, camera-side reset between
cards, and recovery of a server-acknowledged initial intake after a reload lost its
local revision acknowledgement.

## Existing data preservation

Copied the existing 15-set database using SQLite backup to ignored workspace file
`local-evidence/tallybinder.sqlite`; applied migration 005 to the copy. The original
15-set database was retained. New app tables were empty after migration.

- 3,509 catalog products; 21,735 SKUs; **25,812 historical observations preserved**.
- Ordered observation-row SHA-256 before and after migration:
  `0edb007e86e893bcb365e4872a9ab1235b1c0bf2181579be5be42cd6cfdefd5e`.
- Health, config, catalog search, empty inventory and empty intake returned HTTP 200
  against the migrated 15-set database with AI explicitly disabled.
- No generic history was relabeled as a condition-specific market reference.

The full local database remains ignored by git. A new checkout uses the existing
portable dated evidence seed or an operator's backed-up full database.

## Costs, security and limits

No real per-photo API cost, identification accuracy or condition accuracy is measured.
Default reviewed model rates reserve $0.309 per optional request; this is a conservative
input-context/output upper-bound assumption, not typical spend. Usage and estimated
cost accumulate per intake; unknown usage retains reserve. Jobs have one API attempt,
no automatic retries, explicit frontend confirmation and server daily/request budgets.
See the operating guide for model/rate configuration.

Uploads are bounded, decoded and re-encoded with generated filenames, stripped EXIF,
content deduplication and no public static photo folder. An optional personal bearer
token gates app/media routes. Origin and custom-header checks protect browser writes.
Inventory approval uses server-side catalog validation and revision checks. App data
is single-owner; production authentication, abuse limits and photo-retention tooling
are not implemented. Deleted inventory retains intake/photos/audit as documented.

## Next milestone

Perform an actual iPhone Safari acceptance session over trusted HTTPS using manual
identification and the existing local data, including camera permissions, photo
orientation, Add to Home Screen, reload recovery and a 100-card intake session.
Then explicitly authorize a small mocked-equivalent real vision evaluation with
known cards and human condition labels; measure identity accuracy, disagreements,
latency and true costs before enabling AI by default. Commercial data rights remain
unresolved and must not be inferred from this technical milestone.

Setup, API routes, deployment assessment and installation:
[mobile operating guide](../../docs/tallybinder-mobile.md).
