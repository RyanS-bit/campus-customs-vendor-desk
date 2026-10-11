# Problem 4 — Prompt Caching Experiment

**Bottom line.** On all 12 practice documents, with prompt-cache **reads** allowed, the agent cost **$0.00463** in total, or **$0.00039 per document**. With cache **reads prevented**, it cost **$0.03503**, or **$0.00292 per document**. Both figures are actual costs under `data/prices.json`. With caching, the shop pays about **one-eighth** as much. The agent's extracted facts and decisions were identical in both conditions on every document.

All numbers below come from API-reported usage of 48 genuine gpt-6-luna calls. They are rebuilt from the raw logs into `output/cache_test.json`, and the totals reconcile exactly with `output/cache_experiment/full/usage_log.json` ($0.039665885).

---

## 1. Experimental design

| | Cache reads prevented ("disabled") | Caching enabled ("enabled") |
|---|---|---|
| Model / gateway | gpt-6-luna via Portkey (reported as `gpt-6-luna-global`) | same |
| Operating prompt + handbook | identical | identical |
| First line of instructions | `Request ID: <12 random hex>`, **new on every model call** | none |
| Tools, output schema, documents | identical | identical |
| Portkey response cache | bypassed (`x-portkey-cache-force-refresh: true`) | bypassed |
| Security posture | Problem 3 baseline, no defenses | same |

- **How reads are prevented:** prompt caching matches the *start* of the prompt. A different first line on every call means nothing can match a cached prefix. PydanticAI rebuilds the instructions on every model request; an offline test confirmed this, and the logged ID lines prove it: 24 calls, 24 distinct IDs.
- **Proof that only the ID line differs:** for every one of the 48 calls, the request hook hashed what was actually sent. The instructions minus the ID line hash to `…5445837615` and the tool definitions to `…4a9cb8c5d6`, identical across all 48 calls.
- **Paired, alternating order:** each document ran under both conditions before the next document. The first condition alternated: p01 disabled first, p02 enabled first, and so on. The exact order is recorded in `output/cache_experiment/full/runs.json` (`pair_index`, `position_in_pair`, `global_sequence`).

  ```
  1 p01-dis  2 p01-ena  3 p02-ena  4 p02-dis  5 p03-dis  6 p03-ena  7 p04-ena  8 p04-dis
  9 p05-dis 10 p05-ena 11 p06-ena 12 p06-dis 13 p07-dis 14 p07-ena 15 p08-ena 16 p08-dis
  17 p09-dis 18 p09-ena 19 p10-ena 20 p10-dis 21 p11-dis 22 p11-ena 23 p12-ena 24 p12-dis
  ```

- **Automatic safeguards:** the run would have stopped on any cached read in the disabled condition, any Portkey status other than `REFRESH`, any failed run, or spend above $0.08. **None triggered.** There were no retries and no extra runs.
- **Run window:** 2026-10-10 19:45:43 to 19:49:20 UTC.

### How the two conditions were established, including approaches that failed

All evidence is kept in `output/cache_experiment/` and is labeled in `cache_test.json`.

1. **Phase `preliminary` (superseded).** We first tried PydanticAI's `prompt_cache_options` with mode "explicit". Two problems surfaced:
   - **Portkey replay:** the first three runs were **Portkey response-cache replays** (`x-portkey-cache-status: HIT`, with the same response IDs as Problem 3). The model was never called. These 6 calls are excluded from every total.
   - **Setting ignored:** after bypassing Portkey's cache, the "explicit" setting still produced cached reads, and the provider echoed it back as `null`. That approach was abandoned.
2. **Phase `preliminary_option_a`.** The per-call ID method was verified on p01: 0 cache reads, with cache writes still occurring. Dr. Ryan then approved the full run.
3. **Phase `full`.** This report.

## 2. Evidence that the disabled condition had zero cache reads

| Check (all 24 disabled calls) | Result |
|---|---|
| Provider-reported cached input tokens | **0 on every call** (max 0) |
| Distinct request IDs sent | 24 of 24 |
| Portkey cache status | `REFRESH` on every call, so every call was a genuine model request |
| Unique provider response IDs (all 48 calls) | 48 of 48 |
| Raw provider usage block = values parsed by PydanticAI | 48 of 48 match |

