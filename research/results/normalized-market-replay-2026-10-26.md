# Original-response normalization replay

No paid API calls. Original final output text is preserved unchanged and hash-checked. All amounts remain model proposals, not verified market values.

| Card | Original proposal | Original status | Revised status | Display for review | Approved valuation |
| --- | --- | --- | --- | --- | --- |
| modern-common | 0.35 | invalid_estimate | insufficient_evidence | none | none |
| modern-chase | 345 | invalid_estimate | provisional_estimate | 345 USD | none |
| vintage-charizard-lp | $365 | invalid_estimate | insufficient_evidence | none | none |
| first-edition-gengar | $320 | invalid_estimate | provisional_estimate | 320 USD | none |
| japanese-charizard | 390 | invalid_estimate | provisional_estimate | 390 USD | none |

## Measured before and after

| Metric | Original | Normalized |
| --- | ---: | ---: |
| Model proposals | 5 | 5 |
| Structurally parseable proposals | 5 | 5 |
| Complete decimal-parsed proposal/range | 3 | 5 |
| Retained evidence rows | 20 | 20 |
| Decimal-parsed source prices | 6 | 20 |
| Usable estimates | 0 | 0 |
| Provisional estimates | 0 | 3 |
| Explicit insufficient-evidence outcomes | 0 | 2 |

The original run had 5 invalid-estimate outcomes, not explicit model abstentions. They are not retroactively relabeled as insufficient-evidence outcomes.

Remaining substantive findings: 3 rows with contradictions; 1 cross-source price-spread conflicts; 1 known condition mismatch rows. The old validator did not measure a directly comparable conflict count.

## Per-card decisions

### modern-common

**insufficient_evidence**. Original estimate and range: 0.35 (0.25–0.60).

Remaining decision errors: no_identifiable_eligible_priced_anchor, no_explicit_requested_condition_anchor.
Warnings: Original support IDs resolve to multiple rows; all rows retained, no invented independence; Some model-designated support is excluded; proposal retained for review only if other eligible anchors support it.

