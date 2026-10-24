# CardScan

Free-first trading card valuation prototype. Pokémon is the first supported game; the domain model supports additional TCGs.

## Phase 1: Pricing validation

The first milestone is **not** automated valuation from unverified web snippets. It is a reproducible comparable-sale evaluator that accepts independently verified sale records and explains why each record was accepted or rejected.

- Match game, set, collector number, language, edition, finish, and condition.
- Exclude graded cards, active listings, bundles, and mismatched printings.
- Calculate median of accepted sold prices including shipping.
- Return **insufficient evidence** when fewer than 3 qualified sales exist.
- Keep original sale URLs and timestamps for auditability.
- No scraping, paid API keys, or invented comps.

## Run locally

Requires Python 3.10+.

```bash
python -m unittest discover -s tests -v
python -m cardscan.demo
```

All sample prices in the demo are synthetic test fixtures, **not live market values**.

## Next milestone

Test 20 real Pokémon cards with independently verified sold-listing evidence, measure rejection precision and comp error, then explore permitted free source integrations and a mobile PWA.


## Research engine (first improvement)

See [pricing-source research](docs/pricing-sources.md), [architecture](docs/architecture.md)
and the [manual verified-comps workflow](docs/manual-comps.md).

No live pricing provider is enabled. Public website access and an open-source
SDK do not establish commercial pricing-data rights. The new offline provider
requires reviewed permission references and explicit verification metadata.
Missing shipping, mixed currencies and unconfirmed paid prices are rejected.
Extreme price dispersion triggers review rather than a misleading price.

```bash
python -m cardscan.cli TARGET.json COMPS.jsonl PERMISSIONS.json --as-of 2026-10-24
python -m cardscan.validation evaluation/manifest.json local-evidence/evaluation \
  evaluation/permissions.json --as-of 2026-10-24
```

The [20-card evaluation protocol](evaluation/README.md) includes a real-card
candidate cohort and independent holdout metrics. No legally approved real sale
records have been obtained: **market accuracy and the ±10% target are unvalidated**.
The baseline report is an empty-evidence dry run, not a real-market benchmark.
Only USD item price plus known shipping, excluding tax, is implemented. Catalog
lookup requires a reviewed caller-supplied catalog; physical identification and
complete catalog coverage are not implemented. No scanner or PWA work has begun.
