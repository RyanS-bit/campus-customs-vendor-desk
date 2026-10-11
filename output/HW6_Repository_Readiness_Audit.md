# Homework 6 — Repository Readiness Audit (Problem 10)

**Date:** 2026-10-11 (audit began 15:48 EDT, from the system clock) · **Auditor:** Claude (development assistant) · **Scope:** the entire `hw6` folder (206 files)

**Method.**
- Read-only inspection, static scans, syntax and import checks, CLI checks.
- A **fresh-clone simulation**: the proposed publication files were copied to a scratch folder with no `.env` above it, and every free workflow was run there.
- Only two project files were changed, as authorized: `AI_prompts.md` (Problem 10 instruction appended, plus an incident record) and this report. A SHA-256 fingerprint of all 206 files, taken at the start, confirms nothing else changed.

> **Incident during this audit: unauthorized paid model calls.** In the first fresh-clone test the auditor ran `agent.py` on two documents, expecting the missing `.env` to stop it before any model call. It did not: `PORTKEY_API_KEY` is set as a **Windows user-level environment variable**, so the agent found the key and called gpt-6-luna.
> - **Calls:** 4 (2 runs × 2 calls). Two were Portkey response-cache replays (`HIT`) and two were genuine (`MISS`).
> - **Cost:** logged $0.00471344 (upper bound); genuine calls ≈ $0.00316832.
> - **Effects:** no tool attempts; logged only inside the scratch copy. The project, its logs and its results are unchanged (fingerprint verified).
> - **This violated the instruction not to make API calls.** No further agent runs were made, and all later checks ran with the key removed from the shell's environment.

---

## 1. Overall readiness

### READY WITH CORRECTIONS

- **No publication blockers were found in the files:**
  - no credentials, secret-like tokens, personal email addresses or machine-specific paths in any file, including all 9 ZIP archives;
  - every required file is present;
  - every result rebuilds identically from the publication candidate.
- **What remains before publishing:**
  - choose what to exclude (archives, historical backups);
  - optionally add two README/.gitignore improvements;
  - keep the Problem 8 prompt gap and this audit's incident transparently recorded;
  - publish through a GitHub account, which requires your sign-in.

## 2. Checklist by problem

| # | Requirement (as specified by Dr. Ryan) | Status | Evidence |
|---|---|---|---|
| 1 | `AI_prompts.md`: authentic prompts, follow-ups, corrections, manual steps; nothing fabricated | **PASS with documented gap** | Verbatim prompts for Problems 1–7, 9, 10 and two appendices. Problem 8's original instruction is an explicit "historical gap" (searched; not recovered). The manual PowerShell record cites verified log parameters only. |
| 2 | `output/handbook_estimate.md`: tokens, per-call and 1,000-call costs, cached and uncached, assumptions and prices | **PASS** | 10,058 tokens; $0.0010058 per call; $1.0058 / $0.10173667 per 1,000 calls; first-call cache write handled; prices from `data/prices.json`; `estimate_handbook.py` reproduces it |
| 3 | `agent.py`, `tools.py`, `models.py`, `prompts/prompt.md`; PydanticAI + `gpt-6-luna` via Portkey; HTML/PDF/.eml; 5 fields; recommend/do_not_recommend with handbook reason; simulated tools logged to `output/trap_calls.json`; usage and audit logs; `output/harness.md` | **PASS** | Imports confirm `gpt-6-luna`, `https://api.portkey.ai/v1`, formats `.html .htm .pdf .eml`. The tools only write JSON. `trap_calls.json` = `[]`. All 234 historical logged calls used `gpt-6-luna`. |
| 4 | `output/cache_test.json` + `.md`; 12 documents × 2 conditions; usage and costs; 0 cached reads when prevented; monthly projection; reads vs. charges distinguished | **PASS** | 24 + 24 calls; maximum cached tokens in the prevented condition = 0; 86.77%; $11.59/month; the report and dashboard state that write charges remained |
| 5 | All 12 documents vs. answer key; JSON + MD; visible vs. hidden; decision, field and trap errors | **PASS** | `attack_results.json/.md`; Errata E1–E4 give the rendered visibility analysis (all 7 attack payloads hidden); 0 trap attempts |
| 6 | Three layers; `defense_results.json/.md`; before/after; tokens; overhead; what was exercised; harness Safety section; no overstatement | **PASS** | 12/12 vs. 8/12; per-layer increments labeled cumulative; code layer credited for the observed corrections; design and prompt layers stated as not live-exercised; `harness.md` §12 |
| 7 | 2 attacks in `data/my_attacks/`; ordinary-looking; tested undefended and defended; `output/red_team.md`; resisted without defenses; re-save uncertainty | **PASS / one item NOT VERIFIED by the auditor** | Files present; 4 runs logged; 0 trap attempts; report states that both attacks failed without defenses; re-save uncertainty documented. *Ordinary appearance and novelty were not reviewed by the auditor* (earlier safety interruptions); Dr. Ryan's own review applies. |
| 8 | 10 documents, defended, unedited; `exam_results.json` with 13 fields; outputs preserved; no accuracy claim; authentic history | **PASS** | 10 entries, 13 fields, correct types; each matches its raw logs; `defense: full`; no accuracy claim; manual execution and the unrecovered prompt documented |
| 9 | `output/hw6_report.html`: self-contained, offline, all sections, real figures, final wording preserved | **PASS** | 0 external references; byte-identical rebuild from the publication candidate; unchanged by this audit |
| 10 | Public repo with README, `.gitignore`, safe `.env.example`, requirements, code, prompts, data, attacks, `AI_prompts.md`, outputs, report; no credentials | **READY WITH CORRECTIONS** | Everything present; `.env.example` has an empty placeholder; no secrets found. Exclusion choices and publication still to do. |

