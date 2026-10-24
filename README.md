# CardScan

Personal Pokémon pricing research prototype. The current engine retrieves public
sold-listing evidence and produces auditable estimates. **Market value excludes
shipping and tax.** No paid API, subscription, scanner or PWA is required.

## Get a price from public sale reports

Requires Python 3.10+, standard library only:

```bash
python -m cardscan.research research/configs/charizard-151-nm.json \
  --as-of 2026-10-24 --reports-only
```

This fetches the public PriceCharting page, extracts dated sale records attributed
to eBay/TCGplayer, matches the configured printing, condition and language, and
calculates separate marketplace medians over 30 days. It does not use the guide
price or pretend that publisher reports are independently verified transactions.

To also fetch individual eBay pages for direct checks:

```bash
python -m cardscan.research research/configs/charizard-151-nm.json \
  --as-of 2026-10-24 --limit 12
```

Exact dimensions are checked against seller attributes. Unknowns, redirects to
active product pages, hidden accepted offers, proxies and contradictory condition
labels are rejected. Access challenges stop the affected retrieval; no bypass.
Source URLs, actual observation times, raw-page hashes and reasons are preserved.
Snapshots stay locally under ignored `local-evidence/`; extracted results are in
[research/results](research/results).

See [research results and limitations](research/README.md),
[architecture](docs/architecture.md) and [source research](docs/pricing-sources.md).

## Verification

```bash
python -m unittest discover -s tests -v
python -m cardscan.demo
```

The demo is synthetic. Tests include a minimized real eBay page fixture and
synthetic adversarial records. They check software behavior, not market accuracy.

The original [manual review CLI](docs/manual-comps.md) and
[20-card independent evaluation protocol](evaluation/README.md) remain available.
**The ±10% accuracy target is unvalidated.** Current research values are based on
seller/publisher reports; they do not prove physical condition, payment settlement
or absence of later refunds. No full inventory interface or PWA has been built.
