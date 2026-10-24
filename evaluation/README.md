# Twenty-card evaluation protocol

`manifest.json` selects 20 distinct real Pokémon card candidates across vintage
and modern sets, all five conditions, ordinary/reverse/holo variants, and
hypothesized low/mid/high price tiers. Tier labels are sampling hypotheses, not
observed values. Identity links are review pointers, not proof of every listed
physical variant. All identities require physical-printing review before scoring.
No real market comps, prices, timestamps or accuracy claims are included.

## Collect and freeze evidence

1. Review identities and public collection/commercial-use permissions using
   `docs/manual-comps.md`. The committed empty registry authorizes no sources.
2. Freeze the cohort, USD market basis, cutoff, 90-day window, minimum 3 sales,
   outlier factor 3 and code revision **before** seeing holdout results. Record
   changes as a new experiment, not edits to improve a previous score.
3. For each case ID, create an evidence directory with `prediction.jsonl` using
   the full manual schema. Include plausible hard negatives (wrong edition,
   language, collector number, finish or condition) to assess matching failures.
4. A separate reviewer independently checks printing/condition for each accepted
   candidate against permitted evidence and independently collects at least
   three held-out exact sales in `reference.jsonl`. Use disjoint transaction
   IDs **and** URLs; manually check syndicated/relisted copies too. Reference
   `verified_by` must equal the independent reviewer. Prediction reviewers must
   differ. Keep matched date ranges/region/shipping basis; no condition discounts.
5. Independently review the target physical printing and mark `target_verified`
   only after that review. Save `adjudication.json` as below. Reviewer identity is an attestation, not
   software-authenticated independence. Preserve review notes/artifacts separately.
6. Run the evaluation and archive its JSON, all input hashes, permission reviews,
   cutoff and git revision. Have the reviewer sign the frozen evidence manifest.

```json
{
  "reviewer": "ACTUAL INDEPENDENT REVIEWER",
  "target_verified": true,
  "labels": [
    {"source": "SOURCE KEY", "transaction_id": "ACTUAL ID",
     "printing_matches": true, "condition_matches": true}
  ]
}
```

```bash
python -m cardscan.validation evaluation/manifest.json local-evidence/evaluation \
  evaluation/permissions.json --as-of 2026-10-24
```

Use your reviewed registry instead of `evaluation/permissions.json` when real
permitted evidence exists. The empty committed registry intentionally produces
only pending cases with an absent evidence directory.

## Metrics and denominators

- Exact-printing matching accuracy: independently labeled accepted comps whose
  six printing dimensions match / labeled accepted comps. This is acceptance
  precision, **not** scanner accuracy, catalog recall or a tautological comparison
  against the parser's own labels. Report annotation coverage alongside it.
- Condition matching accuracy: independent correct-condition labels / labeled
  accepted comps. Report counts and coverage; unlabeled evidence is unsupported.
- Median absolute percentage pricing error: median `100 * abs(estimate - heldout
  median) / heldout median`, restricted to valued cases with sufficient disjoint
  reference evidence and fully correct acceptance labels. Also report scored
  card count and proportion within ±10%; do not hide excluded cases.
- Sufficient evidence: emitted valuations / **all 20 planned cases**, including
  abstentions/pending. This measures engine eligibility, not external truth.
- Incorrect or unsupported valuation rate: emitted values with an incorrect
  accepted identity/condition, missing adjudication/reference evidence, or error
  above 10% / emitted values. Denominator zero gives `null`, never a perfect rate.

Full review of all 20 cases can complete an evaluation even if some abstain.
Sparse cards must remain in the cohort. Target ±10% for sufficiently liquid cards
remains **unvalidated**. Report within-tier/condition results, sample sizes,
spreads and sensitivity to cutoff/window in a later market study; 20 observations
alone cannot establish general accuracy across Pokémon.

## Current run

`baseline-report.json` is a reproducible **empty-evidence dry run** dated
2026-10-24. All 20 are pending; eligibility is 0/20, pricing/matching/unsupported
metrics are null. This is not a completed real-card validation experiment. The
integration tests use synthetic prices only. Obtaining legally reusable public
transactions and independent human review remains the blocking work.
