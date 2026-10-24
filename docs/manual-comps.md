> This is the original strict manual-review workflow. For the current personal
> research mechanism, use [public-web research](../research/README.md); no permission
> registry is required for that command. Shipping is excluded in both workflows.

# Manual verified comparable ingestion

This workflow does not authorize copying a marketplace. Use only publicly
available transaction evidence whose collection and commercial reuse have been
reviewed and permitted. Unknown permissions mean no ingestion. TCGplayer,
eBay and PriceCharting are not preapproved. Entering a sale manually does not
cure restrictions on copying or combining that data.

1. Create `local-evidence/permissions.json`, mapping a source key to the exact
   reviewed grant or license reference. Preserve the document, review date,
   scope and attribution requirements. Do not invent a license reference.
2. Identify the exact physical printing: canonical set, full collector number,
   language, edition and all finish/stamp distinctions. Choose exactly one of
   NM, LP, MP, HP, DMG, based on reviewed condition evidence. If ambiguous, stop.
3. Verify a completed single-card, ungraded, nonrefunded transaction. Record the
   actual paid amount, sale date, known shipping, currency, stable source
   transaction ID and public evidence URL. Hidden best-offer amounts, asking
   prices, auction bids and broad “used” condition labels are insufficient.
4. Record reviewer, actual review date, and notes explaining printing, condition,
   price and sold-status verification. Keep permitted supporting artifacts;
   exclude buyer identities, addresses and payment details.
5. Save one JSON object per line using **every** `Sale` field below. Money uses
   decimal strings. Booleans must be JSON booleans. Unknown shipping is `null`;
   it is allowed and never enters the valuation. Malformed lines fail the run with a line number.
6. Run the CLI with a reproducible cutoff. Inspect every rejection and review
   state. Never fill missing comps to reach the configured minimum.

```bash
python -m cardscan.cli local-evidence/target.json local-evidence/comps.jsonl \
  local-evidence/permissions.json --as-of 2026-10-24 --minimum-sales 3
```

`target.json` contains just the seven fields in `card` below. The example is
**synthetic schema illustration only**, not a real sale, market value or permission:

```json
{
  "card": {
    "game": "pokemon", "set_name": "base set", "number": "4/102",
    "language": "english", "edition": "unlimited", "finish": "holo", "condition": "LP"
  },
  "item_price": "100.00", "shipping": "5.00", "sold_on": "2026-10-20",
  "url": "https://example.com/SYNTHETIC-NOT-A-SALE",
  "sold": true, "graded": false, "bundle": false, "currency": "USD",
  "source": "synthetic", "transaction_id": "SYNTHETIC-1",
  "verified_by": "SYNTHETIC REVIEWER", "verified_on": "2026-10-24",
  "verification_notes": "SYNTHETIC ONLY; no verified market evidence",
  "permission_reference": "SYNTHETIC ONLY; no permission granted",
  "price_confirmed": true, "condition_confirmed": true, "refunded": false,
  "verification_level": "reviewed"
}
```

Keep permission references and source keys stable across runs. Transaction IDs
must identify the underlying sale across tracking URLs; do not create new IDs
for relists or the same sale syndicated elsewhere. The engine deduplicates
source/transaction ID and normalized URLs; cross-provider syndicated evidence
still needs human review. Scrutinize conflicting records rather than accepting
whichever copy happens to appear first.
