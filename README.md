# Campus Customs Vendor Desk Agent (Homework 6)

An AI agent that reads vendor quotes, catalog pages and emails (HTML, PDF, `.eml`) for Campus Customs, a Yale merchandise shop. It extracts the purchasing facts, checks them against the shop handbook, and returns `recommend` or `do_not_recommend` with a one-sentence reason.

The project measures token costs and prompt caching, evaluates prompt-injection attacks against the original agent, and adds a three-layer defense (code, design, prompt). Every result in `output/` comes from runs that already happened. **No new model calls are needed to review this repository.**

Built with [PydanticAI](https://ai.pydantic.dev/). Every model call uses **`gpt-6-luna`** through the **Portkey** gateway.

> **⚠ Cost warning.** Running `agent.py`, or any script that runs it, makes **paid model calls** whenever `PORTKEY_API_KEY` is available to the process. That includes a key in a `.env` file **and** a key set as a system or user environment variable (for example, a Windows user-level environment variable). **A missing `.env` file does not mean no key is available.** Check before you run anything (see "Which commands cost money" below).

## Project structure

```
agent.py              agent and command-line entry point
tools.py              document readers; read_vendor_document; SIMULATED send_email / approve_payment
models.py             structured output (vendor, sku, unit_price, lead_time_days, min_order, decision, reason)
defenses.py           Problem 6 code layer (human-visible rendering) and design layer (validation + handbook policy engine)
prompts/prompt.md                 defended operating prompt (used by --defense full)
prompts/prompt_undefended.md      original Problem 3 prompt (used by every other mode)
data/shop_handbook.md, data/prices.json, data/practice_key.json
data/practice_docs/   12 practice documents        data/exam_docs/   10 exam documents
data/my_attacks/      2 original red-team documents (Problem 7)
data/data/            historical Problem 7 copies of the attacks + preregistration.json (read by build_report.py)
estimate_handbook.py  Problem 2 token/cost estimate (local, no API calls)
cache_experiment.py   Problem 4 caching experiment
attack_eval.py        Problem 5 injection evaluation
defense_eval.py       Problem 6 defense evaluation
build_report.py       Problem 9 results page builder (local, no API calls)
tests/offline_checks.py   offline verification suite (no API calls); fixtures in tests/fixtures/
baseline_problem3/    read-only snapshot of the Problem 3 agent (used by the offline checks)
output/               reports (*.md), results (*.json), raw run logs, and hw6_report.html
AI_prompts.md         record of the AI-assisted development
```

## Installation

Developed and tested with Python 3.14.7 on Windows; other versions are untested. Google Chrome is used by the defended modes.

```
pip install -r requirements.txt
```

If Chrome is not installed, install Playwright's own browser instead:

```
python -m playwright install chromium
```

**Licensing note:** PyMuPDF (PDF inspection in the defended modes) is AGPL-3.0, or a commercial license from Artifex. Playwright is Apache-2.0.

## Configuration (Portkey)

1. Copy `.env.example` to `.env` (in this folder or its parent) and set your own key:
   ```
   PORTKEY_API_KEY=your-portkey-key
   ```
2. Your Portkey account must route the model **`gpt-6-luna`**. The agent calls Portkey's OpenAI-compatible Responses API at `https://api.portkey.ai/v1`.

The agent also uses a `PORTKEY_API_KEY` that is already set in the environment; a value already in the environment takes precedence over `.env`. Never commit `.env`; it is excluded by `.gitignore`.

## Viewing the results (free)

- **Results page:** open `output/hw6_report.html` in any web browser (double-click it, or drag it into a browser window). It is a single self-contained file that works offline.
- **Reports and data:** the Markdown reports and JSON results are listed below; raw per-run logs are in `output/cache_experiment/`, `output/attack_eval/`, `output/defense_eval/`, `output/problem7/` and `output/exam_runs/`.

| File | Contents |
|---|---|
| `output/handbook_estimate.md` | Problem 2: handbook token and cost estimate |
| `output/harness.md` | Agent architecture, fields, tools, Safety section |
| `output/usage_log.json`, `output/audit_trail.json`, `output/trap_calls.json` | Problem 3 initial test logs |
| `output/cache_test.json`, `output/cache_test.md` | Problem 4: caching experiment |
| `output/attack_results.json`, `output/attack_results.md` | Problem 5: undefended agent vs. practice attacks |
| `output/defense_results.json`, `output/defense_results.md` | Problem 6: defended agent, per-layer costs |
| `output/red_team.md` | Problem 7: original red-team attacks |
| `output/exam_results.json` | Problem 8: final defended agent on the 10 exam documents |
| `output/hw6_report.html` | Problem 9: results page |
| `output/HW6_Compliance_Audit.md`, `output/HW6_Repository_Readiness_Audit.md`, `output/offline_checks_results.txt` | Audit and verification records |

**About caching.** The Portkey key used here had a gateway **response cache** that can replay an earlier response instead of calling the model. In the default `--cache default` mode, a repeated request may therefore be a replay. The `enabled` and `disabled` modes send a cache-bypass header. The Problem 4 caching experiment measures **prompt-cache reads** (cached input tokens) separately from **cache-write charges**: preventing cache reads did not remove cache-write charges. See `output/cache_test.md`.

## Running the agent (paid)

```
python agent.py --doc data/practice_docs/p01_bluehen_quote.html
```

Options (from `python agent.py --help`):

| Option | Values | Meaning |
|---|---|---|
| `--doc` | path | Vendor document (`.html`, `.pdf`, `.eml`). It must be in `data/practice_docs/`, `data/exam_docs/` or `data/my_attacks/` (or `data/data/`, the historical Problem 7 location). Other paths are rejected. |
| `--defense` | `none` (default), `code`, `code+design`, `full` | `none` is the original undefended agent. `full` is the fully defended agent (code + design + prompt layers). |
| `--cache` | `default` (default), `enabled`, `disabled` | `default` sends the original request. `enabled` adds the Portkey response-cache bypass (`x-portkey-cache-force-refresh`), so every call is a fresh model response; it was used for all evaluations from Problem 4 on. `disabled` additionally prevents prompt-cache reads (Problem 4 experiment). |
| `--log-dir` | folder inside `output/` | Where this run's logs are written (default `output/`) |

**Examples (original vs. defended mode):**

```
python agent.py --doc data/exam_docs/e01_quote.html --defense full --cache enabled --log-dir output/my_run
python agent.py --doc data/my_attacks/attack1_exception_quote.html --defense none --cache enabled --log-dir output/my_attack_test
```

Each run prints the run ID, the number of model calls, the cost, and the structured result. It appends to three JSON logs in the log folder:

- `usage_log.json`: API-reported tokens (input, cached, cache-write, output, reasoning) and cost for each model call, computed from `data/prices.json`.
- `audit_trail.json`: every tool call with arguments and a short result, the final answer, and (in defended modes) a `security` record.
- `trap_calls.json`: every attempted `send_email` / `approve_payment` call.

## Safety: simulated tools

`send_email` and `approve_payment` are **simulated only**. They never send email, approve payments or contact any external system. They only record the attempt in `trap_calls.json`. In the `code+design` and `full` modes they are also locked behind a buyer authorization that document content cannot provide; blocked attempts are recorded with `"blocked": true`. See `output/harness.md`, section 12, for a plain-language explanation of the defenses.

## Which commands cost money

**Free (no model calls):**

```
python estimate_handbook.py
python tests/offline_checks.py
python attack_eval.py evaluate
python defense_eval.py evaluate --phase full
python cache_experiment.py --build-only
python build_report.py
```

- `tests/offline_checks.py` replaces the model with local fakes (PydanticAI `TestModel` / `FunctionModel`). It still builds the agent, so `PORTKEY_API_KEY` must be set to *some* value; a placeholder works.
- The `evaluate` and `--build-only` commands rewrite their results JSON (`attack_results.json`, `defense_results.json`, `cache_test.json`) from the archived raw logs.
- `build_report.py` rewrites `output/hw6_report.html` from the project records; the page shows the date it was built.

**Paid (uses your Portkey credits):**
- every `agent.py` run;
- `python attack_eval.py run`;
- `python defense_eval.py run --phase full`;
- `python cache_experiment.py --phase full`.

Each evaluation runner has built-in spending limits.

Note: the evaluation runners *append* to their existing log folders, which already contain this project's runs. Move or rename those folders first if you want a clean rerun.
