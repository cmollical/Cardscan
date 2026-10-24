# First authorized OpenAI web-search pilot — 2026-10-24

Run: https://github.com/cmollical/Cardscan/actions/runs/40114686775/attempts/2
Code: bac237d9912f270af78c590d300e907816ef781b
Evidence artifact: https://github.com/cmollical/Cardscan/actions/runs/40114686775/artifacts/12568485590
Artifact SHA-256: 91c674bd4c3a2885453511cddc974096484d1692660e8ac342dd7fe49b3c725a
GitHub artifact retention: seven days. Artifact copied into the execution workspace for inspection.

## Outcome

The repository Actions secret was successfully available to the runner. All five
Responses requests returned usage records. No defensible valuation was established.
The workflow completed successfully as an experiment runner; this is not pricing success.

| Case | Requested condition | Provider result | Retained sold candidates | Qualified sales | Estimated API USD | Seconds |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Charmander Obsidian Flames 26/197 English standard non-holo | NM | researched | 4 | 0 | 0.03729575 | 10.804 |
| Charizard ex 151 199/165 English standard holo | NM | researched | 6 | 0 | 0.03668675 | 10.154 |
| Charizard Base Set 4/102 English Unlimited holo | LP | invalid_response | 0 | 0 | 0.04312575 | 8.965 |
| Gengar Fossil 5/62 English First Edition holo | LP | researched | 3 | 0 | 0.03292250 | 9.140 |
| Charizard ex Pokemon Card 151 201/165 Japanese standard holo | NM | invalid_response | 0 | 0 | 0.04242375 | 8.920 |

All are raw targets. Exact target definitions are in experiments/ai-five/manifest.json.
Retained counts exclude evidence discarded by provider validation; zero retained
does not establish that the search found no candidate information.

Total estimated API charge: **$0.19245450**.
Average estimated charge: **$0.03849090**. Maximum: **$0.04312575**.
Average research-and-valuation latency: **9.596558991 seconds**.
Sum of case latencies: **47.982794955 seconds**; excludes runner setup.
These are estimates from response usage and the documented rate card, not invoices.

## Evidence findings

The three parsed responses retained thirteen purported completed-sale candidates.
All thirteen failed deterministic qualification. Candidate claims came from
PriceCharting, Rip & Hold, CollectAIO and lastsold.com. These names describe
unverified research output, not approved or independently validated providers.

All retained candidates lacked a genuine marketplace transaction/listing ID.
Additional gaps included explicit single-card/bundle status, price excluding
shipping/tax, exact condition, actual sale date and/or original currency.
No candidate reached direct eBay corroboration, because required fields failed
earlier validation. This pilot therefore did not independently substantiate
the claimed sale amounts, dates, conditions, or source access descriptions.

Some model outputs populated NM condition while their own summaries admitted
that precise raw condition was unavailable. Such claims must not be accepted;
a missing-information versus identity consistency check is a useful next fix.

TCGplayer/eBay query suggestions did not produce accepted primary-source
transactions. Search coverage and citations do not establish source support.

## Search-limit finding

The Base Set Charizard and Japanese Charizard responses each contained **three**
web_search_call items despite a configured max_tool_calls of two. The provider
recorded the cost, rejected each response with
"Search call count outside configured limits", and produced no valuation.

Do not treat the API setting as a verified billing cap. Inspect returned search
actions and current API semantics before further paid experiments. The observed
total was below the authorized $2 budget. No retries or extra paid experiments
were launched after these five requests.

## Tests and accuracy

The GitHub runner passed **90 mocked automated tests** in **1.028 seconds**.
No paid API credentials were exposed to the test step.

Sufficient-evidence rate: **0/5**. Valuations issued: **0**.
Incorrect/unsupported valuations issued: **0**, because the engine abstained.
Independent exact-printing accuracy, condition accuracy, source-price
substantiation, MAPE and percentage within +/-10% remain **unmeasured**.
Abstention is not evidence of pricing accuracy.

## Next work

1. Diagnose actual search-call action accounting and budget enforcement.
2. Resolve original transaction URLs/IDs through permitted source discovery.
3. Reject internally contradictory condition/missing-information claims.
4. Independently verify source pages before calculating a sold-comp median.
5. Keep this run as the baseline; do not substitute synthetic test success for
   market validation. No additional paid run is included in this report.
