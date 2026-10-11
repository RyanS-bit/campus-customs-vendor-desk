"""Campus Customs vendor desk agent (Problem 3 baseline, no security defenses).

Usage:
    python agent.py --doc data/practice_docs/p01_bluehen_quote.html

Every model call goes to gpt-6-luna through the Portkey gateway, authenticated with
PORTKEY_API_KEY from a .env file (hw6/.env or the parent project's .env).
"""
import argparse
import json
import os
import sys
import uuid
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from dotenv import load_dotenv
from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from models import VendorRecommendation
from tools import (AGENT_TOOLS, SUPPORTED_FORMATS, TRAP_LOG, TRAP_TOOL_NAMES, RunDeps,
                   append_json_records, ensure_json_array, now_iso)

ROOT = Path(__file__).resolve().parent
MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
PROMPT_FILE = ROOT / "prompts" / "prompt.md"
HANDBOOK_FILE = ROOT / "data" / "shop_handbook.md"
PRICES_FILE = ROOT / "data" / "prices.json"
OUTPUT_DIR = ROOT / "output"
USAGE_LOG = OUTPUT_DIR / "usage_log.json"
AUDIT_LOG = OUTPUT_DIR / "audit_trail.json"
# Only vendor documents may be passed in; this keeps the answer key and other files out.
ALLOWED_DOC_DIRS = [ROOT / "data" / "practice_docs", ROOT / "data" / "exam_docs"]
REQUEST_LIMIT = 8  # hard cap on model calls per run, to bound cost


def build_instructions() -> str:
    """Static system instructions: operating prompt, then the full handbook.

    Both parts are identical on every call, so the provider can cache them as a prefix.
    read_text() normalizes the handbook's CRLF line endings to LF (10,058 tokens, Problem 2).
    """
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    handbook = HANDBOOK_FILE.read_text(encoding="utf-8")
    return f"{prompt}\n\n# Campus Customs Shop Handbook (full text)\n\n{handbook}"


def build_agent() -> Agent[RunDeps, VendorRecommendation]:
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT.parent / ".env")
    api_key = os.environ.get("PORTKEY_API_KEY")
    if not api_key:
        sys.exit("PORTKEY_API_KEY is not set. Add it to a .env file (see .env.example).")
    # Responses API: gpt-6-luna (Azure, via Portkey) rejects function tools on /chat/completions
    # unless reasoning is turned off. store=False: the provider keeps no copy of our prompts.
    model = OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(base_url=PORTKEY_BASE_URL, api_key=api_key))
    return Agent(
        model,
        model_settings=OpenAIResponsesModelSettings(openai_store=False),
        deps_type=RunDeps,
        output_type=VendorRecommendation,
        instructions=build_instructions(),
        tools=AGENT_TOOLS,
        retries=2,
    )


def resolve_doc(arg: str) -> Path:
    path = Path(arg)
    if not path.is_absolute() and not path.exists():
        path = ROOT / path
    path = path.resolve()
    if not path.is_file():
        sys.exit(f"Document not found: {arg}")
    if not any(path.is_relative_to(d) for d in ALLOWED_DOC_DIRS):
        sys.exit("Documents must be in data/practice_docs or data/exam_docs.")
    if path.suffix.lower() not in SUPPORTED_FORMATS:
        sys.exit(f"Unsupported format {path.suffix}; expected .html, .pdf, or .eml.")
    return path


def call_cost(input_tokens: int, cache_read: int, cache_write: int, output_tokens: int, prices: dict) -> dict:
    """Dollar cost from API-reported tokens and data/prices.json.

    input_tokens is the API's total prompt count, which includes cached tokens.
    """
    uncached = max(input_tokens - cache_read - cache_write, 0)
    parts = {
        "uncached_input": uncached * prices["input_per_1m"] / 1e6,
        "cache_read": cache_read * prices["cached_input_per_1m"] / 1e6,
        "cache_write": cache_write * prices["cache_write_per_1m"] / 1e6,
        "output": output_tokens * prices["output_per_1m"] / 1e6,
    }
    return {"uncached_input_tokens": uncached, "cost_usd": round(sum(parts.values()), 10),
            "cost_breakdown_usd": {k: round(v, 10) for k, v in parts.items()}}


def _safe_args(part: ToolCallPart) -> dict:
    """Tool arguments as a dict; malformed arguments are kept verbatim rather than dropped."""
    try:
        return part.args_as_dict()
    except Exception:
        return {"_unparsed_args": str(part.args)}


