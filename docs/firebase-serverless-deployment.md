# TallyBinder Firebase and Cloud Run deployment

Status: **deployed October 27, 2026**. The billing issue was repaired and the no-VM
Google Cloud resources are live. The first bounded pricing sync and Vercel production
deployment completed successfully.

## Selected architecture

```text
Vercel Next.js
    |
    | Firebase Authentication ID token
    | same-origin /api/backend rewrite
    v
Cloud Run FastAPI (scales to zero)
    |-- Firestore: intake sessions, cards, inventory and audit versions
    |-- private Cloud Storage: normalized card photos
    |-- Cloud Tasks: bounded, authenticated AI work dispatch
    `-- /tmp validated read-only SQLite pricing snapshot

Cloud Tasks -> Google-signed internal API endpoint
    |-- exact audience and task-caller identity verification
    |-- Firestore: atomic job claim, result, usage and daily reservation ledger
    `-- OpenAI Responses API: image analysis with strict JSON Schema output

Cloud Scheduler -> Cloud Run Job
    |-- download current versioned SQLite snapshot
    |-- run bounded provider synchronization locally
    `-- publish with a Cloud Storage generation precondition
```

Cloud Storage is object storage, not a POSIX filesystem. The API downloads a
validated snapshot to instance-local `/tmp`; it never opens SQLite directly on a
bucket mount. API instances periodically compare object generations and atomically
replace their local read-only snapshot. The daily job is the only pricing writer.
Bucket object versioning provides rollback generations, and a generation-match
precondition prevents concurrent jobs from silently overwriting each other.

The production AI path is durable and does not use instance background work. The API
atomically reserves a per-job and daily budget in Firestore, creates an idempotent
job, and enqueues a named Cloud Task. A Google-signed internal API endpoint verifies
the exact task-caller identity and atomically claims the job before making one OpenAI
request. A repeated delivery sees the claimed or finished state and cannot create a
second paid attempt. Identification is reconciled
against the local catalog; condition review remains preliminary and both require
explicit human confirmation in the UI before pricing or inventory changes.

## User accounts and data isolation

The frontend uses Firebase Authentication with Google and email/password providers.
After sign-in, the Firebase browser SDK sends a short-lived ID token to the API on
each request. Cloud Run verifies the token against the `tallybinder` Firebase project
and derives the owner only from its signed `uid`; a browser cannot select or spoof an
owner ID.

Every mutable Firestore document is written with that verified owner, and reads for
intake sessions, card drafts, inventory, photo metadata, AI jobs and daily AI budgets
are filtered by it. Private image objects are also owner-namespaced. Cloud Tasks do
not rely on browser identity: the queued job records its owner, and the authenticated
worker restores that owner scope before reading photos or writing AI results.

Vercel needs only the public `NEXT_PUBLIC_FIREBASE_*` web-app values listed in
`frontend/.env.example`. Cloud Run needs `TALLYBINDER_FIREBASE_PROJECT_ID`. Neither
the OpenAI key nor a Firebase service-account credential belongs in Vercel.

## Resources

- Project: `tallybinder` (`1031748906945`)
- Region: `us-east1`
- Firestore Native `(default)`: created, free tier, delete protection enabled
- Private bucket: `tallybinder-1031748906945-data`
- Artifact Registry repository: `tallybinder`
- Runtime identities: `tallybinder-api`, `tallybinder-sync`, and the dedicated
  `tallybinder-tasks` invocation identity
- Vercel root directory: `frontend`
- Cloud Run API: `https://tallybinder-api-1031748906945.us-east1.run.app`
- Cloud Tasks queue: `tallybinder-vision`, serial dispatch in `us-east1`
- Cloud Run job: `tallybinder-sync`
- Cloud Scheduler: `tallybinder-daily-pricing`, 06:15 `America/New_York`
- Vercel frontend: `https://tallybinder.vercel.app`

The API and daily job share one image built from `deploy/Dockerfile.serverless`.
The service runs the API module, and the daily job overrides the command with
`python -m cardscan.cloud.daily`. No VM or continuously running worker is used.

## AI safety and operating limits