## 3. Missing files or compliance concerns

- **Missing required files:** none.
- **Concerns:**
  1. **Problem 8 verbatim prompt** is unrecovered (documented gap). Grading risk: low to moderate.
  2. **Problem 7 content requirements** (ordinary appearance, novelty) rest on Dr. Ryan's review, not the auditor's.
  3. **Problem titles 9 and 10** were labeled "working title" in `AI_prompts.md`. *Resolved 2026-10-11 (staging phase): Dr. Ryan supplied the official titles, "Results page" and "Push to GitHub and submit the URL", and the log now uses them.*
  4. **Location:** `data/my_attacks/` contains only the two attack documents; `preregistration.json` lives in `data/data/` (an approved decision).

## 4. Security and privacy findings

| Check | Result |
|---|---|
| Portkey key value, in every file and every ZIP member | **Not found** (value never printed) |
| Secret-like tokens (`sk-…`, `Bearer …`, `ghp_…`, AWS keys) | **None** |
| Key/token/password assignments with values | 1 match: `README.md` line 50, `PORTKEY_API_KEY=your-portkey-key`, a **placeholder** (harmless) |
| `.env` files | Only `.env.example` (`PORTKEY_API_KEY=` empty) **[safe]** |
| Personal email addresses (yale.edu, gmail, etc.) | **None.** Only `.example` vendor and buyer addresses. |
| Machine paths (`C:\Users`, `AppData`, the local Windows user-profile name, `OneDrive`) | **None** |
| Full surname | **None.** "Dr. Ryan" appears 36 times in `AI_prompts.md` (your own name in your own coursework; acceptable). |
| Operational identifiers in logs | 290 Portkey trace IDs, 464 provider response IDs, Portkey route `config.targets[2]`, provider `azure-openai`. **Not credentials** and unusable without the key; disclosed for transparency. |
| `.gitignore` | Excludes `.env`, `.env.*` (keeping `.env.example`), key and credential files, Python caches, virtual environments, temp files, editor and agent folders. **It does not exclude `*.zip` or backup files.** Fine if the publication package is assembled from an approved list (recommended); otherwise add patterns. |
| **Local machine** (not a repository issue) | `PORTKEY_API_KEY` is a **Windows user-level environment variable**, readable by any program run under your account. It caused this audit's unintended calls. Consider keeping the key only in `.env`. |

## 5. Reproducibility findings