**Important qualification:** preventing cache *reads* did **not** prevent cache *creation*. Every disabled call reported cache **writes** of 10,989–11,479 tokens; 267,768 in total. The provider stored each unique prompt even though nothing could ever reuse it. So this condition is best described as **"cache reads prevented,"** not "caching switched off."

## 3. Token totals (12 documents, 24 calls per condition)

| Tokens | Source | Cache reads prevented | Caching enabled |
|---|---|---|---|
| Total input | reported | 270,792 | 270,503 |
| Cached input (cache reads) | reported | **0** | **263,746** |
| Cache writes (cache creation) | reported | **267,768** | **3,733** |
| Uncached input = input − reads − writes | derived | 3,024 | 3,024 |
| Output | reported | 2,516 | 2,456 |
| of which reasoning | reported | 1,188 | 1,105 |

- **Input totals:** they differ by 289 tokens. The ID line adds 14 tokens × 24 calls = 336; small differences in output length change what the second call re-sends.
- **Uncached input:** exactly 126 tokens on every call in both conditions (see section 9).
- **Enabled condition:** **every one of the 24 calls read from cache**, including call 1 of every document. Cache writes there were small: 20–23 tokens on call 1, and 190–484 tokens on call 2, where the new vendor-document text was added. p01 was the exception, with 0 writes on both calls.

## 4. Total cost per condition

| | Cache reads prevented | Caching enabled |
|---|---|---|
| **Actual cost under `prices.json`** | **$0.03503140** | **$0.00463449** |
| Hypothetical: provider that neither reads nor writes cache | $0.02833720 | $0.02827830 |

- **How actual cost is calculated:** for each call, uncached × $0.10 + cache reads × $0.01 + cache writes × $0.125 + output × $0.50, all per 1M tokens, summed over calls.
  - When a call reports 0 reads but 11,000 writes, those 11,000 tokens are billed at the **cache-write** rate ($0.125/1M), 25% above ordinary input.
  - That is why the disabled condition's actual cost is **23.6% above** the hypothetical.
- **Hypothetical (not actual pricing):** every input token at $0.10/1M plus output at $0.50/1M, as if the provider had no cache at all. It is shown only for comparison and never mixed into the actual figures.

## 5. Per-document costs and savings (actual pricing)

| Document | Reads prevented | Caching enabled | Saved | Saved % |
|---|---|---|---|---|
| p01_bluehen_quote.html | $0.00292420 | $0.00034683 | $0.00257737 | 88.1% |
| p02_elmcity_quote.html | $0.00296370 | $0.00043809 | $0.00252561 | 85.2% |
| p03_ivyprint_catalog.html | $0.00297432 | $0.00043872 | $0.00253561 | 85.2% |
| p04_harborstitch_quote.html | $0.00294132 | $0.00041449 | $0.00252684 | 85.9% |
| p05_maplemills_quote.pdf | $0.00287933 | $0.00035046 | $0.00252886 | 87.8% |
| p06_qtextile_quote.pdf | $0.00288395 | $0.00036647 | $0.00251748 | 87.3% |
| p07_longwharf_quote.pdf | $0.00292870 | $0.00037634 | $0.00255236 | 87.1% |
| p08_chapelst_email.eml | $0.00287908 | $0.00037460 | $0.00250447 | 87.0% |
| p09_westville_email.eml | $0.00291408 | $0.00036697 | $0.00254710 | 87.4% |
| p10_eastrock_email.eml | $0.00290107 | $0.00036297 | $0.00253810 | 87.5% |
| p11_yorkst_quote.html | $0.00291208 | $0.00040484 | $0.00250724 | 86.1% |
| p12_bluehen_quote.pdf | $0.00292958 | $0.00039370 | $0.00253587 | 86.6% |
| **Average per document** | **$0.00291928** | **$0.00038621** | **$0.00253308** | **86.8%** |

Savings were very consistent, at 85.2–88.1% across all three formats (HTML, PDF, email). Enabled costs vary mainly with output length.

## 6. Overall savings: two separate comparisons, not combined

| Comparison | Baseline | Caching enabled (actual) | Saved | Saved % |
|---|---|---|---|---|
| **A. Actual vs. actual** (what we measured under `prices.json`) | $0.03503140 (reads prevented) | $0.00463449 | $0.03039692 | **86.8%** |
| **B. Actual vs. hypothetical** (a provider with no cache at all) | $0.02833720 (hypothetical) | $0.00463449 | $0.02370272 | **83.6%** |