- Model: `gpt-5.4-mini`; image input and strict structured outputs only.
- OpenAI key: Cloud Run Secret Manager injection; never sent to Vercel or an API
  response payload.
- Per authorized request reserve: `$0.309` at reviewed maximum token assumptions.
- Per-user daily ceiling: 30 jobs and `$5.00` reserved spend.
- Cloud Tasks: one concurrent dispatch; the Firestore claim makes delivery retries
  idempotent.
- OpenAI Responses are stateless (`store=false`) and have no tools enabled.
- AI output never changes identity or condition automatically. The owner selects a
  catalog candidate and accepts or rejects the preliminary condition recommendation.

## Daily pricing job

The production job discovers provider set indexes and selects a bounded rotating
batch without naming individual sets in application code. Each run admits up to ten
previously unseen sets (split across English and Japanese catalogs) and refreshes up
to four recently released imported sets. Only genuine, non-future release dates are
eligible; undated promotional buckets are not treated as new releases. Explicit scope configuration remains
available for recovery or a reviewed backfill.

At most 64 provider requests are allowed per execution. Provider endpoint cooldown,
conditional-request state, append-only observations and sync checkpoints live inside
the published snapshot. A provider-specific failure is publishable only when another
approved provider successfully committed the same exact set; a set with no successful
provider aborts publication. Cloud Scheduler should invoke one task once daily with job retries disabled;
the provider cooldown and generation precondition are additional safeguards.

## Deployment record

Completed: private versioned bucket, Artifact Registry, restricted service-account
IAM, Cloud Build image, Cloud Run job, initial snapshot, Secret Manager values, Cloud
Run API, Vercel frontend, and a daily Scheduler trigger with retries disabled. The
initial snapshot contained 1,209 products and 7,625 SKUs. Production checks through
the Vercel same-origin proxy returned 200 for health, login and authenticated
inventory; an anonymous protected request returned 401.

Firebase Authentication is live on the Vercel production deployment with Google and
email/password registration. The production API is revision
`tallybinder-api-00010-v7q`; anonymous configuration requests succeed while private
inventory requests return `401 sign_in_required`. The only records created before
account authentication are the synthetic acceptance-test draft, two test photos and
its AI job; there is no legacy saved inventory to migrate.

AI was enabled with a restricted OpenAI key
in Secret Manager. A live synthetic-photo acceptance request exercised upload,
Firestore reservation, authenticated Cloud Tasks delivery, the Responses API,
result polling and cost settlement. The placeholder was correctly reported as not
being a real card, the task endpoint returned 204, the queue drained, and the app
recorded `$0.0011295` for the request. Real-card identification and condition output
still require human review as designed.

## Demo marketplace publishing

An approved inventory record can be pushed through the marketplace adapter without
granting the storefront access to the user's binder or Firebase identity. The
outbound payload freezes the listing revision, seller-approved title, description,
condition, price, quantity, catalog fields and front image. Each attempt is recorded
as `sending`, `published` or `failed` with its provider, external listing ID,
timestamps, response and a payload/image fingerprint. Retrying is idempotent because
the TallyBinder listing ID is also the external listing ID.

The initial adapter targets the private ChatGPT Site **The Card Counter** at
`https://tallybinder-demo-card-shop.cmollical.chatgpt.site`. It uses D1 for listing
records and R2 for images and explicitly provides no checkout, payments or
fulfillment. The adapter boundary can later implement Square, Shopify or another
provider without changing the scan, human-review or inventory audit model.
The production service keeps both its publish credential and the Site's private
service-access credential in Secret Manager. A schema-7 pricing job execution and a
non-mutating authenticated publish probe completed successfully before traffic was
sent to the marketplace-enabled API revision.

## Local verification

The migration retains the local SQLite/filesystem implementation and its tests.
Current verification before the production switch:

- 300 Python tests pass, including Firebase ID-token isolation, marketplace
  publication auditing, Firestore job
  idempotency, authenticated task
  construction, snapshot validation and publish preconditions.
- 14 frontend unit tests pass.
- Next.js typecheck and production build pass.
