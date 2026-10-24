# Direct TCGplayer sales-history investigation — 2026-10-24

## Verified outcome

The public Charizard product page and first-party application code are accessible.
Product metadata and filter metadata returned HTTP 200 without credentials.
The exact sales-history request returned **HTTP 403 Forbidden** from this
execution environment. No live sales rows were retrieved, no direct TCGplayer
pricing provider is enabled, and the user's five screenshot rows were not passed
off as a network response. The reason for the server rejection is not proven.

## First-party observations

- Product [42382](https://www.tcgplayer.com/product/42382/pokemon-base-set-charizard)
  identifies Charizard, Base Set, 004/102. Its product tip explicitly describes
  the Unlimited printing. `foilOnly` is true. Its market-price aggregate is **not**
  an MP sale price and was not used for valuation.
- [Product metadata](https://mp-search-api.tcgplayer.com/v1/product/42382/details)
  returned 200; [filter metadata](https://mp-search-api.tcgplayer.com/v1/product/categoryfilters?productId=42382)
  returned condition 3 = Moderately Played, language 1 = English, and variant
  11 = Holofoil. These are live observations, not assumed enum IDs.
- The [request client bundle](https://www.tcgplayer.com/js/src-1TdckMNQ.js)
  calls `POST https://mpapi.tcgplayer.com/v2/product/42382/latestsales`.
  Its caller supplies the selected condition/language/variant/listing-type filters.
- The [application bundle](https://www.tcgplayer.com/js/index-DDW8-tIO.js)
  uses a five-row limit for its signed-out view. It also obtains request-validation
  values before making the sales call. We did not generate, forge or replay them.
- The [sales component](https://www.tcgplayer.com/js/ProductDetails-vnTPLyjW.js)
  displays `orderDate`, `condition`, `variant`, `language`, `quantity`, and
  `purchasePrice`. The displayed price is the purchase price, not an active
  listing or product-level market aggregate. The source separately presents
  “Sign In to View More Sales”; we did not request signed-in pagination.

The unauthenticated five-row request tested was:

```json
{"conditions":[3],"variants":[11],"languages":[1],"listingType":"All","limit":5}
```

It returned 403 without an API key, cookie, authorization header or generated
validation values. We did not vary headers or endpoints to evade the denial.
Successful metadata access does not establish sales access, and 403 does not
prove the panel is inaccessible through an ordinary user browser.

## What remains unverified

No browser-control connection is available in this session, so we could not open
the panel, select the filters and observe a successful normal-browser response.
We cannot establish whether this environment's rejection results from missing
client validation, session requirements, network filtering or another policy.
A connected user browser is needed to test the ordinary UI path and compare its
five rows with the screenshot. Do not increase row limits or bypass sign-in.

The public-page approach is technically different from the discontinued developer
API. Our earlier API-access assessment was too broad to establish this path's
availability. The screenshot proves UI visibility to that user, not programmatic
access from every environment.

## Reproducible diagnostic

```bash
python -m cardscan.tcgplayer_probe
```

This sends one five-row request, records status/hash, does not retry or solve
request validation, and never returns a valuation. A successful future response
still requires actual schema inspection, exact mapping, duplicate semantics and
price-only validation before it can become an engine provider. Tests use synthetic
responses to ensure 403 and HTML challenges cannot be reported as live pricing.

The committed investigation JSON records actual observed statuses and hashes of
captured first-party resources. Exact initial request times were not recorded;
`observed_at` is null instead of an invented timestamp. Resource build names may
change; discover current paths from the public page rather than pinning these
bundle names in a production provider.
