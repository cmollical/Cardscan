# TallyBinder Firebase and Cloud Run deployment

Status: **deployed October 27, 2026**. The billing issue was repaired and the no-VM
Google Cloud resources are live. The first bounded pricing sync and Vercel production
deployment completed successfully.

## Selected architecture

```text
Vercel Next.js
    |
    | same-origin /api/backend rewrite
    v
Cloud Run FastAPI (scales to zero)
    |-- Firestore: intake sessions, cards, inventory and audit versions
    |-- private Cloud Storage: normalized card photos
    |-- Cloud Tasks: bounded, authenticated AI work dispatch
    `-- /tmp validated read-only SQLite pricing snapshot

Private Cloud Run vision worker (scales to zero)
    |-- Firestore: atomic job claim, result, usage and daily reservation ledger
    |-- Cloud Storage: read-only normalized front/back photos
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
job, and enqueues a named Cloud Task. A private Cloud Run worker atomically claims the
job before making one OpenAI request. A repeated task delivery sees the claimed or
finished state and cannot create a second paid attempt. Identification is reconciled
against the local catalog; condition review remains preliminary and both require
explicit human confirmation in the UI before pricing or inventory changes.

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
- Private Cloud Run worker: `tallybinder-vision`
- Cloud Tasks queue: `tallybinder-vision`, serial dispatch in `us-east1`
- Cloud Run job: `tallybinder-sync`
- Cloud Scheduler: `tallybinder-daily-pricing`, 06:15 `America/New_York`
- Vercel frontend: `https://tallybinder.vercel.app`

The API, private worker and daily job share one image built from
`deploy/Dockerfile.serverless`. The API uses the default module, the worker selects
`cardscan.cloud.vision_worker:app`, and the daily job overrides the command with
`python -m cardscan.cloud.daily`.

## AI safety and operating limits

- Model: `gpt-5.4-mini`; image input and strict structured outputs only.
- OpenAI key: worker-only Secret Manager injection; never sent to Vercel or the API
  response payload.
- Per authorized request reserve: `$0.309` at reviewed maximum token assumptions.
- Per-user daily ceiling: 30 jobs and `$5.00` reserved spend.
- Cloud Tasks: one concurrent dispatch; the Firestore claim makes delivery retries
  idempotent.
- OpenAI Responses are stateless (`store=false`) and have no tools enabled.
- AI output never changes identity or condition automatically. The owner selects a
  catalog candidate and accepts or rejects the preliminary condition recommendation.

## Daily pricing job

The default approved scopes remain explicit and bounded:

```text
3:23228,3:23237,3:604,3:630,85:23599
```

At most 64 provider requests are allowed per execution. Provider endpoint cooldown,
conditional-request state, append-only observations and sync checkpoints live inside
the published snapshot. A partial provider failure does not publish the modified
snapshot. Cloud Scheduler should invoke one task once daily with job retries disabled;
the provider cooldown and generation precondition are additional safeguards.

## Deployment record

Completed: private versioned bucket, Artifact Registry, restricted service-account
IAM, Cloud Build image, Cloud Run job, initial snapshot, Secret Manager values, Cloud
Run API, Vercel frontend, and a daily Scheduler trigger with retries disabled. The
initial snapshot contained 1,209 products and 7,625 SKUs. Production checks through
the Vercel same-origin proxy returned 200 for health, login and authenticated
inventory; an anonymous protected request returned 401. Upload, private image,
catalog, pricing and CSV workflows should still receive an interactive owner
acceptance pass before relying on the deployment.

## Local verification

The migration retains the local SQLite/filesystem implementation and its tests.
Current verification before the production switch:

- 296 Python tests pass, including Firestore job idempotency, authenticated task
  construction, snapshot validation and publish preconditions.
- 14 frontend unit tests pass.
- Next.js typecheck and production build pass.
