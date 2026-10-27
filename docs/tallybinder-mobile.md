# TallyBinder mobile MVP

TallyBinder adds an installable Next.js/React/TypeScript frontend to the existing
FastAPI/SQLite pricing backend. The Python package remains `cardscan`; the GitHub
repository is unchanged. Research artifacts retain their historical product names.
This is a personal-use, single-owner application, not a production multi-user service.

## Run the complete manual workflow

Follow the root README startup instructions. The database must be initialized and
migrated before starting the API. Use **one API worker**: durable vision jobs execute
in FastAPI background tasks, not a distributed queue. Startup marks interrupted AI
jobs for manual review and holds their cost reservations; it never retries them.

1. Open Scan. Capture/upload front and back. Review either thumbnail to retake it.
   Photo-library upload works when live-camera permissions are unavailable.
2. Add to review. Photos and the draft are saved in IndexedDB before uploading.
   Start the next card immediately; uploads and pricing are separate from capture.
3. Open Review, select a card, search by name and optionally exact set/full number.
   Choose a catalog product and confirm language, edition and finish. A printing
   attribute is prefilled only when all catalog variants agree. Unknowns remain unknown.
4. Confirm NM/LP/MP/HP/DMG based on inspection in hand. Optional AI suggestions are
   never automatically applied. Photo assessment cannot reliably detect every defect.
5. Request the exact SKU price. The app labels provider, SKU, update time, missing
   data and staleness. Generic references appear separately. Identity/condition
   changes clear the displayed quote immediately. There is no web-search fallback.
6. Choose your selling price; the market reference is a separate observation.
   When no exact price exists, enter your own price. Preview and edit the deterministic
   description, title, quantity and notes, then approve and save.
7. Inventory supports search, condition filtering, edits, CSV and confirmed deletion.
   Repeated identical save requests cannot create duplicate listings for one intake.

An unknown or conflicting printing does not become a condition-specific price.
Selecting a catalog entry is required for inventory approval; arbitrary unindexed
cards can remain in intake until their catalog metadata is available. Current scope
is raw Pokémon cards. No graded-card pricing or automatic listing approval is provided.

## Persistence and failure behavior

Schema migration **005** adds `app_media`, `intake_sessions`, `intake_cards`,
`vision_jobs`, `inventory_listings`, and append-only `inventory_versions`. All
existing catalog/SKU/price history tables remain intact. Back up SQLite and the
media directory together. Monetary values remain decimal strings in API/storage.
Inventory snapshots retain confirmed identity, product/SKU references, source
market reference and the independently chosen selling price.

Drafts and compressed photo blobs persist in the browser's IndexedDB. Successful
uploads use generated IDs and backend storage. Reload recovers local drafts and
server intake; revision checks prevent stale overwrites. A lost initial save response
can reconcile the same photo pair without creating a second intake. A conflicting
later server draft requires review before confirmation. Errors stay attached to
individual cards and do not block capture. Retry using the queue's sync control.
Browser storage eviction, private browsing or clearing site data can remove unsynced
work. Do not treat browser storage as a backup.

The service worker stores public shell assets and an offline navigation explanation.
An already open app can capture durable local drafts offline. **Cold offline reload
shows a fallback page, not the full workflow.** AI, catalog search, server inventory
and fresh pricing require the backend. Background work is not guaranteed after
browser termination; server AI work can finish while the browser is closed if the
API process remains alive. Server restarts do not retry possibly billed requests.

Deletion hides an inventory listing; intake, photos and revision audit remain for
traceability. There is no automatic permanent photo cleanup in this milestone.
CSV exports use authenticated download, quote fields and escape spreadsheet formulas.
Images export as backend media references, not public image hosting URLs. Square
integration will need an explicit mapping and authorized image hosting later.

## Configuration

Root `.env.example` is a **backend template**, not automatically loaded. Export
variables or use `uvicorn --env-file .env` after installing `python-dotenv`.
Next.js reads `frontend/.env.local`; copy `frontend/.env.example` when needed.
Never place OpenAI credentials in `NEXT_PUBLIC_*` variables or frontend files.

