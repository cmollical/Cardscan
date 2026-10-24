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