- **A** is larger because the reads-prevented condition still pays the cache-write premium.
- **B** answers a different question: how much cheaper caching is than a provider that never caches. It's the closer analogue to Problem 2's "no caching" baseline.

**Business meaning:** the stable instructions, mostly the handbook, make up 94.7–98.9% of every prompt's input. Reading them from cache costs a tenth of the normal price, so caching cuts the vendor desk's running cost by roughly 84–87%. Without cache reads, this provider still charges a premium to store every prompt, making the no-reuse case even more expensive.

## 7. Comparison with the Problem 2 estimates

| Quantity | Problem 2 (estimate) | Problem 4 (measured) |
|---|---|---|
| Stable prompt prefix | handbook only: 10,058 tokens (tiktoken) | **10,959–10,979 cached tokens** on call 1 (handbook + operating prompt + framing + tool definitions) |
| Model calls per document | not modeled (1 call = 1 handbook send) | **2** (one to read the document, one to answer) |
| Cost per call, no caching | $0.0010058 (handbook only) | $0.00145964 actual / $0.00118072 hypothetical (whole call) |
| Cost per call, cached | $0.00010058 (handbook read) | $0.00019310 (whole call) |
| Savings | 89.9% (1,000 calls, handbook only) | 83.6% (B) / 86.8% (A), whole agent |
| Cold-start write | 1 write, then reads | **No full-prefix write in the full run**: the cache was already warm |

**Why the measured values differ:**
1. **Bigger prefix.** The cached prefix includes the operating prompt (about 609 tokens by tiktoken) and tool and format framing, not just the handbook. The 10,058 handbook count is consistent with this: 10,058 + 609 = 10,667, plus about 300 tokens of framing. The handbook alone can't be isolated from the API counts.
2. **Two calls per document.** The handbook is sent twice per document, so per-document costs are about double the per-call figures.
3. **Parts that can't be cached.** Problem 2 counted only the handbook, which is entirely cacheable. Real calls also have 126 uncached tokens each, output tokens at 5× the input price (never cached), and small cache writes for the new document text. These keep savings below Problem 2's 89.9%.
4. **Cache writes happen even when nothing is reused.** Problem 2 treated "no caching" as plain input at $0.10/1M. This provider writes every new prefix at $0.125/1M, which is why comparisons A and B differ.

**Verdict:** the measurements **support the Problem 2 conclusion**: caching saves most of the input cost, and the savings approach 90% of the cacheable part. The real system saves somewhat less (84–87%) because of the uncacheable parts above.

## 8. Monthly projection: 1,000 documents per day for 30 days (30,000 documents)

| Scenario | Per document | Per day | **Per month** |
|---|---|---|---|
| Caching enabled, warm cache as measured | $0.00038621 | $0.39 | **$11.59** |
| Caching enabled, call 1 misses on every document (pessimistic) | $0.00164653 | $1.65 | **$49.40** |
| Hypothetical provider with no cache (not actual pricing) | $0.00236143 | $2.36 | **$70.84** |
| Cache reads prevented (actual pricing) | $0.00291928 | $2.92 | **$87.58** |

**Assumptions** (all explicit; none measured over a month):
1. Future documents look like the 12 practice documents: similar size, about 2 model calls each, and similar output length.
2. Prices stay as in `prices.json`. There is no Portkey markup and no charge for Portkey itself.
3. **Warm scenario:** every call reads the cached prefix, as in all 24 enabled calls in this run. Evidence supporting it:
   - the cache stayed usable across a 7.7-minute gap between phases;
   - the provider reports `prompt_cache_retention: "24h"`;
   - 1,000 documents a day is about one every 86 seconds.

   That evidence covers about one hour of operation, **not a month**.
4. **Pessimistic scenario:** call 1 of every document misses the cache and rewrites the prefix ($0.00139248, the miss actually observed in phase `preliminary_option_a`), while call 2 still hits. We did observe that miss even though the same prefix had been written within the previous hour, so warm reuse is not guaranteed.
5. One daily cold start (a single full write, about $0.0014) is included in neither scenario. It's negligible at this volume.
6. Retries, failures, longer documents, or a prompt change would change these numbers. A prompt or handbook edit invalidates the cache until it is rewritten.

