# Source-verification implementation retained alongside AI estimation

The earlier source-verification work is preserved in `cardscan/references/`.
It is separate from the new experimental AI synthesis provider and from sold-comp
valuation. Its tests use explicitly synthetic saved JSON and mocked HTTP responses.

`ReferenceSourceAdapter` defines extraction; `TCGdexAdapter` reads a documented
single-card JSON endpoint. `ReferenceVerifier` applies source permission/purpose,
exact identity, condition, currency, price basis, freshness and field-provenance
checks. `ReferenceCandidate.from_ai` retains model fields as claims, never source
facts. A bounded HTTPS JSON transport refuses redirects, unapproved endpoints,
oversized/invalid responses and HTML challenges. No credentials, retries or full
page storage. Minimal audit JSON is append-only by filename, hash-bound and stored
outside git by default. Source hashes identify received bytes, not a retained page.

Status transitions distinguish permission_blocked, retrieval_failed, rejected,
context_only, verified and duplicate. Duplicate tracking is invocation-local, not
a price cache. Each extracted field preserves value, direct/structured/inferred/
AI/missing/contradictory basis, locator, source URL, content hash and extraction
method. Only source-supported fields can satisfy strict reference verification.

## Actual limited research observation (2026-10-25)

One implemented-adapter retrieval succeeded at
https://api.tcgdex.net/v2/en/cards/sv03.5-199
at **2026-10-25T14:34:29.396554+00:00**. The prior exploratory request also returned
this product, but no second implemented-adapter live verification was completed.
Content SHA-256: `9943d250bab633b5d7774bd396ed6be544f656256057f4b661d432e25b74f9e2`.

Source JSON reports Charizard ex, set 151, local ID 199, official set count 165,
holofoil price variant, USD unit and marketplace product ID 517045. The price
field is `/pricing/tcgplayer/holofoil/marketPrice`; update timestamp is
**2026-10-14T22:55:09.651Z**. The actual extracted amount is retained in the local
audit, not republished here as a pricing dataset or a licensed commercial quote.

Outcome: **context_only**, no valuation. Price was independently observed in the
TCGdex response; it was not checked against the upstream TCGplayer marketplace.
The response does not establish condition, priced-item language, edition, grading
status or shipping/tax exclusion. Its update date also exceeds the seven-day
reference window. Metadata locale and firstEdition=false are retained as such,
not converted into price-language or standard-edition claims. A generic condition
label is not invented: condition_scope remains unknown.

Audit: `local-evidence/source-verification/charizard-2026-10-25.json` (ignored by git).
Source API charge for this request: $0; about 0.33 seconds in the completed CLI
run. Cost per successful NM verification remains unmeasured because there were
zero successful NM verifications. No paid OpenAI requests were made.

## Access and licensing findings

| Source | Confirmed first-party capability / limitation | Adapter policy |
| --- | --- | --- |
| TCGplayer | [API terms](https://help.tcgplayer.com/hc/en-us/articles/360061115874-TCGplayer-API-Terms-Conditions) restrict automated collection outside approved API access | No approved access; direct pricing-page retrieval disabled, not attempted in this assignment |
| PriceCharting | [API documentation](https://www.pricecharting.com/api-documentation) describes subscription pricing access; reviewed pricing uses generic ungraded/grade buckets | No applicable subscription/permission established; disabled. A page's sale rows or ungraded guide do not establish an NM benchmark |
| TCGdex | [FAQ](https://tcgdex.dev/faq) documents free keyless API; [market integration](https://tcgdex.dev/markets-prices) documents embedded marketplace price fields | Limited research API retrieval enabled; minimal local audit only. Upstream commercial pricing rights unresolved, commercial purpose blocked |
| JustTCG | [Schema](https://justtcg.com/docs/schema/variant) documents condition/printing variants and USD current price; [quickstart](https://justtcg.com/docs/quickstart) requires a key | No key/subscription configured, disabled; no request attempted |

[JustTCG terms](https://justtcg.com/terms) reserve commercial display, derived
analytics, data combination and storage rights to paid tiers, with restrictions
on substitute feeds and raw-data exports. Its free tier is personal/non-commercial.
Documented capability is not a successful endpoint test or evidence of upstream
accuracy. No subscription was created or purchased.

The TCGdex documentation is treated as permission for its intended documented API
research use, not proof of upstream commercial rights. Its metadata/code license
does not automatically license third-party prices. This implementation does not
authorize full-page storage, data resale or unrestricted redistribution. A
commercial adapter requires a reviewed source-specific permission record.

Technical access, data completeness and licensing remain distinct: TCGdex retrieval
worked but lacks condition semantics; TCGplayer is blocked by missing permission;
PriceCharting has access/licensing and condition limitations; JustTCG is a promising
condition-aware licensed route that remains untested without credentials.

The new AI market-estimation experiment deliberately accepts weaker reported
evidence for labeled estimates, while preserving this stricter independent
verification path. Neither method should describe the observed generic price as
an established NM valuation.
