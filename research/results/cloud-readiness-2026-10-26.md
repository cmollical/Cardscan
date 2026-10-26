# TallyBinder cloud readiness — October 26, 2026

**Prepared and locally validated; no public deployment.** No cloud account,
provider resource, DNS record, public HTTPS endpoint, paid plan or paid AI request
was created. The managed environment reported no cloud credential/identity bindings.
The owner must authorize provisioning/publishing and provide secure account access.

## Recommendation and implementation

Use Vercel Hobby for this personal Next frontend plus a single OCI Always Free
ARM VM for FastAPI, persistent SQLite/photos, a serial vision worker and systemd
timers. An optional full-VM Next configuration is supplied. Current official OCI
docs list **2 OCPUs/12 GB**, 200 GB combined boot/block, 20 GB Object Storage and
10 TB outbound. Free capacity, identity eligibility and idle reclamation remain
real limitations; zero monthly hosting is conditional, not an uptime guarantee.

Implemented:

- Non-root production API and Next standalone images; cloud runtime dependency lock.
- Compose API/worker/private admin/proxy services and a single-VM frontend profile.
- Caddy HTTPS configuration, durable data/TLS paths, health checks and worker heartbeat.
- Cloud fail-closed configuration: distinct strong secrets, exact HTTPS origins,
  external job worker and authentication for all private API reads/writes/photos.
- Secure HttpOnly/SameSite/host-only browser sessions, logout, secret rotation,
  request limits, no private CDN cache and no credential in frontend storage.
- Migration 006: frozen job model/rates/limits and execution-day accounting. API
  restart leaves external queued work intact. Serial worker never auto-retries
  interrupted requests; unknown costs retain reserve. Per-scan usage remains tracked.
- Explicit currently-imported daily set scopes, 64-request cap, resume/cooldowns,
  persisted failure state and private manual/timer execution against the durable DB.
- Consistent online SQLite + immutable photos backup with integrity/foreign-key,
  checksum, path and restoration checks; private encrypted off-VM restic runbook.
- Disaster restore quarantines pending jobs and holds AI until explicit provider-cost
  review, preventing older queued authorizations from being automatically replayed.

No pricing engine, matching rules, image identification prompt, provider price
semantics, research artifacts or historical observations were replaced.

## Actual automated results

| Validation | Actual outcome |
| --- | --- |
| Full Python suite | **291 passed**: 272 prior + 19 new cloud/recovery tests |
| Frontend unit tests | **14 passed** |
| Mobile Chromium browser tests | **4 passed**, including cloud login without localStorage key persistence |
| TypeScript | Passed |
| Next production build | Passed |
| Docker API and frontend production images | Built successfully |
| Container contract | Passed: 10 named checks, AI disabled, private localhost networking only |
| Compose API-only and full-VM configurations | Both validate |
| Caddy API-only and full-VM configurations | Both validate; no real certificate issuance |
| Linux ARM64 Python 3.12 dependency wheels | Resolved/downloaded; not native ARM runtime validation |
| Real OpenAI calls | **0** |
| Public deployment / actual cloud sync | **Not performed** |
| Physical iPhone acceptance | **Not performed** |

The repeatable container contract uses saved real five-card provider excerpts and
synthetic JPEGs. It tests authentication, worker startup/restart heartbeat, Cookie
header forwarding through the real Next server, **7.9 MB** synthetic-image upload,
exact Base Set LP SKU **2999653** at the dated **$527.70** reference, inventory/CSV,
API restart and full container replacement, photo persistence and complete restore.
It preserves **42 fixture history rows**. It does not prove actual Vercel payload
behavior, browser Secure-cookie acceptance over cloud HTTPS, real card condition
accuracy or real AI prices. The local transport test uses localhost HTTP with
explicit Cookie headers; actual browser HTTPS acceptance remains required.

Tests exposed and fixed image-source ownership for the non-root user and ownership
of transferred WAL/SHM files. Monetary assertions compare precise decimals rather
than incorrectly rejecting equivalent strings `527.7` and `527.70`.

## Existing full dataset preservation

A SQLite-consistent copy of the original 15-set DB was migrated from schema 5 to 6
only after creating a full pre-migration archive. Original files were retained.

- 3,509 products, 21,735 SKUs, **25,812 historical observations**.
- Observation-row hash before and after:
  `0edb007e86e893bcb365e4872a9ab1235b1c0bf2181579be5be42cd6cfdefd5e`.
- Full 58,060,800-byte pre-migration archive restored successfully into an unused
  directory: 3,509 products and all 25,812 history rows; no card photos existed in
  that source DB. Synthetic photo/inventory restoration is separately tested.
- Preflight passed on the migrated copy.
- Daily plan: **15 existing sets, at most 59 export/metadata requests**, configured
  budget 64. Only dry-run executed; no live pricing provider requests occurred.

The full DB, source payloads, archives and photographs remain ignored by Git.
[Portable local validation metadata](../evidence/cloud-hosting/local-validation-2026-10-26.json)
records test results separately from actual cloud acceptance.

## Capacity and remaining blockers

Measured source DB is 58,052,608 bytes. All observation indexes included, the measured
storage is 1,156.98 bytes/row. This projects to ~10.90 GB/year for the current daily
row count, and **~168.92 GB/year for 400,000 daily SKU rows alone**. Neither 400,000+
SKU annual history plus photos/backups nor unlimited Vercel photo traffic is promised
inside free tiers. Review expansion before quota exhaustion; never delete history
or upgrade hosting automatically.

Still required: OCI/Vercel owner accounts and explicit deployment approval; free
home-region ARM capacity; a free/existing DNS hostname; private backup repository
and recovery-key setup; actual HTTPS upload/cookie/media probes; real provider sync;
separately authorized real vision calls; restart/redeployment checks on the actual
volume; physical iPhone Safari/PWA and 100-card acceptance.

[Deployment steps and exact owner actions](../../docs/cloud-deployment.md) ·
[Official free-tier comparison](../../docs/free-tier-hosting-research.md) ·
[Architecture decision](../../docs/cloud-deployment-decision.md)
