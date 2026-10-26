# TallyBinder cloud deployment runbook

Status: **prepared for operator approval; not deployed**. No cloud account or VM
was created. No cloud credentials were available in the managed execution context.
No paid AI call or hosting purchase occurred. See the
[decision](cloud-deployment-decision.md), [current free-tier comparison](free-tier-hosting-research.md)
and [local validation results](../research/results/cloud-readiness-2026-10-26.md).

## Exact prerequisites and approval boundary

The owner must:

1. Provide/authorize an existing **Oracle Cloud Free Tier account**, or create it
   personally at https://www.oracle.com/cloud/free/ . Signup can require identity
   and card verification. Select the home region deliberately. Do not upgrade to
   Pay As You Go, substitute trial-credit-only shapes, or accept a nonzero quote.
2. Provide/authorize a personal **Vercel Hobby account** at https://vercel.com/signup
   with access to `cmollical/Cardscan`. This is not eligible for commercial shop use
   under Hobby's personal-use terms.
3. Supply an existing DNS hostname, or authorize obtaining a free DNS hostname
   (for example through https://www.duckdns.org/). Point its A record to the VM.
   No domain purchase is required or authorized. The free DNS provider is another
   availability dependency; neither DNS-account creation nor DNS changes occurred.
4. Explicitly approve provisioning the listed **Always Free resources** and the
   public HTTPS deployment after reviewing this runbook. Existing instructions
   authorize preparation, not public publishing.
5. Configure cloud/SSH access through a secure credential mechanism. Do not paste
   SSH private keys, passwords, provider tokens or OpenAI keys into chat. Generate
   the personal app access key/session secret on the VM and use a password manager.
6. Separately authorize paid vision use, then put `OPENAI_API_KEY` on the VM only.
   Every in-app AI request also requires confirmation and the persisted budget check.

These are real account/authorization requirements. They are not a request to run
Python on an iPhone. After account access and deployment approval, the operator can
perform the setup; the phone user needs only the resulting URL and access key.

## Resource plan — verify console quote is $0 before creation

- One **VM.Standard.A1.Flex**, 2 OCPUs, 12 GB RAM, Always Free-compatible Ubuntu
  Linux image, in the tenancy's home region and an available availability domain.
- 50 GB boot volume + **100 GB retained block volume**, within the current 200 GB
  combined Always Free allowance. Do not enable deletion of the data volume when
  terminating a VM. Use normal free-eligible volume performance, not paid upgrades.
- Public networking needed for HTTPS; verify actual IPv4/network resource pricing
  in the console and stop if any component is nonzero. No load balancer/NAT gateway
  or paid reserved networking resource is required by this configuration.
- Security group/NSG: 80/443 inbound, SSH 22 restricted to the operator's IP. No
  public 3000/8000 port or Docker socket. Keep the OS firewall aligned; Docker port
  publishing is not controlled by every host firewall configuration automatically.
- A **private** home-region OCI Object Storage bucket within 20 GB and 50,000
  requests/month for encrypted off-VM backups, plus up to five free volume backups.
  No public bucket, archive-tier lifecycle or paid automatic expansion.

OCI may have no ARM capacity or reclaim an idle instance. Do not work around its
idle rules with artificial traffic/load. If capacity is unavailable, stop and
report it; do not silently provision paid compute. Free hosting is conditional,
not an uptime/SLA commitment. Data-volume retention and off-VM recovery still need
actual tenancy verification.

## Persistent layout

Attach/mount the retained data volume at `/srv/tallybinder` using a filesystem UUID
in `/etc/fstab`. Back up its configuration separately. Confirm it is really mounted
before writing; do not accidentally use the boot filesystem as the data volume.
On this dedicated VM, install the supplied
`deploy/systemd/docker.service.d/tallybinder-data.conf` under
`/etc/systemd/system/docker.service.d/` and run `systemctl daemon-reload` before
starting the stack. It orders Docker after the required mount. Private sync/backup
scripts also refuse to run when that mount is absent. Do not add a silent fallback
to a boot-directory or delete the data volume on VM replacement.

```text
/opt/tallybinder/                  repository checkout, replaceable code
/srv/tallybinder/data/
  database.sqlite                 catalog, SKUs, append-only history, inventory, jobs
  photos/                         private immutable JPEGs
  daily-sets.json                 explicit, bounded approved provider/set scopes
/srv/tallybinder/config/
  app.env                         backend-only keys and origins, root mode 600
  compose.env                     hostname and persistent path selections
  backup.env                      root-only private object-store credentials
  restic-password                 separate encrypted-repository key, mode 600
/srv/tallybinder/backups/          consistent local archives; not sole backup
/srv/tallybinder/tls/              persistent Caddy account/certificates
```

Create data/photos/backups as UID/GID **10001**, mode 700. Keep configuration
root-owned; Docker reads `app.env` on the host, not through an app-readable static
folder. Create the TLS directory for Caddy's image user as required by that image.
Never put the database, card photos, live env files or backup credentials in Git.

## Build, migrate and validate privately

Install Docker Engine + Compose v2, git, Python 3 and `flock` on the VM using
vendor-supported packages. Backups additionally use the host `restic` CLI.
Clone this repository under `/opt/tallybinder`, pin the approved commit and copy
`deploy/compose.env.example` / `deploy/app.env.example` into the private config
directory. Replace placeholders. Example commands below are **operator instructions**;
none provisions or publishes anything in this assignment.

Generate two independent long random values locally on the VM (e.g. Python
`secrets.token_urlsafe(48)`) for `TALLYBINDER_ACCESS_TOKEN` and
`TALLYBINDER_SESSION_SECRET`. Do not log them. Template placeholder values are
rejected in cloud mode. Set `TALLYBINDER_CLOUD=true` and
`TALLYBINDER_JOB_MODE=external`; background-in-request mode is rejected in cloud.
Initially leave AI disabled until separately authorized and configured.

Set `TALLYBINDER_ALLOWED_ORIGINS=https://YOUR-PROJECT.vercel.app` to the stable
production frontend origin. No wildcard CORS or preview-origin authorization.

Transfer the **existing real full SQLite database and all referenced photos**
using a consistent backup/restore, not a raw copy of a live WAL database. The ignored
workspace source currently has the 15 sets/3,509 products/21,735 SKUs/25,812 dated
observations. It is not present in a fresh Git clone. A Git clone cannot recreate
private inventory/photos. Do not seed the cloud from synthetic data or pretend the
portable five-card seed is the complete live catalog.

To create a transferable snapshot from an existing local database:

```bash
python -m cardscan.ops --db /path/database.sqlite --media /path/photos \
  backup --destination /private/transfer-backups
python -m cardscan.ops restore --archive /private/transfer-backups/tallybinder-....tar \
  --destination /private/restored-copy
```

Use secure copy to transfer the archive, verify its reported SHA-256, restore into
an unused directory on the data volume and select it as the deployment data path.
Restore refuses to overwrite existing live data. Database and photos must move
together. Fix ownership to 10001 before starting containers.

From `/opt/tallybinder`:

```bash
docker compose --env-file /srv/tallybinder/config/compose.env -f deploy/compose.yml build api
# Applies migration 006 only after an automatic complete pre-migration backup.
docker compose --env-file /srv/tallybinder/config/compose.env -f deploy/compose.yml \
  run --rm --no-deps admin migrate --backup-directory /backups
docker compose --env-file /srv/tallybinder/config/compose.env -f deploy/compose.yml \
  run --rm --no-deps admin check
docker compose --env-file /srv/tallybinder/config/compose.env -f deploy/compose.yml \
  run --rm --no-deps admin approved-sets --output /data/daily-sets.json
docker compose --env-file /srv/tallybinder/config/compose.env -f deploy/compose.yml \
  run --rm --no-deps admin daily --config /data/daily-sets.json
```

Review the final dry-run output and the JSON file: **only currently imported scopes**,
at most 15 sets, at most **64 requests per invocation**. Newly imported sets do not
silently enter the daily plan. `approved-sets` refuses to overwrite an approval file.
The image does not seed a blank DB; missing database/catalog data fails preflight.
Runtime dependencies are locked in `requirements-cloud.txt`; update the lock and
retest deliberately. ARM wheel availability was checked, but native VM execution
still needs validation.

Migration 006 adds frozen job settings and execution timestamps/index only. Existing
catalog/observations/inventory/media are preserved. Back up before any future
migration; stop writers for schema changes and retain a tested rollback snapshot.

## Enable the backend only after public-deployment approval

With working DNS, approved firewall rules, correct HTTPS origin and persistent
paths verified:

```bash
docker compose --env-file /srv/tallybinder/config/compose.env -f deploy/compose.yml up -d api worker edge
```

Caddy obtains and renews public certificates automatically and redirects HTTP to
HTTPS. Its state is durable. API, photos and inventory are not mounted into its
static file server. No public administrative sync/backup endpoint exists.

Health must be green before the edge/worker starts. Check private container logs
and public `/health`. The API requires authentication for catalog/pricing, inventory,
media, jobs and API documentation; only safe health/config and login are public.
No cache may retain API/media responses. Any initial pricing is explicitly dated;
perform the bounded sync below and check provider freshness rather than assuming
old references are live.

## Vercel frontend

After the same explicit publishing approval, import `cmollical/Cardscan` at
https://vercel.com/new and select:

- Hobby personal project; root directory **`frontend`**, framework **Next.js**.
- Build `npm run build`, install `npm ci`; supported Node 22 runtime.
- Server-side `TALLYBINDER_BACKEND_URL=https://YOUR-API-HOSTNAME`, **no trailing slash**.
  No OpenAI key, app access key, session secret or object-store credential in Vercel.
- Do not opt into paid add-ons/marketplace databases, analytics upgrades or Pro.

The existing rewrite `/api/backend/:path*` goes to the VM's API path. Do not replace
it with a custom serverless Function proxy. Browser requests and secure host-only
session cookies remain first-party to the Vercel hostname, avoiding Safari
third-party-cookie dependence. Verify this behavior on the actual platform.
Changing the backend target requires a new Next build because rewrite configuration
is serialized at build time.

Visit Settings and sign in with the personal access key. Production exchanges the
key for a **Secure, HttpOnly, SameSite=Strict, host-only 12-hour cookie**; it does not
persist the key in localStorage. Signing out removes the cookie. Browser-local draft photos remain on the personal
device so unsynced work is not erased; use device security and do not treat a shared
browser as encrypted multi-user storage. Rotating either
the app access key or session secret invalidates prior sessions. Bearer access
remains available for authorized operator/API clients. Preserve HTTPS and exact
Origin checks; CORS is not being used as authentication.

**Required real Vercel probes:** maximum supported image upload, Cookie/Set-Cookie
forwarding, authenticated image download, CSV export and polling while scanning.
Published rewrite timeout is 120 seconds; no OpenAI work waits inside the request.
The 4.5 MB Function limit alone does not establish a rewrite payload cap. If actual
platform behavior prevents required uploads, use the supplied single-VM frontend;
do not declare a compromised deployment complete.

## Single-VM frontend fallback (Option C)

Set the allowed origin to `https://YOUR-APP-HOSTNAME` and use:

```bash
docker compose --env-file /srv/tallybinder/config/compose.env \
  -f deploy/compose.yml -f deploy/compose.full.yml --profile full build frontend
docker compose --env-file /srv/tallybinder/config/compose.env \
  -f deploy/compose.yml -f deploy/compose.full.yml --profile full up -d api worker frontend edge
```

The full Caddy config proxies `/api/backend/*` directly to FastAPI and other paths
to the Next standalone server. It uses the same volumes, private sessions, worker
and timers. No pricing/database rewrite is needed. Public port 3000 remains closed.

## Real AI execution and restart safety

Only after explicit paid-use approval, set the real backend `OPENAI_API_KEY` and
`TALLYBINDER_AI_ENABLED=true`; recreate API and worker with the same persistent
volume. No new code/mock mode is needed. Each in-app identification/condition
request still requires confirmation. Default daily count 30 and $5 guards are
intentional, not a missing feature; review budgets before 200 jobs for 100 cards.

The API records consent, model, rate/context assumptions and reservation atomically,
then returns queued state. A single filesystem-locked worker serially claims rows
with a transactional status transition. Only it executes the vision provider.
Per-job settings stay frozen across redeployments. Enqueue-day and execution-day
limits both apply; backlog cannot bypass spending safeguards across midnight.

A successful response persists usage and estimated cost. Unknown costs retain their
reserve. API retries are disabled. On worker restart, queued never-attempted jobs
can continue, but **running jobs become interrupted and are not retried**. Restarted
API processes do not touch external worker jobs. SIGTERM allows 100 s of grace with configured 60-second SDK timeouts;
network timeouts are not a guaranteed total wall-clock cap. A hard crash can still
leave an interrupted, possibly billed request. Exactly-once completion across a provider/network crash is not promised.
If AI is switched off, queued work waits without an API attempt. Polling and camera
capture remain independent.

## Daily sync — durable database, not an ephemeral CI runner

`deploy/run-daily.sh` executes the existing importer in an admin container sharing
**the same retained DB volume**. The host flock and existing DB sync lock prevent
overlap; endpoint state persists cooldowns/ETag/Last-Modified and Retry-After.
TCGCSV retrieval is no more frequent than 24 hours; unchanged data still yields a
dated snapshot with truthful provider/retrieval timestamps. Each provider/set import
is atomic, history append-only and replays idempotent. Last valid prices remain when
a provider fails. Partial failure/budget exhaustion returns a nonzero service exit.

After reviewing dry-run scope and authorizing free provider collection, run the
same command with `--execute`, verify results, and install `deploy/systemd/*` under
`/etc/systemd/system/`. Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tallybinder-sync.timer tallybinder-backup.timer
systemctl list-timers 'tallybinder-*'
journalctl -u tallybinder-sync.service --since yesterday
```

The sync timer starts after boot and then **24 hours after the prior run finishes**
to avoid jitter violating provider guidance; it drifts rather than promising a
fixed wall-clock minute. Endpoint cooldown/resume checkpoints survive reboot.
Do not enable unrestricted full-catalog sync. Manual sync is the same private shell
command; no HTTP admin control is exposed. Check set-level freshness/warnings in the
app and `/sync/status` while authenticated. Timer logs and failures require monitoring;
provider outages and VM downtime cannot be prevented by a scheduler.

## Complete backups and restore drill

Set up an existing **private** OCI Object Storage bucket in the home region and
scoped S3-compatible credentials. Store `deploy/backup.env.example` as root-only
`backup.env`. Create a separate strong `restic-password`; keep an encrypted recovery
copy **off the VM**, together with the repository endpoint/credentials. Losing this
key loses the encrypted backup. Scope credentials to the backup bucket; no public
objects or URLs. Confirm the 20 GB/50,000-request free allowance and lack of paid
upgrades in the actual account.

Initialize the designated private repository deliberately with `restic init`, then
run `deploy/run-backup.sh` and inspect its successful snapshot before enabling the
backup timer. **Do not** enable a timer that has no working off-VM repository.

The backup command uses SQLite's online backup API, checks integrity/foreign keys,
then includes all photo files referenced by that consistent snapshot. Photos are
immutable; concurrent later uploads do not invalidate the snapshot. The archive
contains SHA-256/size provenance, not only the DB. Local files are private; restic
encrypts off-VM storage. Uncompressed tar preserves block deduplication. The script
keeps two local archives only after a successful remote backup. It never auto-prunes
the remote repository. Monitor actual repository size and review retention before
quota exhaustion; free storage is not a billing cap on upgraded accounts.

Restore drill to an **unused** path:

```bash
# Recover the archive from the private restic repository to a private directory.
restic restore latest --target /private/restore-download
python -m cardscan.ops restore --archive /private/restore-download/.../tallybinder-....tar \
  --destination /srv/tallybinder/restore-drill-UNIQUE
```

The restore rejects traversal, links, duplicate members, wrong hashes and existing
destinations. Verify inventory quantities/selling prices, exact SKU results,
photos, provenance, history counts and schemas. For real recovery, stop API/worker,
retain the old data directory, select the restored directory in `compose.env`, fix
ownership, run migration/preflight, then restart. Never run two workers against a
restored/live copy that could both execute the same queued paid request. No restore
command silently replaces the live DB.

**Paid-job rollback safeguard:** every restore creates `.ai-restore-hold` and
quarantines restored queued/running jobs as interrupted. A snapshot cannot prove
which requests were executed after it was taken, and its daily ledger may be old.
The worker and API refuse new AI execution while this hold exists; the app reports
the pause. Reconcile the provider dashboard, deliberately set the remaining daily
budget (or wait for a new accounting day), and only then acknowledge:

```bash
docker compose --env-file /srv/tallybinder/config/compose.env -f deploy/compose.yml \
  run --rm --no-deps admin acknowledge-restore --confirm-cost-review
```

This logs local clearance and removes the hold; it does not execute a paid request
or requeue interrupted jobs. A new explicit per-card authorization is still required.
This also applies to an initial backup transfer: confirm no missing post-snapshot
vision usage before clearing it. Keep AI disabled until that review is complete.
The restored manifest retains the original archive hashes and records recovery
changes and the resulting DB hash; pricing history is not rewritten.

App configuration, DNS and recovery secrets need separate protected backups; they
are deliberately absent from the data archive. OCI volume backups are an additional
layer within the five-backup allowance, not a substitute for encrypted off-VM
application backups and a verified restore. RPO is approximately the last successful
daily backup; RTO depends on VM capacity. No zero-data-loss/disaster SLA is claimed.

## Safe redeployment and acceptance gate

Build images before stopping services. Back up, stop API/worker for schema changes,
apply migrations, run preflight and recreate code containers while retaining the
same data/TLS paths. Never run `docker compose down --volumes` or format/recreate the
data volume as an upgrade. Roll back code only if compatible with the current schema;
otherwise restore a tested snapshot into a separate path.

Complete this checklist on the **actual environment** before declaring success:

- [ ] Public HTTPS certificates and stable DNS; only intended ports exposed.
- [ ] Anonymous inventory/photos/catalog/docs denied; login, logout, expired session,
      origin rejection and no private CDN/API cache verified.
- [ ] No server credential in frontend assets or browser request URLs.
- [ ] Actual supported-size upload, private photos, CSV and cookie forwarding on Vercel.
- [ ] Physical iPhone Safari: Add to Home Screen, safe areas, front/back camera,
      orientation, retakes and photo-library permission fallback.
- [ ] Explicitly authorized real identification and condition jobs, catalog review,
      override, LP/MP repricing and human-approved listing.
- [ ] Persistent inventory after reload, quantity/price edit and export.
- [ ] Photos/inventory/history survive container recreation and backend/worker restart.
- [ ] No duplicated API attempt after a deliberately interrupted test job.
- [ ] Bounded actual provider sync updates the durable DB while lookups remain available.
- [ ] Successful private off-VM backup and restore drill, with quota monitoring.
- [ ] 100-card intake session; job budgets configured deliberately; errors isolated.

Automated local browser/container tests do not check any box requiring actual cloud
or physical iPhone evidence. No deployment success is claimed in this assignment.