| Row | Source | Normalized price | Evidence classification | Exclusion / uncertainty |
| --- | --- | --- | --- | --- |
| 0 | [PriceCharting](https://www.pricecharting.com/game/pokemon-obsidian-flames/charmander-26) | 1.07 USD | unverified_published_reference_claim | representation_unresolved: number: Collector denominator missing or number unrecognized; missing_identity:language; collector_denominator_missing; missing_identity:edition; missing_identity:finish; freshness_unknown |
| 1 | [PriceCharting](https://www.pricecharting.com/game/pokemon-obsidian-flames/charmander-26) | 0.34 USD | unverified_completed_sale_claim | representation_unresolved: number: Collector denominator missing or number unrecognized; collector_denominator_missing; missing_identity:edition; missing_identity:finish |
| 2 | [PriceCharting](https://www.pricecharting.com/game/pokemon-obsidian-flames/charmander-26) | 0.40 USD | unverified_completed_sale_claim | representation_unresolved: number: Collector denominator missing or number unrecognized; collector_denominator_missing; missing_identity:edition; missing_identity:finish |
| 3 | [eBay](https://www.ebay.com/p/10062149619) | 1.50 USD | active_asking_price | asking_or_unknown_context_not_market_anchor; missing_identity:language; missing_identity:edition; missing_identity:finish; freshness_unknown |
| 4 | [eBay](https://www.ebay.com/p/10062149619) | 0.99 USD | active_asking_price | asking_or_unknown_context_not_market_anchor; missing_identity:language; missing_identity:edition; missing_identity:finish; freshness_unknown |

### modern-chase

**provisional_estimate**. Original estimate and range: 345 (320–370).

Remaining decision errors: none; review warnings still apply.
Warnings: Source prices and source facts remain unverified AI claims; Missing identity/freshness fields remain unknown.

| Row | Source | Normalized price | Evidence classification | Exclusion / uncertainty |
| --- | --- | --- | --- | --- |
| 0 | [TCGplayer search result for Charizard ex - 199/165](https://www.tcgplayer.com/search/pokemon/product?q=Charizard+ex+-+199%2F165) | 366.83 USD | unverified_published_reference_claim | missing_identity:edition; freshness_unknown |
| 1 | [PriceCharting card page for Charizard ex #199](https://www.pricecharting.com/game/pokemon-scarlet-%26-violet-151/charizard-ex-199?q=charizard+ex+199) | 350.00 USD | unverified_completed_sale_claim | missing_identity:edition; freshness_unknown |
| 2 | [ValueMyCard page for Charizard ex #199/165](https://valuemycard.com/card/517045-charizard-ex-pokemon-sv-scarlet-violet-151) | 307.49 USD | unverified_published_reference_claim | missing_identity:language; missing_identity:edition |

### vintage-charizard-lp

**insufficient_evidence**. Original estimate and range: $365 ($345–$460).

Remaining decision errors: no_identifiable_eligible_priced_anchor, no_explicit_requested_condition_anchor.
Warnings: Original support IDs resolve to multiple rows; all rows retained, no invented independence; Some model-designated support is excluded; proposal retained for review only if other eligible anchors support it.

| Row | Source | Normalized price | Evidence classification | Exclusion / uncertainty |
| --- | --- | --- | --- | --- |
| 0 | [PriceCharting](https://www.pricecharting.com/game/pokemon-base-set/charizard-4) | 367.79 USD | unverified_completed_sale_claim | shipping_or_tax_basis_uncertain; missing_identity:language |
| 1 | [PriceCharting](https://www.pricecharting.com/game/pokemon-base-set/charizard-4) | 349.99 USD | unverified_completed_sale_claim | shipping_or_tax_basis_uncertain; missing_identity:language |
| 2 | [eBay](https://www.ebay.com/itm/327385385994) | 380.00 USD | unverified_completed_sale_claim | condition_mismatch; missing_identity:language |
| 3 | [PriceCharting](https://www.pricecharting.com/game/pokemon-base-set/charizard-4) | 470.00 USD | unverified_completed_sale_claim | completed_sale_price_or_status_uncertain; missing_identity:language |

### first-edition-gengar

**provisional_estimate**. Original estimate and range: $320 ($275–$470).

Remaining decision errors: none; review warnings still apply.
Warnings: Source prices and source facts remain unverified AI claims; Missing identity/freshness fields remain unknown; Material source price disagreement is preserved; no averaging or outlier removal.

| Row | Source | Normalized price | Evidence classification | Exclusion / uncertainty |
| --- | --- | --- | --- | --- |
| 0 | [cardflip.io](https://cardflip.io/cards/pokemon/fossil-1st-edition/gengar--base3-5-1st) | 289.91 USD | unverified_published_reference_claim | freshness_unknown |
| 1 | [PokeValues](https://www.pokevalues.com/card/gengar-5-fossil-05) | 460.96 USD | unverified_published_reference_claim | no row-level exclusion; source claims still unverified |
| 2 | [lastsold.com](https://lastsold.com/en/sets/fossil/gengar-5-1st) | 341.40 USD | unverified_completed_sale_claim | missing_identity:graded |
| 3 | [Bill's Archive](https://billsarchive.com/fossil.html) | 663.25 USD | unverified_published_reference_claim | missing_identity:language; missing_identity:graded |
| 4 | [CollectAIO](https://www.collectaio.com/item/fossil-gengar-5-05-62) | 335.62 USD | unverified_completed_sale_claim | missing_identity:graded |

Price conflicts: [{"kind": "material_condition_matched_price_spread", "prices": ["289.91", "460.96"], "ratio": "1.590010692973681487358145631", "meaning": "Review trigger above 25% spread, not an outlier-removal or accuracy rule."}]

### japanese-charizard

**provisional_estimate**. Original estimate and range: 390 (380–405).

Remaining decision errors: none; review warnings still apply.
Warnings: Some model-designated support is excluded; proposal retained for review only if other eligible anchors support it; Source prices and source facts remain unverified AI claims; Missing identity/freshness fields remain unknown.

| Row | Source | Normalized price | Evidence classification | Exclusion / uncertainty |
| --- | --- | --- | --- | --- |
| 0 | [The Lab TCG](https://thelabtcg.com/card/566544%3AHolofoil) | 388.35 USD | unverified_published_reference_claim | contradictory_condition_fields; missing_identity:edition |
| 1 | [ValueMyCard](https://valuemycard.com/card/566544-charizard-ex-pokemon-japan-sv2a-pokemon-card-151) | 392.37 USD | unverified_completed_sale_claim | missing_identity:edition |
| 2 | [LastSold](https://lastsold.com/en/sets/pokemon-card-151/charizard-ex-201) | 390.28 USD | unverified_completed_sale_claim | representation_unresolved: number: Collector denominator missing or number unrecognized; representation_unresolved: finish: Unknown finish label; collector_denominator_missing; missing_identity:edition; missing_identity:finish |

Full row transformations, raw fields, identifiers, original errors and decisions are preserved in the adjacent JSON report. Accuracy remains unmeasured without independent benchmark prices.
