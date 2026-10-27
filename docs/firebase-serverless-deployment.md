# TallyBinder Firebase and Cloud Run deployment

Status: **implementation complete locally; cloud deployment blocked by the linked
billing account**. On October 27, 2026, Google reported that billing account
`Firebase Payment` was past due or lacked valid payment information. Firestore was
created successfully, but Google rejected Cloud Storage and Artifact Registry
creation. No VM, Cloud Run service, bucket, container image or scheduler was created.

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
- Intended Artifact Registry repository: `tallybinder`
- Runtime identities: `tallybinder-api` and `tallybinder-sync`
- Vercel root directory: `frontend`

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

## Resume after billing is repaired

1. Verify the linked billing account is active. Do not enter payment credentials in
   source files, chat or command output.
2. Create the private `us-east1` bucket with uniform access and object versioning.
3. Create the `us-east1` Docker repository and grant bucket object-user access only
   to the API and sync service accounts.
4. Build the serverless image with Cloud Build.
5. Deploy and execute the sync job once. It initializes the five approved live sets
   and publishes the first snapshot.
6. Create two Secret Manager secrets: the personal access key and independent session
   signing secret. Grant only the API identity access.
7. Deploy Cloud Run with minimum instances zero, AI disabled, exact Vercel origin,
   the private API service account and secrets mounted as environment variables.
8. Import `cmollical/Cardscan` into Vercel using root `frontend` and set server-side
   `TALLYBINDER_BACKEND_URL` to the Cloud Run URL.
9. Update the exact allowed origin if Vercel assigned a different production domain,
   then test login, upload, private image retrieval, catalog search, pricing, inventory,
   CSV export and session-cookie forwarding.
10. Create a daily Cloud Scheduler trigger only after the first manual job succeeds.

## Local verification

The migration retains the local SQLite/filesystem implementation and its tests.
Current verification:

- 294 Python tests pass, including snapshot validation and publish preconditions.
- 14 frontend unit tests pass.
- Next.js typecheck and production build pass.
