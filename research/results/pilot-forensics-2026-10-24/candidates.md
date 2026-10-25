# Candidate-by-candidate forensic table

Every amount, date, source access description and condition below is an **unverified model claim** extracted from the original ledger. No source document or original search snippet is retained. “Potential reference” means a discovery lead, not a Tier 2 benchmark. No new marketplace fetches were used to rewrite historical evidence.

The full structured record, target, claim hash, raw JSON pointer, actual rejection and separate offline replay are in [evidence-analysis.json](evidence-analysis.json). All 20 prices, printings and conditions remain independently unsubstantiated.

Source types: PC = PriceCharting aggregator; RH = Rip & Hold aggregator; LS = lastsold.com aggregator; CA = CollectAIO aggregator; EB = eBay primary marketplace. Aggregator type is based on the reported product/sales-page role, not an endorsement of data or permission. The underlying marketplace for aggregator rows is claimed to be eBay; no original transaction link was returned.

## Retained candidates (13)

| ID / card | Source and original URL | Claimed item amount / currency / sale date | Claimed condition and printing support | Actual deterministic rejection | Analysis category |
| --- | --- | --- | --- | --- | --- |
| C1 / modern-common | [PriceCharting](https://www.pricecharting.com/game/pokemon-obsidian-flames/charmander-26) | 0.99 / USD / 2026-09-26 | Title paraphrase claims NM; no original title or non-holo evidence retained. | not an explicit single-card transaction; missing genuine source record ID | Unverified potential lead (claimed sale) |
| C2 / modern-common | [PriceCharting](https://www.pricecharting.com/game/pokemon-obsidian-flames/charmander-26) | 1.16 / USD / 2026-09-25 | Paraphrase names card only; structured NM/non-holo unsupported by retained source material. | not an explicit single-card transaction; missing genuine source record ID | Unverified potential lead (claimed sale) |
| C3 / modern-common | [PriceCharting](https://www.pricecharting.com/game/pokemon-obsidian-flames/charmander-26) | 1.00 / USD / 2026-09-13 | Paraphrase names card only; structured NM/non-holo unsupported by retained source material. | not an explicit single-card transaction; missing genuine source record ID | Unverified potential lead (claimed sale) |
| C4 / modern-common | [PriceCharting](https://www.pricecharting.com/game/pokemon-obsidian-flames/charmander-26) | 0.99 / USD / 2026-09-11 | Paraphrase calls it single-card but bundle is null; no original condition/finish support. | not an explicit single-card transaction; missing genuine source record ID | Unverified potential lead (claimed sale) |
| M1 / modern-chase | [PriceCharting](https://www.pricecharting.com/game/pokemon-scarlet-%26-violet-151/charizard-ex-199?q=charizard+ex+199) | 269.29 / USD / 2026-10-19 | Paraphrase says NM-MT; mapping to NM is not independently supported. | not an explicit single-card transaction; card-only paid price unconfirmed; missing genuine source record ID | Unverified potential lead (claimed sale) |
| M2 / modern-chase | [PriceCharting](https://www.pricecharting.com/game/pokemon-scarlet-%26-violet-151/charizard-ex-199?q=charizard+ex+199) | 329.99 / USD / 2026-10-18 | Explicit contradiction: NM field versus exact raw condition missing. | not an explicit single-card transaction; card-only paid price unconfirmed; missing genuine source record ID | Unverified potential lead (claimed sale) |
| M3 / modern-chase | [PriceCharting](https://www.pricecharting.com/game/pokemon-scarlet-%26-violet-151/charizard-ex-199?q=charizard+ex+199) | 290.00 / USD / 2026-10-18 | Explicit contradiction: NM field versus exact raw condition missing. | not an explicit single-card transaction; card-only paid price unconfirmed; missing genuine source record ID | Unverified potential lead (claimed sale) |
| M4 / modern-chase | [Rip & Hold](https://ripandhold.com/cards/charizard-ex-151-199/charizard-ex-151-199-unlimited) | 365.00 / USD / 2026-09-30 | Explicit contradiction: NM field versus only raw/ungraded known. | not an explicit single-card transaction; card-only paid price unconfirmed; missing genuine source record ID | Unverified potential lead (claimed sale) |
| M5 / modern-chase | [Rip & Hold](https://ripandhold.com/cards/charizard-ex-151-199/charizard-ex-151-199-unlimited) | 280.00 / USD / 2026-09-20 | Explicit contradiction: NM field versus only raw/ungraded known. | not an explicit single-card transaction; card-only paid price unconfirmed; missing genuine source record ID | Unverified potential lead (claimed sale) |
| M6 / modern-chase | [Rip & Hold](https://ripandhold.com/cards/charizard-ex-151-199/charizard-ex-151-199-unlimited) | 335.50 / USD / 2026-09-15 | Explicit contradiction: NM field versus only raw/ungraded known. | not an explicit single-card transaction; card-only paid price unconfirmed; missing genuine source record ID | Unverified potential lead (claimed sale) |
| G1 / first-edition-gengar | [CollectAIO](https://www.collectaio.com/item/fossil-gengar-5-05-62) | 335.62 / USD / 2026-09-06 | LP/First Edition asserted by paraphrase only. Card-only flag false despite summary mentioning separate shipping. | card-only paid price unconfirmed; missing genuine source record ID | Unverified potential lead (claimed sale) |
| G2 / first-edition-gengar | [lastsold.com](https://lastsold.com/en/sets/fossil/gengar-5-1st) | 739.21 / unknown currency / 2026-10-22 | RAW LP asserted by paraphrase; original currency unknown. | card-only paid price unconfirmed; missing genuine source record ID; USD comparable required; no inferred FX conversion | Unverified potential lead (claimed sale) |
| G3 / first-edition-gengar | [PriceCharting](https://www.pricecharting.com/game/pokemon-fossil/gengar-1st-edition-5) | 602.88 / unknown currency / unknown date | LP asserted by paraphrase; sale date and currency unknown. Recent-sales row is not a published benchmark. | card-only paid price unconfirmed; missing genuine source record ID; USD comparable required; no inferred FX conversion; missing or invalid actual sale date | Unverified potential lead (claimed sale) |

## Discarded response candidates (7)

These candidates were recoverable from raw output text in SQLite. Their candidate-level reasons below are an **offline replay**, not reasons evaluated during the original run. Both responses failed the provider’s output-item count gate before candidate validation.

| ID / card | Source and original URL | Claimed item amount / currency / sale date | Claimed condition and printing support | Provider rejection / offline replay | Analysis category |
| --- | --- | --- | --- | --- | --- |
| V1 / vintage-charizard-lp | [lastsold.com](https://lastsold.com/en/sets/base-set/charizard-4) | $532.98 / USD / 2026-10-07 | LP claimed; missing_information admits Unlimited is not explicit. Price includes dollar symbol. | Whole response: Search call count outside configured limits. Offline replay: missing genuine source record ID; invalid money | Unverified potential lead (claimed sale) |
| V2 / vintage-charizard-lp | [lastsold.com](https://lastsold.com/en/sets/base-set/charizard-4-play) | $498.18 / USD / 2026-10-22 | LP claimed; completed-sale status explicitly uncertain despite completed_sale kind. Dollar-symbol price. | Whole response: Search call count outside configured limits. Offline replay: missing genuine source record ID; invalid money | Unverified potential lead (claimed sale) |
| V3 / vintage-charizard-lp | [lastsold.com](https://lastsold.com/en/sets/base-set/charizard-4) | $449.36 / USD / 2026-10-08 | LP claimed; both English and Unlimited explicitly uncertain. Dollar-symbol price. | Whole response: Search call count outside configured limits. Offline replay: missing genuine source record ID; invalid money | Unverified potential lead (claimed sale) |
| V4 / vintage-charizard-lp | [lastsold.com](https://lastsold.com/en/sets/base-set/charizard-4) | $532.98 / USD / 2026-10-07 | Same source URL, date and amount as V1; not another comp. Language/edition uncertain. Dollar-symbol price. | Whole response: Search call count outside configured limits. Offline replay: missing genuine source record ID; invalid money | Unusable duplicate of V1 |
| J1 / japanese-charizard | [eBay](https://www.ebay.com/itm/388184641220) | 699.99 / USD / 2026-09-01 | Near mint or better is a source-label claim, not canonical NM; no independent page. Promising primary-source lead. | Whole response: Search call count outside configured limits. Offline replay: condition mismatch or unknown | Unverified potential lead (claimed sale) |
| J2 / japanese-charizard | [eBay](https://www.ebay.com/itm/314651077203) | 735.99 / USD / unknown date | Unverified buy-it-now ask; bundle false conflicts with missing bundle confirmation. | Whole response: Search call count outside configured limits. Offline replay: condition mismatch or unknown; not a completed sale; missing or invalid actual sale date | Unverified active ask |
| J3 / japanese-charizard | [eBay](https://www.ebay.com/itm/298489269956) | 399.99 / USD / unknown date | Unverified ask; bundle false conflicts with missing bundle confirmation; offer versus ask uncertain. | Whole response: Search call count outside configured limits. Offline replay: condition mismatch or unknown; not a completed sale; missing or invalid actual sale date | Unverified active ask |

## Classification totals

| Mutually exclusive analysis bucket | Retained 13 | Discarded 7 | All 20 |
| --- | ---: | ---: | ---: |
| verified_completed_sales | 0 | 0 | 0 |
| verified_published_references | 0 | 0 | 0 |
| unverified_potential_references | 13 | 4 | 17 |
| active_listings | 0 | 2 | 2 |
| incorrect_or_mismatched_cards | 0 | 0 | 0 |
| unusable_evidence | 0 | 1 | 1 |

“Incorrect or mismatched cards = 0” means no mismatch was independently established; it does not mean exact-card matching was verified. Two active asks are model-classified, not verified as currently active. The duplicate finding compares retained claims, not proven transactions. None of the 18 sale claims is a published market benchmark. Reclassifying those rows cannot create a verified reference price.

All 13 actual sold-comp rejections were appropriate. A marketplace ID is not a Tier 2 requirement, but these were claimed individual sales with neither source corroboration nor an alternative verified provenance. The two response-wide call-count rejections were overly broad: each counted an unfinished open-page attempt as a processed call. Correcting that alone yields no verified comp. J1 still needs canonical source-condition review and page corroboration; V1–V4 have further money/provenance/identity issues.
