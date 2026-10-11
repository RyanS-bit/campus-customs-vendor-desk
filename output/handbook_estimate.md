# Problem 2 — Size Up the Handbook

> **ESTIMATES ONLY.** Every number in this file comes from a local tokenizer and the price sheet. **No model calls were made.** Actual token counts and costs measured from gpt-6-luna through Portkey will be collected in Problem 4 and may differ (see Limitations).
>
> **HANDBOOK TOKENS ONLY.** These are the costs of sending the handbook, not the total cost of running the agent (see section 8).

Reproduce (from the `hw6` folder):

```
pip install -r requirements.txt
python estimate_handbook.py
```

The script prints every number in sections 2, 4 and 5. On its first run, `tiktoken` downloads its tokenizer file from the internet (free, not a model call), then caches it locally.

**How to read the labels below:**
- **Verified:** measured locally from the supplied files or computed from them.
- **Background (unverified):** general knowledge about AI providers, not stated in the supplied materials. Treat it as an assumption until Problem 4 measures it.

---

## 1. Inputs

**File measured:** `data/shop_handbook.md`

| Measure | Value |
|---|---|
| Bytes on disk (UTF-8, all ASCII) | 29,241 |
| Characters after line-ending normalization | 28,903 |
| Words | 6,127 |
| Lines | 338 |

**Line endings (verified):** the file uses Windows line endings (CR+LF) on all 338 lines. Python's `read_text()` converts each CR+LF to a single LF, which removes 338 characters. That accounts exactly for the gap between 29,241 bytes and 28,903 characters.

**Prices:** `data/prices.json`, model `gpt-6-luna` (source in file: "OpenAI Standard pricing, per 1M tokens (MGT 409 Lecture 11)")

| Price field | $ per 1M tokens | $ per token |
|---|---|---|
| `input_per_1m` (normal input) | 0.100 | 0.000000100 |
| `cache_write_per_1m` (first time a prefix is cached) | 0.125 | 0.000000125 |
| `cached_input_per_1m` (cache read / hit) | 0.010 | 0.000000010 |
| `output_per_1m` (not used here) | 0.500 | 0.000000500 |

So a cache write costs 1.25× normal input, and a cache read costs 0.1× normal input (a 90% discount).

## 2. Token count

**Method (verified):** OpenAI's `tiktoken` library (v0.14.0, pinned in `requirements.txt`), encoding **`o200k_base`**.

**Choice of tokenizer (background, unverified):** `o200k_base` is the encoding OpenAI uses for its recent models. The supplied materials do not say which tokenizer gpt-6-luna uses, so using `o200k_base` is an assumption (see Limitations).

| Method | Tokens |
|---|---|
| **`o200k_base`, text as Python reads it (LF line endings), used for all costs below** | **10,058** |
| `o200k_base`, raw file bytes (CR+LF kept), alternative | 10,069 (+11, +0.1%) |
| `cl100k_base` (older OpenAI tokenizer, cross-check, LF) | 10,184 |
| Rule of thumb: characters ÷ 4 | ≈ 7,226 |

**Why 10,058 is primary:** our Python agent will load the handbook with `read_text()`, which normalizes line endings, so 10,058 is the text it will send. This is a design intention; it will be verified when the agent code exists. If the raw bytes were sent instead, every cost below would rise by 0.1% (about $0.0000011 per uncached call).

The two real tokenizers agree within about 1%. The "÷ 4" rule of thumb undercounts by about 28% because the handbook is full of tables, SKUs, prices, and punctuation, which split into more tokens than plain prose does.

**Handbook size used: T = 10,058 tokens.**

## 3. Formulas

Let T = 10,058 tokens, N = number of calls, and prices converted to $ per token (price ÷ 1,000,000).

- Uncached, one call: `T × input`
- Cache write (first cached call): `T × cache_write`
- Cache read (each later call): `T × cached_input`
- Uncached, N calls: `N × T × input`
- Cached, N calls: `T × cache_write + (N − 1) × T × cached_input`

## 4. Results

### (1) One call, no caching

10,058 × $0.100 / 1,000,000 = **$0.00100580** (about 0.10¢)

### (2) One call, with caching

| Part | Calculation | Cost |
|---|---|---|
| First call (cache **write**) | 10,058 × $0.125 / 1M | **$0.00125725** |
| Each later call (cache **read**) | 10,058 × $0.010 / 1M | **$0.00010058** |

A single cached call on its own costs **25% more** than an uncached one ($0.00125725 vs $0.00100580), because the write premium is paid up front. Caching only pays off once the handbook is reused.

### (3) 1,000 calls, no caching

1,000 × $0.00100580 = **$1.0058**

### (4) 1,000 calls, with caching (PRIMARY estimate)

The first call creates the cache at the cache-write price ($0.125/1M); the other 999 calls read it at the cached-input price ($0.01/1M).

| Part | Calculation | Cost |
|---|---|---|
| 1 cache write | 1 × $0.00125725 | $0.00125725 |
| 999 cache reads | 999 × $0.00010058 | $0.10047942 |
| **Total** | | **$0.10173667** |

**Savings vs. no caching:** $1.0058 − $0.1017 = **$0.9041 (89.9% less)**

