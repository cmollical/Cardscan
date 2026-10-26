# Free-tier hosting comparison — checked October 26, 2026

All allowances below are from public official provider pages retrieved in this
assignment. **Documentation verified; cloud provisioning and cloud runtime untested.**
No paid plan, trial-funded deployment or commercial data rights are assumed.
[Retrieval URLs/status/content hashes](../research/evidence/cloud-hosting/official-documents-2026-10-26.json)
and [measured local requirements](../research/evidence/cloud-hosting/runtime-measurements-2026-10-26.json)
are retained. Provider terms and console eligibility must be checked again at setup.

## Architecture comparison

| Architecture | Recurring hosting within allowances | Persistent execution/storage | Full current workload | Changes and risks |
| --- | --- | --- | --- | --- |
| A: Vercel + managed free SQL/object/runtime | Several components offer $0 tiers; no complete unchanged stack established | PostgreSQL/object storage can be durable; free Python hosts may sleep or lack disk | **Not established**; not selected | PostgreSQL SQL/migration rewrite, object-store authorization, separate durable worker; smaller DB quotas and service caps |
| B: Vercel Hobby + OCI Always Free ARM VM | **$0 conditional on actual Always Free resources and personal Hobby eligibility** | VM processes, retained block volume, private filesystem photos | **Compatible in design and locally tested containers; cloud acceptance pending** | Preserves SQLite and providers; needs accounts, capacity, DNS/HTTPS, backups; idle reclamation and no free support |
| C: complete stack on same free ARM VM | **$0 under the same OCI conditions** | Same persistent runtime/volumes; Next additionally on VM | **Compatible in design; local images build** | One less platform; frontend build/Node RAM on VM; same idle/capacity risks |

B is recommended to honor the Vercel preference. C is the supplied fallback if
Vercel real-world proxy/upload/cookie testing fails or personal-use eligibility ends.
A is not represented as ready merely because separate services have free tiers.

## Providers and actual limits