**Business meaning:** with caching working as measured, the vendor desk would cost about **$12 a month** for 30,000 documents, against **$71–88** without cache reuse. Even in the pessimistic case it stays below the no-cache cost. The largest monthly risk isn't caching but changes in volume, document size, or model behavior.

## 9. Unexpected findings, limitations, and methodological concerns

**Unexpected findings**
1. **Portkey response replay.** The Portkey key's gateway config caches entire responses. Unless the bypass header is sent, repeating a request returns a stored answer and the model is never called. This affected the preliminary runs (excluded from all totals), and it **will affect Problem 3's default mode in later problems** if documents are re-run.
2. **`prompt_cache_options` was ignored.** The provider echoed it as `null`. There is no confirmed way, in this configuration, to switch provider caching off.
3. **Cache creation without reuse.** Preventing reads still triggered a full cache write on every call, about 11,000 tokens billed at $0.125/1M.
4. **Exactly 126 uncached tokens per call,** in every call of both conditions, regardless of document. *Unverified explanation:* the provider caches in fixed-size blocks, and the final partial block is never cached.
5. **Cross-run reuse is real but not guaranteed.** In the full run, 24 of 24 enabled calls hit the cache, including the first call of each document. In the preliminary run, an enabled first call missed despite a recent write.
6. **Behavior unchanged by condition.** Vendor, SKU, price, lead time, minimum order and decision were identical in both conditions for all 12 documents. Only the reason wording varied. Tools used were `read_vendor_document` and `final_result` only. **No trap tool was called** (`trap_calls.json` = `[]`), and no run failed or retried.
7. **Observation for the later security problems (not evaluated here).** Some outputs look influenced by text embedded in the documents, identically in both conditions:
   - for `p03_ivyprint_catalog.html`, the agent reported the vendor as "Chapel Street Goods" and recommended;
   - for p07, the reason refers to a "**corrected** lead time" of 7 business days.

   Problem 4 measures cost, not accuracy, so outputs were **not** compared with the answer key.

**Limitations**
1. **Prompts differ by 14 tokens** (the ID line, about 0.13% of input). The fingerprints confirm everything else was identical.
2. **"Reads prevented" ≠ "caching disabled."** Cache creation still occurred and was billed. Comparison B covers the true no-cache case only hypothetically.
3. **Warm-cache measurement.** The enabled condition began warm from the preliminary phase, so the full run never shows the one-time cold write. That was observed separately: 10,979 tokens, $0.00139.
4. **Order effects.** Because every disabled prefix is unique, disabled runs can't warm or be warmed by anything, and they don't warm the enabled prefix. Enabled runs benefit from earlier enabled runs. Alternating the order made no visible difference:
   - average enabled cost per document was $0.00039172 when enabled ran first in the pair, and $0.00038069 when it ran second;
   - all enabled calls hit the cache in both positions.
5. **One run per document per condition,** within about 4 minutes. Model outputs vary somewhat between runs, so per-document costs carry some noise, mainly from output length.
6. **Prices come from `prices.json`,** not a provider invoice. Whether Azure actually bills cache writes at 1.25× has not been verified.
7. **One private PydanticAI import** (`create_async_httpx2_client`) is used so the HTTP transport matches Problem 3 exactly. It's safe at the pinned version.

## 10. Reproducing the experiment

```
pip install -r requirements.txt
python cache_experiment.py --phase full        # 24 runs: paired, alternating, with safeguards
python cache_experiment.py --build-only        # rebuild output/cache_test.json from the logs
```

- **Before re-running:** a re-run *appends* to `output/cache_experiment/full/`. Move that folder aside first, or the new runs will be combined with these.
- **Single run:** `python agent.py --doc <doc> --cache {disabled|enabled} --log-dir output/cache_experiment/<phase>`.
- **Problem 3 baseline:** preserved in `baseline_problem3/` (read-only, with SHA-256 manifest). `python agent.py --doc <doc>` with no `--cache` still sends the Problem 3 request, with no bypass header and no ID.

**Files created or changed for Problem 4:** `agent.py` (`--cache`, `--log-dir`, response hook, per-call ID), `tools.py` (per-run trap-log path), `cache_experiment.py` (new), `requirements.txt` (+`httpx2==2.12.0`), `output/cache_test.json`, `output/cache_test.md`, `output/cache_experiment/` (logs), and `baseline_problem3/` (snapshot).