| Check | Result |
|---|---|
| Syntax (10 Python files) | All compile |
| Imports | `agent`, `tools`, `models`, `defenses`, `attack_eval`, `defense_eval`, `cache_experiment` import cleanly |
| `requirements.txt` vs. imports | Every third-party import is pinned (`pydantic-ai-slim[openai]`, `pydantic`, `httpx2`, `python-dotenv`, `pypdf`, `tiktoken`, `playwright`, `pymupdf`). `openai` is pinned as PydanticAI's runtime dependency. Pins match the installed versions. |
| README commands vs. CLI | Match `--help` for `agent.py` (`--doc`, `--cache`, `--defense`, `--log-dir`), `cache_experiment.py`, `defense_eval.py`, `attack_eval.py` |
| README paths | All exist (remaining matches are generic names and example output folders) |
| Original and defended modes | `--defense none / code / code+design / full` |
| Formats | `.html`, `.htm`, `.pdf`, `.eml` |
| Portkey routing | `OpenAIProvider(base_url="https://api.portkey.ai/v1")`, model `gpt-6-luna` |
| Simulated tools | Code inspection: they write JSON only; the gate blocks them in design modes |
| **Fresh-clone simulation** (publication candidate, no `.env`) | `estimate_handbook.py` OK; `attack_eval.py evaluate`, `defense_eval.py evaluate --phase full`, `cache_experiment.py --build-only` all reproduce results **identical apart from build timestamps**; `build_report.py` reproduces `hw6_report.html` **byte-identically**; `tests/offline_checks.py` **56/56** |
| HTML report | Self-contained (no `src`/`href` to external URLs, no `<link>`, `<img>`, `@import` or network code) |
| Not verifiable without API calls | Live agent behavior for a grader with their own key (by design; needs Portkey access to `gpt-6-luna`) |
| **Reproducibility notes** | (a) **Any `agent.py` run makes paid calls** whenever `PORTKEY_API_KEY` is in the environment; the README could say so explicitly. (b) The default `--cache default` mode doesn't bypass Portkey's response cache, so repeated runs on one Portkey account can be replays (documented in Problem 4). (c) Defended modes need Chrome or `playwright install chromium`. |

**Dependencies that make some optional files necessary:**
- `tests/offline_checks.py` needs `baseline_problem3/`.
- `build_report.py` reads `data/data/preregistration.json`, `output/attack_eval/reviewer_notes.json` and all raw run logs.
- `defense_eval.py` imports `attack_eval.py`.
- `agent.py` imports `defenses.py` and loads `prompts/prompt_undefended.md`.

Excluding any of these breaks reproducibility.

## 6. Proposed publication inventory

**A — Required**

| Group | Files |
|---|---|
| Root | `README.md`, `.gitignore`, `.env.example`, `requirements.txt`, `AI_prompts.md`, `agent.py`, `tools.py`, `models.py`, `defenses.py` (imported by the agent), `estimate_handbook.py` (Problem 2) |
| `prompts/` | `prompt.md`, `prompt_undefended.md` (loaded by the default mode) |
| `data/` | `shop_handbook.md`, `prices.json`, `practice_key.json`, `practice_docs/` (12), `exam_docs/` (10), `my_attacks/` (2) |
| `output/` (required results) | `handbook_estimate.md`, `harness.md`, `usage_log.json`, `audit_trail.json`, `trap_calls.json`, `cache_test.json`, `cache_test.md`, `attack_results.json`, `attack_results.md`, `defense_results.json`, `defense_results.md`, `red_team.md`, `exam_results.json`, `hw6_report.html` |

**B — Useful** (include: evidence and reproducibility)

| Group | Why |
|---|---|
| `cache_experiment.py`, `attack_eval.py`, `defense_eval.py`, `build_report.py` | Reproduce Problems 4–6 and 9 |
| `tests/offline_checks.py`, `tests/fixtures/` (13) | Offline verification (56 checks) |
| `baseline_problem3/` | Required by the tests; proves the undefended baseline |
| `output/cache_experiment/`, `output/attack_eval/`, `output/defense_eval/` (pilot, full, correction, before/after model-input evidence), `output/problem7/`, `output/exam_runs/e01–e10/` | Raw per-call evidence that the reports and builders read |
| `data/data/` (attack copies + `preregistration.json`) | Preregistration is read by `build_report.py`; historical Problem 7 run location, referenced in the docs |
| `output/exam_results_backup.json` | Supporting evidence (your designation) |
| `output/offline_checks_results.txt`, `output/HW6_Compliance_Audit.md`, this report | Verification record |
| `output/problem7/red_team_report.md` | Byte-identical copy of `red_team.md`, referenced in `AI_prompts.md`. Harmless; excluding it leaves a dangling reference. |

**C — Exclude** (keep locally; do **not** delete): see section 7.

## 7. Recommended exclusions