| Provider / official reference | Free allowance relevant here | Persistence, execution, idle and bandwidth | Suitability |
| --- | --- | --- | --- |
| [Vercel Hobby](https://vercel.com/docs/plans/hobby) | Personal/non-commercial only; 100 GB fast data transfer, 10 GB origin transfer, 1M CDN requests, 1M Function invocations, 4 active CPU hours, 360 GB-hours Function memory/month | CDN serves frontend; Function memory/filesystem is not durable storage; Hobby Function duration up to 300 s with applicable runtime settings; usage exhaustion can suspend features until reset | Frontend only. No SQLite, media or AI worker in Functions. No autoswitch to Pro |
| [Vercel limits](https://vercel.com/docs/limits), [Function limitations](https://vercel.com/docs/functions/limitations) | External-rewrite timeout **120 s**; **Function** request/response maximum **4.5 MB** | The latter must not be generalized as a documented rewrite limit. This app uses external rewrites, not a custom Function proxy | Verify 8 MB upload, Set-Cookie/Cookie forwarding, CSV and auth on the actual deployment. Worker makes enqueue/poll short |
| [OCI Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) | Current page: **1,500 OCPU-hours + 9,000 GB-hours/month = 2 ARM OCPUs / 12 GB RAM**; 200 GB boot+block volume combined in home region; 5 volume backups; 20 GB Object Storage combined; 50,000 Object Storage API requests/month; 10 TB outbound/month | Persistent Linux processes and volumes; no Function timeout; own scheduling. Idle instances may be reclaimed after a 7-day low-utilization period. Capacity may be unavailable. 2 AMD micro instances are also listed but have only 1 GB RAM each | Best preservation of this application. Use only Always Free-tagged resources and verify $0 console estimate. Do not use older 4-core/24-GB claims |
| [OCI FAQ](https://www.oracle.com/cloud/free/faq/) | Eligibility and signup verification; free-tier customers lack paid support | Home-region choice and available ARM capacity matter. Verification card/identity may be required; do not upgrade merely to get capacity | Conditional availability, not an SLA. Backups must be off-VM; do not generate artificial load to evade idle policy |
| [Supabase](https://supabase.com/pricing) | 500 MB DB/project; 1 GB file storage; 5 GB egress + 5 GB cached egress; free automatic DB backups not included | Free project can pause after 1 week inactivity. Managed PostgreSQL/private object storage are useful components; they do not run this filesystem/SQLite Python worker unchanged | Initial data can fit, but daily history exceeds 500 MB quickly; requires tested DB and object-storage migration not justified for first deployment |
| [Neon](https://neon.com/pricing) | Current page: 100 projects, **100 CU-hours/month/project, 1 GB/project**, sizes up to 2 CU/8 GB; advertised 5 GB object storage and backend beta features | PostgreSQL scale-to-zero; not evidence of compatibility with this FastAPI/filesystem worker. Project quotas do not pool into one unlimited DB | Free SQL candidate for a later migration; daily history outgrows 1 GB. Advertised newer backend features not tested |
| [Cloudflare R2](https://developers.cloudflare.com/r2/pricing/) | Standard: 10 GB-month, 1M Class A and 10M Class B operations/month; no R2 egress charge | Private durable objects, not a Python host or SQL database; usage beyond allowance is billable. Infrequent Access does not share this free tier | Viable future media/backup component, but not provisioned; avoid assuming a zero-dollar spending cap |
| [Cloudflare Workers](https://developers.cloudflare.com/workers/platform/limits/) | Free 100,000 requests/day; 128 MB memory and 10 ms CPU/request | HTTP I/O wait differs from CPU limit; do not claim every request is limited to 10 ms wall time. Persistent Python processes, local SQLite and Pillow filesystem uploads are not a drop-in fit | Would require substantial runtime/storage/queue changes; not selected |
| [Render Free](https://render.com/docs/free) | 750 free instance-hours/workspace/month | Spins down after 15 minutes without inbound traffic; filesystem ephemeral; persistent disks unavailable on free web services; free PostgreSQL expires after 30 days | Fails persistence/reliable worker requirements for this app |
| [Google Cloud free](https://cloud.google.com/free/docs/free-cloud-features) | One non-preemptible e2-micro within listed US regions; 30 GB-month standard persistent disk; 1 GB outbound/month excluding certain destinations | Small shared compute/RAM and limited egress; other resources such as public networking must be priced separately | Not established as a complete $0 deployment for photo intake and this stack; do not treat all attached networking as free |

The chosen VM's logical data volume is **100 GB**, plus 50 GB boot = 150 GB within
200 GB combined. It is deliberately not the full allowance. Container RAM limits
(API 2 GB, worker 2 GB, optional frontend 1 GB, proxy 256 MB) fit in 12 GB with OS
headroom. ARM build/runtime behavior still needs testing on the actual VM; local
image tests use the execution environment's architecture.

## Capacity estimates, not guarantees

Measured 15-set DB: **58,052,608 bytes (55.36 MiB)**, 3,509 products, 21,735 SKUs,
25,812 observations and 62 source documents. Observation table plus **all its
indexes** uses 29,863,936 bytes: **1,156.98 bytes/observation**. Source-document
pages currently occupy 13,357,056 bytes; this is not their future change rate.

| Workload | Estimate / consequence |
| --- | --- |
| Current ~25,812 generic+SKU rows captured daily | ~29.86 MB/day; **10.90 GB/year** of observation/index pages alone |
| 400,000 SKU rows captured daily | ~462.79 MB/day; **168.92 GB/year**, excluding generic rows, catalog, source exports, WAL and backups |
| Current 30 / 90 / 180 days | ~0.90 / 2.69 / 5.38 GB history pages alone; measured row-size projection |
| 100 cards, 2 photos/card | Assuming 0.3–1.5 MB/photo, 60–300 MB; planning assumption, not measured real-photo intake |
| 500 cards, 2 photos/card | Same assumption: 0.3–1.5 GB; endpoint's conservative 8 MB/photo ceiling would allow up to 8 GB |
| 100 sequential cards with both AI jobs | 200 explicitly paid jobs; default daily 30-attempt/$5 safeguards intentionally require operator budget review before that many AI requests |

For frequent 100-card sessions, repeated photo previews can make Vercel's 10 GB
origin-transfer allowance the first bottleneck even when the VM is well below its
10 TB allowance. Measure real transfer in the Vercel dashboard. If the expected
monthly photo traffic exceeds Hobby limits, choose Option C before intake rather
than upgrading or accepting a service cutoff. No actual cloud bandwidth measurement
has been made.

The manual 100-card workflow does not require 200 AI requests and remains available
while research is queued. Raising AI budgets is a deliberate paid-usage decision,
not an automatic deployment change. Zero-cost **hosting** does not mean zero AI cost.

Current coverage and months of history are practical on the proposed disk. A full
year of 400,000+ daily SKUs with generic history, sources, photos and backups is
**not guaranteed to fit the free allowance**. Retain append-only semantics; do not
silently delete history to meet a quota. Revisit storage architecture or obtain
paid-storage approval before expanding. No full-catalog import is enabled here.

Off-VM restic repositories must stay inside OCI's 20 GB/50,000-request allowances;
backup deduplication savings have **not** been measured against that service. The
implementation uses uncompressed checksummed tar with restic encryption/deduplication,
not daily opaque compressed archives. Two local archives are retained after remote
success; remote pruning is never automatic. Monitor repository size and quota, and
stop/alert on failure instead of assuming free storage is unlimited.

## Lowest-cost practical fallback

If OCI signup, capacity or reclamation is unacceptable, this same VM/container
architecture can run on a small paid persistent VPS after explicit authorization.
[Hetzner's official cloud page](https://www.hetzner.com/cloud/) was retrieved but its
dynamic pricing content did not establish a trustworthy entry-plan price in this
execution; do not invent a quote. Obtain a current quote including persistent disk,
IPv4, backups and tax. A paid VPS is an operational fallback, **not** authorized here.
No inspected free service gives a guarantee of permanent uptime and unlimited data.