| Variable | Purpose |
| --- | --- |
| `TALLYBINDER_DB` | SQLite file; old `CARDSCAN_PRICING_DB` fallback is preserved |
| `TALLYBINDER_MEDIA_DIR` | Persistent JPEG directory; defaults to `photos` beside DB |
| `TALLYBINDER_ACCESS_TOKEN` | Optional personal bearer token; configure before LAN/public exposure |
| `TALLYBINDER_ALLOWED_ORIGINS` | Comma-separated exact browser origins authorized for writes |
| `TALLYBINDER_BACKEND_URL` | Next server's backend target; default `http://127.0.0.1:8000` |
| `TALLYBINDER_DEV_ORIGINS` | Additional development asset hostnames, without protocol/port |
| `TALLYBINDER_AI_ENABLED` | Defaults `false`; enables paid photo jobs only when deliberately configured |
| `OPENAI_API_KEY` | Backend-only credential, required for real AI jobs |
| `TALLYBINDER_AI_MODEL` | Default `gpt-5.4-mini`; interchangeable provider interface |
| `TALLYBINDER_AI_INPUT_RATE`, `TALLYBINDER_AI_OUTPUT_RATE` | Reviewed USD/million token estimates |
| `TALLYBINDER_AI_MAX_INPUT_TOKENS` | Conservative model context reservation; default 400,000 |
| `TALLYBINDER_AI_MAX_OUTPUT_TOKENS` | Request output cap; default 2,000 |
| `TALLYBINDER_AI_REFINEMENT_MAX_INPUT_TOKENS`, `TALLYBINDER_AI_REFINEMENT_MAX_OUTPUT_TOKENS` | Optional catalog-guided set-code reread caps; defaults 40,000 / 500 |
| `TALLYBINDER_AI_PER_JOB_USD`, `TALLYBINDER_AI_DAILY_USD` | Default $0.50/request and $5/day safeguards |
| `TALLYBINDER_AI_DAILY_JOBS` | Default 30 attempted jobs/day |

AI settings do not authorize calls in this development assignment. No paid calls
were executed. Deployment operators must deliberately enable AI, supply credentials
and confirm each request in the app. Manual identification and condition selection
work without a key. The combined identification review sends the front and back
photos once, returning structured printing evidence and a preliminary condition
recommendation in the same paid request. Both remain editable and require one
explicit human confirmation before pricing.
No web search tools are enabled. Requests use structured outputs and `store=false`;
this does not claim zero retention under all provider policies.

