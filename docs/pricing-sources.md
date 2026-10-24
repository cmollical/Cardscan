# Pricing source research — 2026-10-24

## Decision

No source reviewed establishes a new developer's access to free, commercially
reusable, exact-printing NM/LP/MP/HP/DMG completed-sale evidence at scale.
Implement offline, manually verified ingestion first. Do not scrape marketplaces,
use undocumented endpoints, or treat an open-source wrapper as a pricing license.
Manual entry does **not** remove source restrictions. No real sales are bundled;
no external source is approved by the default permission registry.

“Verified” below means supported by the linked first-party documentation, **not**
a successful authenticated endpoint test or a legal opinion. Unknown permissions
are unresolved, never assumed granted. Recheck terms before enabling an adapter.

| Source | Documented programmatic access and limits | Condition/completed-sales support | Commercial use and prototype decision |
|---|---|---|---|
| TCGplayer | REST API exists; new access closed. No numerical rate limit verified in reviewed pages; obey approved account limits. | SKU pricing distinguishes product conditions; market aggregates are not individual completed transactions. Public guides are references, not an unrestricted feed. | Terms require preapproval and restrict combining prices and obtaining automated third-party copies. Disabled pending express permission. |
| eBay | Marketplace Insights sold-history API is restricted, not open to new users. Browse's published default is 5,000 calls/day for most methods; this is **not** sold-history access. | Sold evidence can contain price/date; raw-card condition and exact variants still require verification. Hidden accepted offers cannot be priced from the displayed asking amount. | API use requires the applicable license and production approvals; no blanket reuse grant verified. User Agreement bars automated collection without permission. No scraping adapter. |
| PriceCharting | Legendary plan currently $49/month includes price API/CSV. API: 1 request/second; CSV: 1/10 minutes. | Current estimates only, not historical sales through the Prices API. Ungraded and slab-grade fields, not five raw conditions. Shipping excluded by methodology. | Internal use under subscription; app sharing requires commercial license/written permission, price unpublished. Excluded from zero-cost prototype. |
| Pokémon TCG API | Documented unauthenticated limits: 1,000/day, 30/minute; existing keys default 20,000/day. Now deprecated; new registrations closed; existing keys through March 1, 2027. | Catalog plus TCGplayer aggregate variant prices; no raw-condition completed-sale feed established. | Do not infer upstream pricing rights from SDK licensing. Dataset repository's reviewed README did not establish a commercial data license. Do not make it a new core dependency. |
| TCGdex | Free REST/GraphQL, no key; no published hard limit; cache bulk needs. Database README declares MIT. | Catalog/variants/languages. Embedded TCGplayer/Cardmarket aggregates; no five-condition completed-sale feed documented. FAQ acknowledges incorrect marketplace mappings. | Prefer as a candidate metadata source with MIT notice retained. Third-party pricing/artwork rights are separate and not verified. Price fields disabled; exact variants require review. |
| Cardmarket | New API applications closed; public catalog/price-guide downloads advertised, updated daily. No numerical download rate limit verified. | Aggregates/trends, not independently attributable sold comps with all required conditions. | Public download availability verified; commercial redistribution/combination permission not established in reviewed pages. Disabled pending explicit terms review. |

## Primary sources

TCGplayer:
- [Access status](https://docs.tcgplayer.com/docs/getting-started)
- [SKU market prices](https://docs.tcgplayer.com/reference/pricing_getproductconditionprices-1)
- [SKU details](https://docs.tcgplayer.com/reference/catalog_getskus)
- [API terms, particularly Restricted Activities](https://help.tcgplayer.com/hc/en-us/articles/360061115874-TCGplayer-API-Terms-Conditions)

eBay:
- [Marketplace support and restricted-access notice](https://developer.ebay.com/api-docs/buy/ref-marketplace-supported.html)
- [Production requirements](https://developer.ebay.com/develop/get-started/get-started-on-a-buying-application)
- [Buy API limits](https://developer.ebay.com/develop/api/buy/api_call_limits)
- [User Agreement](https://www.ebay.com/help/policies/member-behavior-policies/user-agreement?id=5414)

PriceCharting:
- [Subscription plans](https://www.pricecharting.com/pricecharting-pro)
- [API fields, limits and commercial licensing](https://www.pricecharting.com/api-documentation)
- [Methodology](https://www.pricecharting.com/page/methodology)

Open catalogs:
- [Pokémon TCG API limits and deprecation notice](https://docs.pokemontcg.io/getting-started/rate-limits/)
- [Pokémon TCG API card fields](https://docs.pokemontcg.io/api-reference/cards/card-object/)
- [Pokémon TCG data repository](https://github.com/PokemonTCG/pokemon-tcg-data)
- [TCGdex database license statement](https://github.com/tcgdex/cards-database/blob/master/README.md)
- [TCGdex access, limits and mapping caveats](https://tcgdex.dev/faq)
- [TCGdex market field schema](https://tcgdex.dev/markets-prices)

Cardmarket:
- [API access](https://help.cardmarket.com/en/cardmarket-api)
- [Public downloads](https://news.cardmarket.com/en/Magic/were-making-the-price-guide-and-product-catalogue-available-for-download)
- [Daily public catalog and price exports](https://insight.cardmarket.com/en/Articles/scryfall-x-cardmarket)

## What is realistically automatable

Parsing an authorized export, validating explicit identities and conditions,
deduplication, currency checks, shipping normalization, median valuation, and audit
reporting are fully offline and free. Catalog lookup can be automated after a
reviewed metadata snapshot is supplied; it does not establish sales evidence.

Evidence acquisition and condition/printing adjudication remain manual until a
source grants suitable rights and access. A contributor's publicly published,
permissioned transaction ledger could qualify; no such real ledger was verified
in this research. A shop's private receipts do not satisfy this project's
public-data requirement by themselves. A source-specific adapter must establish
public availability, provenance and commercial reuse rights before approval.

PriceCharting is a useful potential reference, but its proprietary estimate and
ungraded bucket cannot validate condition-specific accuracy. TCGplayer's market
price likewise must not be presented as an individual completed sale. Neither
provider's accuracy for this cohort has been measured.
