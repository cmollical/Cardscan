# TallyBinder Firebase and Cloud Run deployment

Status: **backend deployed October 27, 2026; first Vercel production deployment
pending**. The billing issue was repaired and the no-VM Google Cloud resources are
live. The first bounded pricing sync completed successfully.

## Selected architecture

```text
Vercel Next.js
    |
    | same-origin /api/backend rewrite
    v
Cloud Run FastAPI (scales to zero)
    |-- Firestore: intake sessions, cards, inventory and audit versions
    |-- private Cloud Storage: normalized card photos
    `-- /tmp validated read-only SQLite pricing snapshot

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

AI is disabled for the initial deployment. The existing SQLite vision queue is not
used by the Firestore adapter; enabling AI requires a separate Cloud Tasks/Firestore
job implementation and explicit paid-use authorization.

## Resources

- Project: `tallybinder` (`1031748906945`)
- Region: `us-east1`
- Firestore Native `(default)`: created, free tier, delete protection enabled
- Intended private bucket: `tallybinder-1031748906945-data`
- Artifact Registry repository: `tallybinder`
- Runtime identities: `tallybinder-api` and `tallybinder-sync`
- Vercel root directory: `frontend`
- Cloud Run API: `https://tallybinder-api-1031748906945.us-east1.run.app`
- Cloud Run job: `tallybinder-sync`
- Cloud Scheduler: `tallybinder-daily-pricing`, 06:15 `America/New_York`

The service and job share one image built from `deploy/Dockerfile.serverless`.
The service runs its default Uvicorn command. The job overrides the command with
`python -m cardscan.cloud.daily`.

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

## Deployment record and remaining steps

Completed: private versioned bucket, Artifact Registry, restricted service-account
IAM, Cloud Build image, Cloud Run job, initial snapshot, Secret Manager values, Cloud
Run API, and a daily Scheduler trigger with retries disabled. The initial snapshot
contained 1,209 products and 7,625 SKUs; the public health endpoint returned 200 and
an anonymous protected request returned 401.

Remaining:

1. Deploy the connected Vercel project from `cmollical/Cardscan` using root
   `frontend` and server-side
   `TALLYBINDER_BACKEND_URL` to the Cloud Run URL.
2. Update the exact allowed origin if Vercel assigns a different production domain,
   then test login, upload, private image retrieval, catalog search, pricing, inventory,
   CSV export and session-cookie forwarding.

## Local verification

The migration retains the local SQLite/filesystem implementation and its tests.
Current verification:

- 294 Python tests pass, including snapshot validation and publish preconditions.
- 14 frontend unit tests pass.
- Next.js typecheck and production build pass.