Default rates reuse the existing reviewed model rate card: $0.75/M input and
$4.50/M output. A conservative **$0.34125** identification reservation covers the
initial request plus one optional bounded catalog-guided set-code reread; condition
review reserves **$0.309**. These are not predictions of normal image cost. Actual
completed usage is recorded and releases unused reserve. Unknown usage/errors retain reserve.
Two AI jobs per card reserve separately. Custom models require explicitly reviewed
rates and input context. Estimates exclude discounts and must be rechecked against
[OpenAI pricing](https://developers.openai.com/api/docs/pricing) before enabling.
No claim of real identification accuracy, real condition accuracy or real per-scan
cost is supported yet. Mocked tests cannot establish those properties.

## iPhone testing and installation

The app needs a reachable **trusted HTTPS origin** for live camera and installation;
`http://localhost` is secure only on the machine running the browser. An iPhone cannot
reach your computer through the phone's `localhost`.

For a trusted local-network setup, provide a certificate/key trusted by the iPhone
for your development hostname/IP, and start Next with:

```bash
cd frontend
npm run dev -- --experimental-https \
  --experimental-https-key /path/to/dev-key.pem \
  --experimental-https-cert /path/to/dev-cert.pem
```

Set the exact phone-facing URL (for example `https://YOUR-DEV-HOST:3000`) in backend
`TALLYBINDER_ALLOWED_ORIGINS`, the hostname in `TALLYBINDER_DEV_ORIGINS`, and restart
both services. Keep uvicorn on loopback; only Next needs to be reachable on the
trusted network. Use the personal access token via Settings. Do not expose a public
tunnel with authentication disabled. The access token is a personal-development
credential stored in browser localStorage, not a multi-user login implementation.

Open the HTTPS URL in Safari → Share → **Add to Home Screen** → Add. Launch the
TallyBinder icon; manifest, standalone mode, apple-touch icon, viewport safe areas
and touch targets are included. Allow camera access or use the photo library.
HEIC upload depends on the browser's decoder; if unsupported, choose JPEG/PNG.
Safari/iPhone installation and actual hardware camera operation require device
acceptance testing; mobile Chromium tests do not establish Safari compatibility.

## API

Next proxies `/api/backend/*` to FastAPI. Original catalog, exact lookup, generic
references, histories, health and read-only sync status remain available. No public
administrative synchronization endpoint was added.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/app/config` | Safe feature flags and cost reservation, no credentials |
| POST | `/media/upload` | Decode/validate/re-encode one JPEG/PNG/WebP, max 8 MB |
| GET | `/media/{id}` | Authorized private JPEG, no-store |
| POST | `/intake/sessions` | Idempotent intake session |
| GET | `/intake` | Paginated durable intake |
| PUT / GET | `/intake/{id}` | Revision-checked draft / current state |
| POST | `/intake/{id}/price?revision=N` | Local exact lookup, never live provider retrieval |
| POST | `/intake/{id}/jobs` | Explicitly authorized combined identity/condition review (legacy condition jobs remain readable) |
| GET | `/jobs/{id}` | Result, usage, cost, status and stale-result indicator |
| POST / GET | `/inventory` | Approved listing creation / paginated search |
| GET / PUT / DELETE | `/inventory/{id}` | Read, revision-checked edit, confirmed soft delete |
| GET | `/inventory/export.csv` | Formula-safe export |

Interactive request schemas: `/docs`. Writes require `X-TallyBinder-Client: web`;
when configured, private app routes also require `Authorization: Bearer ...`.
Origin checks protect browser writes; no permissive CORS is enabled. Existing public
pricing read endpoints remain public. Photo filenames are generated UUIDs and never
use uploaded names. Decoding checks magic bytes, animation, pixel/size limits and
strips EXIF; no arbitrary path is accepted. API body limits apply independently.
There is no production abuse-rate limiting or multi-user authentication yet.

## Development tests

```bash
. .venv/bin/activate
python -m unittest discover -s tests -q
cd frontend
npm ci
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Browser tests start an isolated temporary SQLite API with saved source excerpts and
AI disabled. Synthetic test photos contain no real card evidence. Tests cover the
manual full workflow, durable batch capture/reload, condition invalidation, mobile
layout, PWA metadata, camera denial, API errors, CSV and inventory edits/deletion.
They are not independent validation of provider pricing accuracy. See the
[implementation results](../research/results/tallybinder-mvp-2026-10-26.md).

## Synchronization

Use the existing controlled pricing CLI; the app never synchronizes while pricing.
See [local pricing documentation](local-pricing-backend.md). Existing daily append-only
observations, exact IDs, request budgets, provider cooldowns and separate generic/SKU
history remain unchanged. No catalog expansion or archive downloads were performed.
Commercial licensing and upstream redistribution remain unresolved.

## Deployment assessment — nothing deployed

- **Single small VM or private home server:** most direct fit. Run Next plus one
  uvicorn worker behind trusted HTTPS with persistent SQLite/media, backups and
  private access. Hosting costs depend on the chosen provider. No scheduler is needed
  to exercise the MVP.
- **Vercel:** suitable for the Next frontend/proxy; persistent Python/SQLite/media
  need a separate backend host. Function-local files are not durable inventory storage.
- **Cloudflare:** frontend hosting is feasible; Workers/Pages are not a drop-in host
  for this persistent FastAPI/SQLite process. Keep the Python backend on a persistent
  service. D1/R2 adaptation is a future project, not implemented here.
- **ChatGPT Sites:** not validated as a host for this Next server plus persistent
  Python/SQLite/media service. Do not assume publishing a Site deploys this backend.

No provider-specific deployment configuration, production service or hosted scheduler
has been created. Before exposure to other users, add proper authentication,
per-owner identity selection, abuse controls, backups/restore drills, secret management,
photo retention controls and commercial data rights. The owner columns are preparation,
not evidence of implemented multi-user isolation/login.
