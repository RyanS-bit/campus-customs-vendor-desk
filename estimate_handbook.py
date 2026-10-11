"""Problem 2: estimate handbook token count and cost (no API calls)."""
import json
from pathlib import Path

import tiktoken

ROOT = Path(__file__).resolve().parent
HANDBOOK = ROOT / "data" / "shop_handbook.md"
PRICES = ROOT / "data" / "prices.json"
MODEL = "gpt-6-luna"
CALLS = 1000

# read_text() converts the file's CRLF line endings to LF, as our agent code will.
text = HANDBOOK.read_text(encoding="utf-8")
raw_text = HANDBOOK.read_bytes().decode("utf-8")  # CRLF kept, for comparison
prices = json.loads(PRICES.read_text(encoding="utf-8"))[MODEL]

counts = {name: len(tiktoken.get_encoding(name).encode(text))
          for name in ("o200k_base", "cl100k_base")}
raw_tokens = len(tiktoken.get_encoding("o200k_base").encode(raw_text))
tokens = counts["o200k_base"]

per_token = {k: v / 1_000_000 for k, v in prices.items()}
uncached_one = tokens * per_token["input_per_1m"]
write_one = tokens * per_token["cache_write_per_1m"]
read_one = tokens * per_token["cached_input_per_1m"]

uncached_n = CALLS * uncached_one
cached_n = write_one + (CALLS - 1) * read_one
cached_n_alt = uncached_one + (CALLS - 1) * read_one  # if first call billed as normal input

print(f"chars={len(text)} raw_bytes={len(raw_text.encode('utf-8'))} "
      f"CR={raw_text.count(chr(13))} words={len(text.split())} lines={text.count(chr(10))}")
print(f"tokens o200k_base={counts['o200k_base']} cl100k_base={counts['cl100k_base']} chars/4={len(text)/4:.0f}")
print(f"tokens o200k_base raw file (CRLF kept)={raw_tokens} (+{raw_tokens - tokens})")
print(f"prices={prices}")
print(f"1 call uncached      = ${uncached_one:.8f}")
print(f"1 call cache write   = ${write_one:.8f}")
print(f"1 call cache read    = ${read_one:.8f}")
print(f"{CALLS} uncached      = ${uncached_n:.6f}")
print(f"{CALLS} cached PRIMARY     = ${cached_n:.8f}  (1 cache write + {CALLS-1} reads)")
print(f"{CALLS} cached ALTERNATIVE = ${cached_n_alt:.8f}  (1 normal input + {CALLS-1} reads)")
print(f"savings = ${uncached_n - cached_n:.8f} ({(1 - cached_n/uncached_n)*100:.2f}%)")
print(f"break-even: caching cheaper from call 2 if write+read < 2*input: "
      f"{write_one + read_one:.8f} vs {2*uncached_one:.8f}")

print("\nScaling table (handbook tokens only; PRIMARY cached = 1 write + N-1 reads)")
# 8 decimals shows every value exactly (no rounding ties).
print(f"{'N':>6} {'no caching':>12} {'with caching':>13} {'saved':>13} {'saved %':>8}")
for n in (1, 2, 12, 22, 100, CALLS):
    un = n * uncached_one
    ca = write_one + (n - 1) * read_one
    print(f"{n:>6} {un:>12.8f} {ca:>13.8f} {un - ca:>13.8f} {(1 - ca/un)*100:>7.1f}%")