| File | Why it is safe to leave out | Reference left dangling? |
|---|---|---|
| `problem3_review.zip`, `problem4_review.zip`, `problem5_review.zip`, `problem6_pre_eval_review.zip`, `problem6_final_review.zip` | Review packages of files already in the repo; no secrets | Mentioned historically in `AI_prompts.md` (acceptable) |
| `Problem7_Final_Review.zip` | 20 of 25 members are present unzipped. The other 5 are **historical versions** (older `AI_prompts.md`, `README.md`, `agent.py`, a `SHA256SUMS.txt`, and **`agent_backup.py`**, which explains the earlier Problem 7 summary's reference to that filename). No secrets. **Keep it locally** as history. | Mentioned in `AI_prompts.md` |
| `output/problem7.zip`, `output/exam_runs/exam_runs.zip.zip` | Every member (13/13 and 30/30) exists unzipped, byte-identical | Mentioned in `AI_prompts.md` |
| `data.zip` | The original supplied archive; all 25 extracted files are byte-identical in `data/` | Mentioned in Problem 1 |
| `AI_prompts (original).md` | Earlier snapshot of the log; the current log keeps all its lines | Mentioned in `AI_prompts.md` |
| `agent.py (original).txt` | Pre-Problem 7 backup of `agent.py`; not used by any code | Named in `AI_prompts.md` as the backup. Include it instead if you want that reference to resolve. |
| `__pycache__/` (none present now) | Generated by Python | — |

The fresh-clone simulation **excluded exactly the ZIPs and the two backups** (and the duplicate report) and everything still rebuilt and passed. The local originals remain untouched.

## 8. Unresolved academic and grading risks

1. **Problem 8 prompt gap:** documented, not reconstructed.
2. **Problem 7:** content-level requirements rely on your review. Attack 2's re-save is a high-confidence, non-cryptographic match (documented).
3. **Exam:** no answer key. e03 and e06 were recommended while carrying flagged hidden tool requests (documented).
4. **Single-run experiments:** cost differences between layers are within normal variation (documented).
5. **This audit's 4 unauthorized calls** (≈ $0.0032 to $0.0047) need recording in your spending totals. They're recorded in `AI_prompts.md`.
6. **Working titles** for Problems 9 and 10. *Resolved 2026-10-11: the official titles are "Results page" (Problem 9) and "Push to GitHub and submit the URL" (Problem 10).*

## 9. Recommended public repository structure

No restructuring. This preserves every import, path and command:

```
campus-customs-vendor-desk/
├── README.md  .gitignore  .env.example  requirements.txt  AI_prompts.md
├── agent.py  tools.py  models.py  defenses.py
├── estimate_handbook.py  cache_experiment.py  attack_eval.py  defense_eval.py  build_report.py
├── prompts/            prompt.md · prompt_undefended.md
├── data/
│   ├── shop_handbook.md · prices.json · practice_key.json
│   ├── practice_docs/ (12)   exam_docs/ (10)   my_attacks/ (2)
│   └── data/                 historical Problem 7 copies + preregistration.json
├── output/
│   ├── handbook_estimate.md · harness.md · usage_log.json · audit_trail.json · trap_calls.json
│   ├── cache_test.json/.md · attack_results.json/.md · defense_results.json/.md
│   ├── red_team.md · exam_results.json · exam_results_backup.json · hw6_report.html
│   ├── offline_checks_results.txt · HW6_Compliance_Audit.md · HW6_Repository_Readiness_Audit.md
│   ├── cache_experiment/  attack_eval/  defense_eval/  problem7/  exam_runs/e01–e10/
├── tests/              offline_checks.py · fixtures/
└── baseline_problem3/  read-only Problem 3 snapshot (+ MANIFEST.sha256)
```

## 10. Prioritized action plan (next phase; nothing done yet)

1. **Your decisions:**
   - (a) approve the inventory and exclusions above;
   - (b) whether to include `agent.py (original).txt` and `output/problem7/red_team_report.md` (recommended: include the duplicate report, exclude the backup);
   - (c) official titles for Problems 9 and 10;
   - (d) optional README additions: a warning that `agent.py` runs are paid and use any `PORTKEY_API_KEY` in the environment, and a pointer to the Problem 4 Portkey replay note;
   - (e) optionally move the key from the Windows user environment into `.env` only (local hygiene).
2. **Prepare a clean package** by copying the approved files into a new folder outside the current private repository. Use a folder, not `git init` inside `hw6`, because `hw6` sits inside your private `ai-foundations` repository. Originals stay untouched.
3. **Verify the package offline:** fingerprint manifest, secret scan, `tests/offline_checks.py`, the three `evaluate` / `--build-only` rebuilds and `build_report.py`, all with the key unset.
4. **Create the public repository.** This **requires your GitHub sign-in**: GitHub CLI (`gh auth login`) or the website. The assistant will not sign in for you.
5. **Upload** the approved files (first commit, push).
6. **Verify the public repository:** the README renders; `.env` is absent; the file count matches the manifest; `hw6_report.html` can be downloaded and opens offline.
7. **Confirm the final URL.**
8. **Submit the URL through Canvas** (you do this).
