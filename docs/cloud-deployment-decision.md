# Deployment decision — TallyBinder, October 26, 2026

**Recommended first deployment: Vercel Hobby frontend + one Oracle Cloud Always
Free ARM VM (Option B).** The VM owns FastAPI, SQLite, private photos, one durable
vision worker, and bounded daily synchronization. Vercel runs the existing Next
application and same-origin external API rewrites; no Python/SQLite/AI work runs
inside Vercel Functions. Option C runs the same frontend on that VM if Vercel
eligibility or real proxy testing prevents use of Option B.

This decision precedes the deployment compatibility implementation. No account,
resource, public deployment or paid request is authorized by this document.

## Why

The current app uses filesystem-backed SQLite WAL, immutable private JPEGs,
revision-checked inventory, long-lived Python execution and CLI synchronization.
A small persistent ARM VM preserves all of that without migrating money/provenance
semantics to PostgreSQL or splitting photo access across services. 2 ARM cores,
12 GB RAM and a 50 GB boot + 100 GB data volume fit the currently published OCI
free allowance; the unused 50 GB is headroom, not automatic permission to allocate.
Vercel Hobby is eligible only while this remains personal and non-commercial.

Published Vercel external-rewrite proxy timeout is 120 seconds. Job submission
returns queued state immediately; the VM worker owns the OpenAI request and the
browser polls. The 4.5 MB Function payload limit is a **Function** limit, not proof
that external rewrites share it. Real 8 MB upload, Cookie/Set-Cookie forwarding,
CSV and HTTPS tests must pass on the actual Vercel deployment before declaring it
accepted. If those fail, use Option C; do not silently lower supported functionality.

## Qualification

This is a technically viable **conditional $0/month** architecture, not guaranteed
capacity or uptime. OCI documents free capacity shortages and reclamation of idle
instances. User eligibility, home-region availability, a free/existing DNS hostname,
private off-VM backup setup and actual cloud acceptance remain blockers. No free
provider examined establishes a guarantee of permanent availability or unlimited
history. See [provider comparison](free-tier-hosting-research.md) and
[deployment runbook](cloud-deployment.md).

The provider documents retrieved in this task list **1,500 OCPU-hours and 9,000
GB-hours/month: 2 OCPUs/12 GB**, not the older 4/24 figures. The console's actual
Always Free designation and $0 estimate must be checked before provisioning.