**ALTERNATIVE billing scenario:** if the provider bills the first call at the normal input rate ($0.10/1M) with no write premium, the total is $0.00100580 + $0.10047942 = **$0.10148522** (savings 89.9%). *Background (unverified):* some providers, including OpenAI's automatic caching, are generally understood to bill this way. However, `prices.json` lists a separate `cache_write_per_1m` price, so the primary estimate uses it. The two scenarios differ by $0.00025145, so the conclusion holds either way. Problem 4 will show which one actually applies.

## 5. How cost grows with the number of vendor documents

This assumes one call per vendor document, with the handbook sent each time (handbook cost only, PRIMARY caching scenario). The table is printed by `estimate_handbook.py` and shown here to 8 decimal places, so every value is exact.

| Calls (N) | Example | No caching | With caching | Saved |
|---|---|---|---|---|
| 1 | one document | $0.00100580 | $0.00125725 | −$0.00025145 (caching costs 25% more) |
| 2 | break-even point | $0.00201160 | $0.00135783 | $0.00065377 (32.5%) |
| 12 | practice set | $0.01206960 | $0.00236363 | $0.00970597 (80.4%) |
| 22 | practice + exam | $0.02212760 | $0.00336943 | $0.01875817 (84.8%) |
| 100 | | $0.10058000 | $0.01121467 | $0.08936533 (88.9%) |
| 1,000 | | $1.00580000 | $0.10173667 | $0.90406333 (89.9%) |

With no caching, cost grows at the full rate of $0.0010058 per call. With caching, it grows at only $0.00010058 per call after a one-time write. **Caching wins from the 2nd call onward**, and savings approach 90% as N grows.

## 6. Assumptions

1. Only the handbook is counted. The system prompt, the vendor document, chat formatting tokens, and the model's **output** are excluded. Output is billed at $0.50/1M and is never cached.
2. The handbook is sent byte-for-byte identically and placed **at the start** of the prompt. Caches match on an exact prefix, so any change before or inside the handbook breaks the cache.
3. **Reuse and expiry:** the cache stays warm for all 1,000 calls, with no expiry between them, and calls are made one after another rather than in parallel.
4. **Eligibility:** the handbook is assumed to be long enough to qualify for caching, and every cache hit is assumed to cover all 10,058 handbook tokens. *Background (unverified):* providers commonly set a minimum prompt length for caching and cache in fixed-size blocks, so a few trailing tokens might be billed at the normal rate. The supplied materials don't specify gpt-6-luna's rules.
5. Portkey passes the provider's prices through with no markup, as `prices.json` implies.
6. Nothing outside the handbook is assumed to be cached. The system prompt is not assumed to be fully cached.

## 7. Limitations: why the Problem 4 measurements may differ

- **Tokenizer:** gpt-6-luna's own tokenizer may differ slightly from `o200k_base`. The API's reported `prompt_tokens` is the authoritative count.
- **Message overhead:** chat formatting adds a few tokens per message, and the API count will include the system prompt and the document.
- **Cache behavior:** the minimum cacheable size, cache lifetime, block size, and whether the first call is billed as a "write" or as normal input are set by the provider. These can only be confirmed from the `cached_tokens` and usage fields in real responses.
- **Concurrency:** calls fired in parallel before the first write finishes may each miss the cache.
- **Scale:** these are fractions of a cent per call. The *percentage* savings is the meaningful result; the dollar amounts are small at this scale.
- **Line endings:** 10,058 assumes the agent sends LF-normalized text. Sending the raw bytes would give 10,069.

## 8. Handbook cost vs. total agent operating cost

This report covers **handbook tokens only**. The real cost of one agent call depends on what the provider actually reports for that call:

```
cost per call = cached_input_tokens   × $0.01  / 1M
              + cache_write_tokens    × $0.125 / 1M   (only when a cache is created)
              + uncached_input_tokens × $0.10  / 1M
              + output_tokens         × $0.50  / 1M
```

- **Input tokens** include the handbook, the rest of the system prompt and instructions, any tool definitions, the vendor document (different every call, so never cached), and message formatting.
- **No part of the prompt is assumed to be cached**, including the full system prompt. Which tokens are cached is decided by the provider and the exact prompt structure, and is known only from the reported usage.
- **Output tokens** cost 5× normal input and are never cached. A long answer can cost more than the cached handbook.

We will fill this formula with **measured** numbers in Problem 4. No total operating cost is estimated here.

## 9. Measurement checklist for the caching experiments (Problem 4)

To confirm or correct the estimates above, record these for every call, from the provider's reported usage, append-only:

1. **Total input tokens** (`prompt_tokens`). Compare with 10,058 plus the other prompt parts to check the tokenizer assumption.
2. **Cached input tokens** (`cached_tokens` or the equivalent field). Shows whether the handbook was read from the cache, and how many tokens of it.
3. **Cache-write tokens**, if reported. Settles the primary vs. alternative billing scenario for the first call.
4. **Output tokens** (`completion_tokens`).
5. **Model actually used**, as returned by Portkey. Confirms the call went to gpt-6-luna.
6. **Cost per call** computed from the reported usage and `prices.json`, plus Portkey's reported cost if available.
7. **Call order and time.** Shows whether caching starts on call 2, and lets us spot expiry or misses during parallel calls.
8. **Prompt prefix check:** confirm the handbook is byte-identical and in the same position on every call (for example, by comparing a hash), so any cache miss can be explained.
9. **Cache-hit rate** across the run: calls with cached tokens > 0, divided by calls after the first.

The checklist lists what to measure; it does not design the Problem 4 experiment.
