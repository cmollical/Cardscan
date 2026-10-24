# Working public pricing research — 2026-10-24

This is the implemented personal-app path, with actual network results. It uses
public pages, no subscription and no paid API. Market value is the card sale
price only; shipping and tax never enter the calculation.

## Actual results: 30-day NM English sale reports

| Printing | Publisher-reported marketplace | Qualified rows | Card-only median |
|---|---|---:|---:|
| Charizard ex, 151, 199/165 | TCGplayer via PriceCharting | 6 | $314.23 |
| Miriam, Scarlet & Violet, 251/198 | TCGplayer via PriceCharting | 13 | $17.80 |
| Iono, Paldea Evolved, 269/193 | TCGplayer via PriceCharting | 13 | $49.62 |

These are **secondary research estimates**, calculated from dated sale rows,
not PriceCharting's guide values. Each JSON result preserves dates, amounts,
publisher row IDs, source fragments, row hashes, page hashes and observed times.
Rows missing explicit condition/language/full number are rejected. Sources:
[Charizard](https://www.pricecharting.com/game/pokemon-scarlet-%26-violet-151/charizard-ex-199),
[Miriam](https://www.pricecharting.com/game/pokemon-scarlet-%26-violet/miriam-251),
[Iono](https://www.pricecharting.com/game/pokemon-paldea-evolved/iono-269).

Publisher mappings/amounts are not independently confirmed at TCGplayer. The
publisher may convert amounts to USD. Raw condition is seller-declared, and
transaction settlement/refunds cannot be established. Do not treat 32 reported
sales as 32 independently verified transactions or claim ±10% accuracy.

## Direct eBay checks

An initial 20-link run found 17 redirects to product pages and 3 parsable listings,
none qualifying fully. No direct valuation was emitted. A later check of three
source-provided original-listing links recovered actual sold pages. One qualified:
[eBay 327406315985](https://www.ebay.com/itm/327406315985?nordt=true&rt=nc),
reported sold 2026-10-21 for $340.00, NM English Charizard ex 199/165. The other
two lacked complete matching attributes. One comp remains below the minimum.

The adapter now retains the publisher's `nordt=true` original-listing link option
rather than dropping it during URL normalization. This is an ordinary publicly
linked page option, not a captcha or login bypass. Product-page redirects remain
rejected. Direct eBay sold search encountered an access challenge and was stopped.
TCGplayer's product page returned only a JavaScript shell in the web reader; no
live TCGplayer transaction endpoint is claimed.

## Reproduce

```bash
python -m cardscan.research research/configs/charizard-151-nm.json \
  --as-of 2026-10-24 --reports-only
python -m cardscan.research research/configs/miriam-nm.json \
  --as-of 2026-10-24 --reports-only
python -m cardscan.research research/configs/iono-nm.json \
  --as-of 2026-10-24 --reports-only
```

Omit `--reports-only` to also check individual discovered eBay pages. Configure
`--limit` (1–30), `--minimum-sales` (at least 3), and `--report-window-days`.
Network results may change; the committed JSON files are dated observations,
not promises that a URL will retain the same contents. Access errors stay explicit.
Raw HTML and observation envelopes are kept locally under `local-evidence/`.

The next validation step is an independent review of exact identities, seller
conditions and disjoint primary sale evidence against these estimates, then an
expanded 20-card cohort. The earlier cohort also had an incorrect display name
for Vivid Voltage 25/185 (Charizard, not Pikachu); that name is corrected.

## Requested check: Base Set Unlimited Charizard 4/102, English MP

On 2026-10-24, ten individually fetched eBay sold pages were evaluated with the
90-day default window. Two qualified under seller-reported exact-field matching:
$320 on 2026-10-23 UTC (item 257801645593) and $380 on 2026-10-10 UTC
(item 327385385994). The engine returned **insufficient_evidence**, not a price,
because three comps are required. Their arithmetic midpoint is $350, a descriptive
two-comp reference only. Shipping and tax are excluded.

The run exposed and fixed explicit Unlimited matching under eBay Features/title,
a false graded classification based only on an orphan grader-name field, and
missed conflicts between current Condition and legacy Card Condition fields.
No missing vintage edition was inferred, and conflicting conditions stayed out.
Detailed accepted/rejected evidence is in
`results/charizard-base-unlimited-mp-2026-10-24.json`. The original secondary-only
run remains archived separately. The suite now passes 47 tests.

## Direct TCGplayer follow-up

The [direct sales-history investigation](../docs/tcgplayer-sales-investigation.md)
located the exact five-row request and verified product/filter metadata. Metadata
returned 200; sales returned 403 from this environment. No direct TCGplayer sales
were retrieved. `python -m cardscan.tcgplayer_probe` reproduces the diagnostic
without credentials, challenge solving, pagination or invented prices.
