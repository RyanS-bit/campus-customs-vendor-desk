"""Problem 4: prompt-caching experiment runner.

Runs agent.py (unchanged agent, same CLI) on vendor documents under --cache disabled and
--cache enabled, then rebuilds output/cache_test.json from the experiment's append-only logs.

    python cache_experiment.py --phase preliminary --docs p01_bluehen_quote.html
    python cache_experiment.py --phase full            # all 12 practice documents, paired + alternating,
                                                       # stops on any cached read (disabled), non-REFRESH
                                                       # Portkey status, failed run, or spend > $0.08
                                                       # (simulated trap calls are recorded, not a stop)
    python cache_experiment.py --build-only            # rebuild cache_test.json from existing logs

Each phase writes its operational logs to output/cache_experiment/<phase>/, separate from
the Problem 3 logs in output/. Failed runs are recorded and never retried automatically.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools import append_json_records

ROOT = Path(__file__).resolve().parent
PRACTICE = ROOT / "data" / "practice_docs"
EXP_DIR = ROOT / "output" / "cache_experiment"
CACHE_TEST = ROOT / "output" / "cache_test.json"
PRICES = json.loads((ROOT / "data" / "prices.json").read_text(encoding="utf-8"))["gpt-6-luna"]
PHASE_NOTES = {
    "preliminary": "SUPERSEDED approach: 'disabled' = prompt_cache_options mode 'explicit' (ignored by provider). "
                   "Runs 1-3 were Portkey response-cache replays (excluded); run 4 used force-refresh but still "
                   "read cached tokens. Kept as evidence only.",
    "preliminary_option_a": "Option A verification: 'disabled' = fresh per-call Request ID line first; "
                            "both conditions use Portkey force-refresh.",
    "full": "Full 12-document comparison under Option A. Paired design: each document runs under both "
            "conditions before the next; the first condition alternates (odd positions: disabled first).",
}
CONDITIONS = ["disabled", "enabled"]
COST_STOP_USD = 0.08  # full batch stops if measured spend exceeds this (approved estimate: $0.04-0.055)


def run_one(phase: str, condition: str, name: str, extra: dict | None = None) -> dict:
    """Run agent.py once and append a record of the run (never retried)."""
    log_dir = EXP_DIR / phase
    doc = PRACTICE / name
    cmd = [sys.executable, "agent.py", "--doc", str(doc.relative_to(ROOT)),
           "--cache", condition, "--log-dir", str(log_dir.relative_to(ROOT))]
    started = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    match = re.search(r"run_id: (\S+)", proc.stdout)
    record = {"phase": phase, "condition": condition, "document": name, "started": started, **(extra or {}),
              "run_id": match.group(1) if match else None, "exit_code": proc.returncode,
              "stderr_tail": proc.stderr.strip()[-500:] or None}
    append_json_records(log_dir / "runs.json", [record])
    lines = proc.stdout.splitlines()
    print(f"[{phase}/{condition}] {name}: exit {proc.returncode}  {lines[1] if len(lines) > 1 else proc.stderr.strip()[-200:]}")
    return record


def run_batch(phase: str, docs: list[str], conditions: list[str]) -> None:
    for condition in conditions:
        for name in docs:
            run_one(phase, condition, name)


def safeguard_problems(phase: str, record: dict) -> list[str]:
    """Stop conditions checked after every run of the full experiment."""
    problems = []
    if record["exit_code"] != 0 or not record["run_id"]:
        problems.append(f"run failed (exit {record['exit_code']})")
    rows = [u for u in _load(EXP_DIR / phase / "usage_log.json") if u["run_id"] == record["run_id"]]
    for u in rows:
        status = ((u.get("provider_raw") or {}).get("portkey_headers") or {}).get("x-portkey-cache-status")
        if status != "REFRESH":
            problems.append(f"call {u['call_index']}: Portkey cache status {status!r}, not a verified fresh model call")
        if record["condition"] == "disabled" and u["cache_read_tokens"] != 0:
            problems.append(f"call {u['call_index']}: {u['cache_read_tokens']} cached tokens in the no-cache-reads condition")
    spent = sum(u["cost_usd"] for u in _load(EXP_DIR / phase / "usage_log.json"))
    if spent > COST_STOP_USD:
        problems.append(f"measured spend ${spent:.5f} exceeds the ${COST_STOP_USD} stop threshold")
    return problems


def run_paired(phase: str, docs: list[str]) -> bool:
    """Paired design: each document under both conditions before the next document.
    The first condition alternates by document position (1st doc: disabled first, 2nd: enabled first, ...)."""
    sequence = 0
    for pair_index, name in enumerate(docs, start=1):
        order = CONDITIONS if pair_index % 2 == 1 else CONDITIONS[::-1]
        for position, condition in enumerate(order, start=1):
            sequence += 1
            record = run_one(phase, condition, name, {"pair_index": pair_index, "position_in_pair": position,
                                                      "global_sequence": sequence})
            problems = safeguard_problems(phase, record)
            if problems:
                print(f"STOPPED after {name} / {condition}: " + "; ".join(problems))
                append_json_records(EXP_DIR / phase / "runs.json", [{
                    "phase": phase, "type": "experiment_stopped", "after_run_id": record["run_id"],
                    "reasons": problems, "time": datetime.now(timezone.utc).isoformat()}])
                return False
    return True


def _load(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def build_cache_test() -> dict:
    calls, runs, stops = [], [], []
    for phase_dir in sorted(p for p in EXP_DIR.iterdir() if p.is_dir()) if EXP_DIR.exists() else []:
        phase = phase_dir.name
        phase_runs = _load(phase_dir / "runs.json")
        errors = {r["run_id"]: r.get("error") for r in _load(phase_dir / "audit_trail.json") if r["type"] == "run_error"}
        usage = _load(phase_dir / "usage_log.json")
        for r in phase_runs:
            if r.get("type") == "experiment_stopped":
                stops.append(r)
                continue
            n = sum(1 for u in usage if u["run_id"] == r["run_id"])
            runs.append({**r, "model_calls": n, "error": errors.get(r["run_id"])})
        for u in usage:
            raw = u.get("provider_raw") or {}
            raw_usage = raw.get("usage") or {}
            raw_in = raw_usage.get("input_tokens_details") or {}
            portkey_cache = (raw.get("portkey_headers") or {}).get("x-portkey-cache-status")
            calls.append({
                "phase": phase,
                # A Portkey response-cache HIT is a stored replay: the model was not called and the
                # usage block is a copy of the original call's. Such calls are excluded from totals.
                "served_by": "portkey_response_cache_replay" if portkey_cache == "HIT" else "model",
                "portkey_cache_status": portkey_cache,
                "condition": u["cache_condition"],
                "document": u["document"],
                "run_id": u["run_id"],
                "call_index": u["call_index"],
                "timestamp": u["timestamp"],
                "model_requested": u["model_requested"],
                "model_reported": u["model_reported"],
                "provider_response_id": u["provider_response_id"],
                "reported": {  # provider-reported (parsed by PydanticAI from the API usage block)
                    "input_tokens": u["input_tokens"],
                    "cached_input_tokens": u["cache_read_tokens"],
                    "cache_write_tokens": u["cache_write_tokens"],
                    "output_tokens": u["output_tokens"],
                    "reasoning_tokens": u["usage_details"].get("reasoning_tokens"),
                },
                "derived": {  # arithmetic on reported values and data/prices.json (actual pricing)
                    "uncached_input_tokens": u["uncached_input_tokens"],
                    "cost_usd": u["cost_usd"],
                    "cost_breakdown_usd": u["cost_breakdown_usd"],
                },
                "hypothetical": {  # NOT actual pricing: all input at the ordinary rate, no cache read/write
                    "all_input_at_uncached_rate_cost_usd": round(
                        u["input_tokens"] * PRICES["input_per_1m"] / 1e6
                        + u["output_tokens"] * PRICES["output_per_1m"] / 1e6, 10),
                },
                "request_sent": raw.get("request_sent"),
                "raw_matches_parsed": bool(raw_usage) and raw_usage.get("input_tokens") == u["input_tokens"]
                    and (raw_in.get("cached_tokens") or 0) == u["cache_read_tokens"]
                    and raw_usage.get("output_tokens") == u["output_tokens"],
                "provider_raw": raw,
            })

    summary = {}
    for c in calls:
        if c["served_by"] != "model":
            s = summary.setdefault(c["phase"], {}).setdefault("excluded_portkey_replays", {"calls": 0})
            s["calls"] += 1
            continue
        s = summary.setdefault(c["phase"], {}).setdefault(c["condition"], {
            "model_calls": 0, "documents": set(), "input_tokens": 0, "cached_input_tokens": 0,
            "cache_write_tokens": 0, "uncached_input_tokens": 0, "output_tokens": 0,
            "reasoning_tokens": 0, "cost_usd": 0.0, "hypothetical_all_input_uncached_cost_usd": 0.0,
            "calls_with_cached_tokens": 0, "calls_with_cache_writes": 0,
            "max_cached_input_tokens_in_one_call": 0, "calls_raw_mismatch": 0})
        r, d = c["reported"], c["derived"]
        s["model_calls"] += 1
        s["documents"].add(c["document"])
        for k in ("input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens"):
            s[k] += r[k]
        s["reasoning_tokens"] += r["reasoning_tokens"] or 0
        s["uncached_input_tokens"] += d["uncached_input_tokens"]
        s["cost_usd"] += d["cost_usd"]
        s["hypothetical_all_input_uncached_cost_usd"] += c["hypothetical"]["all_input_at_uncached_rate_cost_usd"]
        s["calls_with_cached_tokens"] += r["cached_input_tokens"] > 0
        s["calls_with_cache_writes"] += r["cache_write_tokens"] > 0
        s["max_cached_input_tokens_in_one_call"] = max(s["max_cached_input_tokens_in_one_call"], r["cached_input_tokens"])
        s["calls_raw_mismatch"] += not c["raw_matches_parsed"]
    for phase in summary.values():
        for s in phase.values():
            if "documents" in s:
                s["documents"] = len(s["documents"])
                s["cost_usd"] = round(s["cost_usd"], 10)
                s["hypothetical_all_input_uncached_cost_usd"] = round(s["hypothetical_all_input_uncached_cost_usd"], 10)
    for r in runs:
        s = summary.get(r["phase"], {}).get(r["condition"])
        if s is not None:
            s.setdefault("runs", 0)
            s.setdefault("failed_runs", 0)
            s["runs"] += 1
            s["failed_runs"] += r["exit_code"] != 0

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": "Problem 4 prompt-caching experiment: every model call, rebuilt from output/cache_experiment/*/ logs.",
        "pricing_per_1m_usd": PRICES,
        "phases": PHASE_NOTES,
        "field_notes": {
            "reported": "Provider-reported via the API usage block (input_tokens includes cached and cache-write tokens).",
            "derived": "uncached = input - cached - cache_write; cost (ACTUAL pricing under data/prices.json) = "
                       "uncached*$0.10 + cached*$0.01 + cache_write*$0.125 + output*$0.50, per 1M tokens.",
            "hypothetical": "NOT actual pricing: input_tokens*$0.10 + output*$0.50 per 1M, i.e. as if the provider "
                            "neither read nor wrote any cache. For comparison only.",
            "request_sent": "Evidence from the request actually sent: the per-call ID line (disabled condition) and "
                            "SHA-256 hashes of the instructions without that line and of the tool definitions.",
            "raw_matches_parsed": "True if the raw provider usage block equals the values PydanticAI parsed.",
            "served_by": "'model' = genuine model call; 'portkey_response_cache_replay' = Portkey returned a stored "
                          "response (x-portkey-cache-status HIT), excluded from all totals.",
        },
        "summary": summary,
        "experiment_stops": stops,
        "runs": runs,
        "calls": calls,
    }
    write_report(CACHE_TEST, report)
    return report


def write_report(path: Path, data: dict) -> None:
    """cache_test.json is a derived report, rebuilt in full from the append-only logs."""
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--phase", choices=sorted(PHASE_NOTES))
    p.add_argument("--docs", nargs="*", help="Practice document filenames (default: all 12)")
    p.add_argument("--conditions", nargs="*", choices=CONDITIONS, default=CONDITIONS)
    p.add_argument("--build-only", action="store_true")
    a = p.parse_args()
    if not a.build_only:
        if not a.phase:
            p.error("--phase is required unless --build-only")
        docs = a.docs or sorted(x.name for x in PRACTICE.iterdir())
        if a.phase == "full":
            run_paired(a.phase, docs)
        else:
            run_batch(a.phase, docs, a.conditions)
    report = build_cache_test()
    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
