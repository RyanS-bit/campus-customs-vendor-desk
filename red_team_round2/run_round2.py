"""Problem 7, round 2: PAID live test runner. Do not run without Dr. Ryan's approval.

    python red_team_round2/run_round2.py --check-only    # free: verify documents and plan, no model calls
    python red_team_round2/run_round2.py                 # PAID: 12 runs (2 attacks x 2 configs x 3 repeats)

Safeguards (each stops the batch; nothing is retried):
  - the documents in data/my_attacks/ must match the preregistered SHA-256 values;
  - any failed run, any model call not reporting x-portkey-cache-status REFRESH;
  - cumulative spend above SPEND_STOP_USD (checked before every run, using a worst-case run cost).
Logs go to output/problem7_round2/<attack>_<config>_r<n>/, one folder per run.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PREREG = json.loads((HERE / "preregistration_round2.json").read_text(encoding="utf-8"))
LOG_ROOT = ROOT / "output" / "problem7_round2"
SPEND_STOP_USD = 0.04
WORST_RUN_USD = 0.0025  # largest round-1 run was $0.00198 (cold cache); used as headroom before each run
CONFIGS = {"undefended": "none", "defended": "full"}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def plan() -> list[dict]:
    runs = []
    for r in range(1, PREREG["procedure"]["repeats"] + 1):
        for a in PREREG["attacks"]:
            for cfg, mode in CONFIGS.items():
                runs.append({"attack": a["id"], "file": a["file"], "sha256": a["sha256"], "config": cfg, "defense": mode,
                             "log_dir": f"output/problem7_round2/attack{a['id']}_{cfg}_r{r}"})
    return runs


def spent() -> float:
    return sum(u["cost_usd"] for p in LOG_ROOT.rglob("usage_log.json") for u in json.loads(p.read_text(encoding="utf-8")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args()
    runs = plan()
    for a in PREREG["attacks"]:
        doc = ROOT / "data" / "my_attacks" / a["file"]
        if not doc.exists() or sha(doc) != a["sha256"]:
            print(f"STOP: {doc.relative_to(ROOT)} missing or not the preregistered file.")
            return 1
    print(f"documents verified; {len(runs)} runs planned; stop above ${SPEND_STOP_USD}")
    if args.check_only:
        for r in runs:
            print("  ", r["log_dir"], "--defense", r["defense"])
        return 0
    for r in runs:
        if (ROOT / r["log_dir"]).exists():
            print("skip (already run):", r["log_dir"])
            continue
        if spent() + WORST_RUN_USD > SPEND_STOP_USD:
            print(f"STOP: spend ${spent():.6f} + worst-case run would exceed ${SPEND_STOP_USD}")
            return 1
        cmd = [sys.executable, "agent.py", "--doc", f"data/my_attacks/{r['file']}", "--defense", r["defense"],
               "--cache", "enabled", "--log-dir", r["log_dir"]]
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        usage = json.loads((ROOT / r["log_dir"] / "usage_log.json").read_text(encoding="utf-8")) if (ROOT / r["log_dir"] / "usage_log.json").exists() else []
        status = {u.get("provider_raw", {}).get("portkey_headers", {}).get("x-portkey-cache-status") for u in usage}
        print(f"{r['log_dir']}: exit {proc.returncode}, calls {len(usage)}, Portkey {sorted(map(str, status))}, cost ${sum(u['cost_usd'] for u in usage):.6f}")
        if proc.returncode != 0 or status != {"REFRESH"}:
            print("STOP: failed run or non-REFRESH call.\n", proc.stderr[-800:])
            return 1
    print(f"done; total round-2 spend ${spent():.6f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
