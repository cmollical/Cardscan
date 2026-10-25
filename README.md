# CardScan

Pokémon pricing research prototype with deterministic valuation and modular
evidence providers. **Market value excludes shipping and tax.** Scanner, PWA
and inventory work remain out of scope. Existing offline/public-page workflows
are preserved.

## AI market research (paid execution disabled by default)

A separate **[AI market-estimation experiment](docs/ai-market-estimation.md)** now
uses ChatGPT-style research and synthesis without requiring authenticated sales.
It labels estimates, generic references, assumptions and unverified source claims
explicitly. Its new five-card run is **not authorized or executed**. The existing
strict engine remains unchanged. Independent [source-verification adapters](docs/reference-verification.md)
are also preserved. Full mocked suite: **156 tests pass**; this is not evidence
of real-world pricing accuracy.

The new `OpenAIWebSearchProvider` uses the official Responses API with web search,
strict evidence schemas, exact matching, separate sale/reference/asking-price
evidence, independent verification, condition-specific caching and spending guards.
The first authorized five-card pilot completed on October 24, 2026: no verified
valuations, with a $0.19245450 conservative API estimate. Independent pricing
accuracy remains unmeasured. The [forensic analysis](docs/pricing-evidence-forensics.md)
recovers all 20 candidate claims, corrects search-action accounting, and proposes
separate verified-reference pricing. [Experiment 2](experiments/reference-first-v2/PLAN.md)
is a design only and has no paid authorization.

```bash
python -m cardscan.ai.experiment --as-of 2026-10-24
```

That command produces an offline five-card plan and makes no API calls. See
[AI architecture, key setup, costs and experiment instructions](docs/openai-pricing-engine.md).
Live execution requires explicit user authorization and two CLI flags. Model
citations alone never confer verified-comp status.

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