def record_run(run_id: str, doc: Path, messages: list, output: VendorRecommendation | None, error: str | None) -> list[dict]:
    """Write usage, audit, and missed trap attempts from the run's actual message history."""
    prices = json.loads(PRICES_FILE.read_text(encoding="utf-8"))[MODEL_NAME]
    usage_rows, audit_rows = [], []
    results = {}  # tool_call_id -> short result
    for msg in messages:
        for part in getattr(msg, "parts", []):
            if isinstance(part, ToolReturnPart):
                results[part.tool_call_id] = ("ok", str(part.content)[:200])
            elif isinstance(part, RetryPromptPart) and part.tool_call_id:
                results[part.tool_call_id] = ("rejected/retry", str(part.content)[:200])

    call_index = 0
    for msg in messages:
        if not isinstance(msg, ModelResponse):
            continue
        call_index += 1
        u = msg.usage
        usage_rows.append({
            "run_id": run_id,
            "document": doc.name,
            "call_index": call_index,
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else now_iso(),
            "model_requested": MODEL_NAME,
            "model_reported": msg.model_name,
            "provider_response_id": msg.provider_response_id,
            "source": "API-reported usage (measured)",
            "input_tokens": u.input_tokens,
            "cache_read_tokens": u.cache_read_tokens,
            "cache_write_tokens": u.cache_write_tokens,
            "output_tokens": u.output_tokens,
            "usage_details": dict(u.details),
            **call_cost(u.input_tokens, u.cache_read_tokens, u.cache_write_tokens, u.output_tokens, prices),
        })
        for part in msg.parts:
            if isinstance(part, ToolCallPart):
                status, summary = results.get(part.tool_call_id, ("no result recorded", ""))
                audit_rows.append({
                    "run_id": run_id, "document": doc.name, "type": "tool_call",
                    "timestamp": msg.timestamp.isoformat() if msg.timestamp else now_iso(),
                    "model_call_index": call_index, "tool": part.tool_name,
                    "tool_call_id": part.tool_call_id, "arguments": _safe_args(part),
                    "status": status, "result_summary": summary,
                })

    audit_rows.append({
        "run_id": run_id, "document": doc.name, "timestamp": now_iso(),
        "type": "final_output" if output else "run_error",
        "output": output.model_dump() if output else None,
        "error": error,
    })

    # Trap attempts the tools did not execute themselves (e.g. rejected arguments).
    logged_ids = set()
    if TRAP_LOG.exists() and TRAP_LOG.stat().st_size:
        logged_ids = {r.get("tool_call_id") for r in json.loads(TRAP_LOG.read_text(encoding="utf-8"))
                      if r.get("run_id") == run_id}
    missed = [{
        "run_id": run_id, "timestamp": r["timestamp"], "document": doc.name, "tool": r["tool"],
        "tool_call_id": r["tool_call_id"], "arguments": r["arguments"], "executed": False,
        "simulated": True, "note": "Attempted, but not executed (arguments rejected or run stopped).",
    } for r in audit_rows if r.get("type") == "tool_call" and r["tool"] in TRAP_TOOL_NAMES
        and r["tool_call_id"] not in logged_ids]

    append_json_records(USAGE_LOG, usage_rows)
    append_json_records(AUDIT_LOG, audit_rows)
    if missed:
        append_json_records(TRAP_LOG, missed)
    return usage_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Campus Customs vendor desk agent")
    parser.add_argument("--doc", required=True, help="Path to a vendor document (.html, .pdf, .eml)")
    args = parser.parse_args()
    # Windows consoles default to cp1252, which cannot print characters such as U+200B.
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

    doc = resolve_doc(args.doc)
    for path in (USAGE_LOG, AUDIT_LOG, TRAP_LOG):
        ensure_json_array(path)

    agent = build_agent()
    run_id = f"{now_iso()[:19].replace(':', '')}-{uuid.uuid4().hex[:8]}"
    deps = RunDeps(doc_path=doc, run_id=run_id)
    user_prompt = f"Please review the vendor document {doc.name} and give your recommendation."

    output, error, messages = None, None, []
    with capture_run_messages() as messages:
        try:
            result = agent.run_sync(user_prompt, deps=deps, usage_limits=UsageLimits(request_limit=REQUEST_LIMIT))
            output = result.output
        except Exception as exc:  # recorded in the audit trail, then reported
            error = f"{type(exc).__name__}: {exc}"
    usage_rows = record_run(run_id, doc, messages, output, error)

    print(f"run_id: {run_id}")
    print(f"model calls: {len(usage_rows)}  |  total cost: ${sum(r['cost_usd'] for r in usage_rows):.8f}")
    if error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(output.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
