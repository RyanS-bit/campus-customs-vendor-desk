"""Problem 6 defense layers for the vendor desk agent.

Every function here is DETERMINISTIC (no model calls). The model's only judgment in the
defended agent is reading the human-visible document and proposing facts with quotes.

CODE LAYER (before untrusted content reaches the model)
    render_visible_document(path) -> VisibleDocument
        What a human would see: HTML/email rendered in a sandboxed headless browser
        (JavaScript off, network blocked) and PDF spans checked for colour, size and
        position. Hidden or non-displayed content is removed from the model's input and
        kept in a quarantine record for human review. Nothing is silently discarded.
    spotlight(visible) -> str
        Wraps the visible text in a randomly named data boundary.

DESIGN LAYER (after the model proposes facts)
    HandbookPolicy.from_handbook()   purchasing rules parsed from data/shop_handbook.md
    finalize(extraction, visible, policy) -> (VendorRecommendation, security_record)
        Validates each proposed fact against the visible document (label context,
        all candidate values, authoritative revisions), then the policy engine makes
        the decision and writes the one-sentence reason.
"""
from __future__ import annotations

import email
import re
import secrets
from dataclasses import dataclass, field
from email import policy as email_policy
from pathlib import Path

from pydantic import BaseModel, Field

from models import VendorRecommendation

ROOT = Path(__file__).resolve().parent
HANDBOOK_FILE = ROOT / "data" / "shop_handbook.md"
FACTS = ("vendor", "sku", "unit_price", "lead_time_days", "min_order")

# Characters that render as nothing but can split words or reorder text.
INVISIBLE_CHARS = re.compile("[­᠎​-‏‪-‮⁠-⁤﻿]")
MIN_VISIBLE_FONT = 4.0       # px (HTML) / pt (PDF); smaller text is treated as not human-readable
COLOR_MATCH_DISTANCE = 40    # RGB distance under which text colour is treated as matching its background


# =============================================================== CODE LAYER

@dataclass
class VisibleDocument:
    name: str
    format: str
    text: str                                   # what a human sees; the only text the model receives
    removed: list[dict] = field(default_factory=list)   # quarantine: {"text", "reason", "where"}
    flags: list[str] = field(default_factory=list)
    render_ok: bool = True

    def quarantine_summary(self) -> list[dict]:
        return [{"text": r["text"][:300], "reason": r["reason"], "where": r["where"]} for r in self.removed]


def _strip_invisible(text: str, where: str, removed: list[dict]) -> str:
    count = len(INVISIBLE_CHARS.findall(text))
    if count:
        removed.append({"text": f"{count} invisible Unicode character(s)", "reason": "zero-width/bidi control characters", "where": where})
    return INVISIBLE_CHARS.sub("", text)


# --- HTML (also used for email HTML parts) -------------------------------------------

_HTML_VISIBILITY_JS = r"""(cfg) => {
  const removed = [];
  const rgb = (s) => { const m = s && s.match(/rgba?\(([^)]+)\)/); if (!m) return null;
                       const p = m[1].split(',').map(x => parseFloat(x)); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const bgOf = (el) => { for (let e = el; e; e = e.parentElement) { const c = rgb(getComputedStyle(e).backgroundColor);
                         if (c && c[3] > 0) return c; } return [255, 255, 255, 1]; };
  const opacityOf = (el) => { let o = 1; for (let e = el; e; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity); return o; };
  // 1. Comments and non-displayed elements (their text never appears to a reader).
  const walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_COMMENT);
  const comments = []; let c; while ((c = walker.nextNode())) comments.push(c);
  for (const n of comments) { const t = n.textContent.trim(); if (t) removed.push({text: t, reason: 'HTML comment'}); n.remove(); }
  // Stylesheets stay in place: they decide what is visible (innerText never includes them).
  for (const el of document.querySelectorAll('script, noscript, template')) {
    const t = el.textContent.trim(); if (t) removed.push({text: t, reason: '<' + el.tagName.toLowerCase() + '> element'});
    el.remove();
  }
  // 2. Text nodes a reader cannot see, judged on the rendered result.
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const texts = []; let t; while ((t = tw.nextNode())) texts.push(t);
  const W = document.documentElement.scrollWidth, H = document.documentElement.scrollHeight;
  for (const node of texts) {
    const txt = node.textContent.trim(); if (!txt) continue;
    const el = node.parentElement, cs = getComputedStyle(el);
    const r = document.createRange(); r.selectNodeContents(node); const box = r.getBoundingClientRect();
    let why = null;
    if (el.getClientRects().length === 0) why = 'not rendered (display:none or equivalent)';
    else if (cs.visibility !== 'visible') why = 'visibility:' + cs.visibility;
    else if (opacityOf(el) < 0.05) why = 'transparent (opacity)';
    else if (parseFloat(cs.fontSize) < cfg.minFont) why = 'font-size ' + cs.fontSize;
    else if (box.width < 1 || box.height < 1) why = 'zero-size or clipped';
    else if (box.right < 0 || box.bottom < 0 || box.left > W + 50 || box.top > H + 50) why = 'positioned off-page';
    else { const fg = rgb(cs.color), bg = bgOf(el);
           if (fg && fg[3] < 0.05) why = 'transparent text colour';
           else if (fg && Math.hypot(fg[0]-bg[0], fg[1]-bg[1], fg[2]-bg[2]) < cfg.colorDist) why = 'text colour matches background'; }
    if (why) { removed.push({text: txt, reason: why}); node.textContent = ''; }
  }
  return {text: document.body ? document.body.innerText : '', removed};
}"""

_browser = None
_renderer_thread = None


def _on_renderer(fn, *args):
    """Run browser work on one dedicated thread. Playwright's sync API takes over the calling
    thread's event loop, which would break the agent's own (asyncio) run if done on the main thread."""
    global _renderer_thread
    from concurrent.futures import ThreadPoolExecutor
    if _renderer_thread is None:
        _renderer_thread = ThreadPoolExecutor(max_workers=1, thread_name_prefix="renderer")
    return _renderer_thread.submit(fn, *args).result()


def _get_browser():
    """One sandboxed headless browser (on the renderer thread): JavaScript disabled, all network blocked."""
    global _browser
    if _browser is None:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(channel="chrome", headless=True, args=["--mute-audio"])
        except Exception:
            browser = pw.chromium.launch(headless=True, args=["--mute-audio"])  # bundled Chromium fallback
        context = browser.new_context(java_script_enabled=False, offline=True, accept_downloads=False)
        context.route("**/*", lambda route: route.abort())  # no fetches of any kind (images, CSS, fonts, links)
        _browser = (pw, browser, context)
    return _browser[2]


def close_renderer() -> None:
    global _browser, _renderer_thread
    def _close():
        global _browser
        if _browser is not None:
            pw, browser, _ = _browser
            browser.close()
            pw.stop()
            _browser = None
    if _renderer_thread is not None:
        _on_renderer(_close)
        _renderer_thread.shutdown()
        _renderer_thread = None


def _render_html_in_browser(html: str) -> dict:
    page = _get_browser().new_page()
    try:
        page.set_content(html, wait_until="domcontentloaded")
        return page.evaluate(_HTML_VISIBILITY_JS, {"minFont": MIN_VISIBLE_FONT, "colorDist": COLOR_MATCH_DISTANCE})
    finally:
        page.close()


def render_html_visible(html: str, where: str, removed: list[dict]) -> str:
    result = _on_renderer(_render_html_in_browser, html)
    for r in result["removed"]:
        removed.append({"text": INVISIBLE_CHARS.sub("", r["text"]), "reason": r["reason"], "where": where})
    return _strip_invisible(result["text"], where, removed)


# --- PDF ----------------------------------------------------------------------------

def _rgb_int(c) -> tuple[int, int, int]:
    if isinstance(c, (list, tuple)):  # floats 0..1
        vals = [round(255 * float(x)) for x in c[:3]] if c else [0, 0, 0]
        return tuple(vals + [0] * (3 - len(vals)))[:3]
    c = int(c or 0)
    return (c >> 16) & 255, (c >> 8) & 255, c & 255


def _dist(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def render_pdf_visible(path: Path, removed: list[dict]) -> str:
    import pymupdf
    doc = pymupdf.open(path)
    meta = {k: v for k, v in (doc.metadata or {}).items() if v and str(v).strip()}
    if meta:
        removed.append({"text": "; ".join(f"{k}: {v}" for k, v in meta.items()), "reason": "PDF metadata (not displayed on the page)", "where": "metadata"})
    lines_out = []
    for pno, page in enumerate(doc, start=1):
        where = f"page {pno}"
        invisible_boxes = [pymupdf.Rect(s["bbox"]) for s in page.get_texttrace()
                           if s.get("type") == 3 or float(s.get("opacity", 1)) < 0.05]
        fills = [(pymupdf.Rect(d["rect"]), _rgb_int(d["fill"])) for d in page.get_drawings() if d.get("fill")]
        for annot in page.annots() or []:
            info = (annot.info or {}).get("content", "")
            if info.strip():
                removed.append({"text": info, "reason": "PDF annotation (not part of the page text)", "where": where})
        # No clipping: PyMuPDF clips to the page by default, which would drop off-page text silently.
        # Reading everything lets the off-page check below quarantine it with a record.
        for block in page.get_text("dict", clip=pymupdf.INFINITE_RECT())["blocks"]:
            for line in block.get("lines", []):
                kept = []
                for span in line["spans"]:
                    text = span["text"]
                    if not text.strip():
                        kept.append(text)
                        continue
                    box = pymupdf.Rect(span["bbox"])
                    centre = pymupdf.Point((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)
                    background = next((col for rect, col in reversed(fills) if centre in rect), (255, 255, 255))
                    why = None
                    if span["size"] < MIN_VISIBLE_FONT:
                        why = f"font size {span['size']:.1f}pt"
                    elif float(span.get("alpha", 255)) < 13:
                        why = "transparent text"
                    elif any(box.intersects(b) for b in invisible_boxes):
                        why = "invisible text render mode"
                    elif not box.intersects(page.rect):
                        why = "positioned off-page"
                    elif _dist(_rgb_int(span["color"]), background) < COLOR_MATCH_DISTANCE:
                        why = "text colour matches background"
                    if why:
                        removed.append({"text": text, "reason": why, "where": where})
                    else:
                        kept.append(text)
                if "".join(kept).strip():
                    lines_out.append("".join(kept))
    return _strip_invisible("\n".join(lines_out), "pdf text", removed)


# --- Email --------------------------------------------------------------------------

DISPLAYED_HEADERS = ("From", "To", "Cc", "Reply-To", "Subject", "Date")


def render_email_visible(path: Path, removed: list[dict], flags: list[str]) -> str:
    msg = email.message_from_bytes(path.read_bytes(), policy=email_policy.default)
    head = [f"{h}: {msg[h]}" for h in DISPLAYED_HEADERS if msg[h]]
    hidden_headers = [f"{k}: {v}" for k, v in msg.items() if k not in DISPLAYED_HEADERS
                      and k.lower() not in ("content-type", "content-transfer-encoding", "mime-version")]
    if hidden_headers:
        removed.append({"text": "; ".join(hidden_headers), "reason": "email headers not shown by mail clients", "where": "headers"})
    plain, html, attachments = None, None, []
    for part in msg.walk():
        if part.is_multipart():
            continue
        if part.get_filename():
            attachments.append(f"{part.get_filename()} ({part.get_content_type()})")
        elif part.get_content_type() == "text/plain" and plain is None:
            plain = part.get_content()
        elif part.get_content_type() == "text/html" and html is None:
            html = part.get_content()
    body = []
    shown_html = render_html_visible(html, "email HTML part", removed) if html is not None else None
    shown_plain = _strip_invisible(plain, "email plain part", removed) if plain is not None else None
    if shown_html is not None:
        body.append("[Email body as displayed]\n" + shown_html.strip())
        # Mail clients show the HTML part; keep the plain part too if it says something different.
        if shown_plain is not None and _numbers(shown_plain) != _numbers(shown_html):
            flags.append("email_parts_disagree")
            body.append("[Plain-text version of the same email, which differs]\n" + shown_plain.strip())
    elif shown_plain is not None:
        body.append(shown_plain.strip())
    if attachments:
        body.append("[Attachments, not read: " + ", ".join(attachments) + "]")
    return "\n".join(head) + "\n\n" + "\n\n".join(body)


def _numbers(text: str) -> list[str]:
    return sorted(re.findall(r"\d+(?:[.,]\d+)?", text))


# --- Entry point and spotlighting ----------------------------------------------------

def render_visible_document(path: Path) -> VisibleDocument:
    """Human-visible content of a vendor document. On failure, fail closed (no raw fallback)."""
    removed, flags = [], []
    suffix = path.suffix.lower()
    fmt = {".html": "HTML", ".htm": "HTML", ".pdf": "PDF", ".eml": "email"}.get(suffix, "unknown")
    try:
        if fmt == "HTML":
            text = render_html_visible(path.read_text(encoding="utf-8", errors="replace"), "page", removed)
        elif fmt == "PDF":
            text = render_pdf_visible(path, removed)
        elif fmt == "email":
            text = render_email_visible(path, removed, flags)
        else:
            raise ValueError(f"unsupported format {suffix}")
    except Exception as exc:  # rendering failure: do not fall back to unvetted raw content
        return VisibleDocument(path.name, fmt, "", removed, flags + [f"render_failed: {type(exc).__name__}: {exc}"], render_ok=False)
    text = re.sub(r"[ \t]+\n", "\n", text).strip()
    if removed:
        flags.append("hidden_content_removed")
        if any(_is_material(r["text"]) for r in removed):
            flags.append("hidden_content_is_material")
    if not text:
        flags.append("no_visible_text")
    return VisibleDocument(path.name, fmt, text, removed, flags)


def _is_material(text: str) -> bool:
    """Hidden text that bears on purchasing or actions (values, identity, payments, contacts).
    Such content is withheld from the model but flagged for the buyer's review."""
    return bool(re.search(
        r"\$\s?\d|\b\d+\s*(?:business\s+|calendar\s+)?days?\b|\b\d+\s*units?\b|CC-[A-Z]{2}-\d{3}"
        r"|[\w.+-]+@[\w-]+\.[\w.]+|\b(?:vendor|supplier|price|pricing|cost|payment|pay|deposit|invoice|e-?mail|approve|send)\b",
        text, re.I))


def spotlight(visible: VisibleDocument) -> str:
    """Wrap the visible text in a random, unguessable data boundary."""
    token = secrets.token_hex(6).upper()
    body = visible.text.replace("<<<", "< < <")  # the boundary syntax cannot be forged from inside
    return (f"Document: {visible.name} (format: {visible.format}; human-visible content only)\n"
            f"Hidden or non-displayed content removed before this point: {len(visible.removed)} item(s), "
            f"withheld and logged for human review.\n"
            f"<<<VENDOR_DOCUMENT_{token}>>>\n{body}\n<<<END_VENDOR_DOCUMENT_{token}>>>")


# =============================================================== DESIGN LAYER

class FactExtraction(BaseModel):
    """Facts proposed by the model. The model does NOT decide; the policy engine does."""

    vendor: str | None = Field(description="Vendor company name as shown in the document; null if not stated.")
    vendor_evidence: str | None = Field(description="Exact quote from the document that shows the vendor name.")
    sku: str | None = Field(description="Campus Customs SKU (CC-XX-000); null if not stated.")
    sku_evidence: str | None = Field(description="Exact quote from the document containing the SKU.")
    unit_price: float | None = Field(description="Quoted price per unit in US dollars; null if not stated.")
    unit_price_evidence: str | None = Field(description="Exact quote from the document containing the unit price.")
    lead_time_days: int | None = Field(description="Lead time in days as the vendor states it; null if not stated.")
    lead_time_evidence: str | None = Field(description="Exact quote from the document containing the lead time.")
    min_order: int | None = Field(description="Minimum order in units; null if not stated.")
    min_order_evidence: str | None = Field(description="Exact quote from the document containing the minimum order.")
    conflicting_values: list[str] = Field(default_factory=list, description=(
        "Every other value the document states for any of these facts (e.g. a second price, a 'revised' "
        "or 'corrected' figure), each as an exact quote. Empty if none."))


@dataclass
class HandbookPolicy:
    """Purchasing rules read from the handbook at runtime (trusted source)."""

    approved: dict[str, str]          # casefolded name -> display name
    removed_or_pending: dict[str, str]
    order_domains: dict[str, str]     # casefolded approved name -> registered order e-mail domain
    max_unit_cost: dict[str, float]   # SKU -> max unit cost
    max_lead_time_days: int
    max_min_order: int

    @classmethod
    def from_handbook(cls, path: Path = HANDBOOK_FILE) -> "HandbookPolicy":
        text = path.read_text(encoding="utf-8")
        sections = {s.split("\n", 1)[0].split(".")[0].strip(): s for s in re.split(r"\n## ", text)[1:]}

        def table(num: str) -> tuple[list[str], list[list[str]]]:
            rows = [[c.strip() for c in ln.strip().strip("|").split("|")]
                    for ln in sections[num].splitlines() if ln.startswith("|") and not ln.startswith("|---")]
            return [h.casefold() for h in rows[0]], rows[1:]

        rules = sections["4"]
        lead = re.search(r"lead time is (\d+) days or less", rules, re.I)
        moq = re.search(r"minimum order is (\d+) units or less", rules, re.I)
        h5, approved_rows = table("5")
        h6, removed_rows = table("6")
        h9, catalogue = table("9")
        vcol, ncol = h5.index("vendor"), h5.index("notes")
        skucol = h9.index("sku")
        costcol = next(i for i, h in enumerate(h9) if "max" in h and "cost" in h)
        if not (lead and moq and approved_rows and removed_rows and catalogue):
            raise ValueError("handbook purchasing rules could not be parsed; refusing to decide")
        domains = {}
        for r in approved_rows:
            m = re.search(r"[\w.+-]+@([\w.-]+\.\w+)", r[ncol])
            if m:
                domains[r[vcol].casefold()] = m.group(1).casefold()
        return cls(
            approved={r[vcol].casefold(): r[vcol] for r in approved_rows},
            removed_or_pending={r[h6.index("vendor")].casefold(): r[h6.index("vendor")] for r in removed_rows},
            order_domains=domains,
            max_unit_cost={r[skucol]: float(r[costcol].replace("$", "").replace(",", "")) for r in catalogue if r[skucol].startswith("CC-")},
            max_lead_time_days=int(lead.group(1)),
            max_min_order=int(moq.group(1)),
        )


# --- Candidate values in the visible document (deterministic scanner) -----------------

_MONEY = r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
_LABELS = {
    "unit_price": r"unit\s*price|price\s*(?:per|/)\s*(?:unit|piece|item)|per[-\s]unit\s*(?:price|cost)|unit\s*cost",
    "lead_time_days": r"lead\s*time|turnaround|production\s*time|delivery\s*time",
    "min_order": r"minimum\s*order(?:\s*quantity)?|min\.?\s*order|\bmoq\b",
}
_VALUE = {
    "unit_price": _MONEY,
    "lead_time_days": r"(\d{1,3})\s*(?:business\s+|calendar\s+|working\s+)?days?\b",
    "min_order": r"(\d{1,3}(?:,\d{3})*|\d+)\s*(?:units?|pcs|pieces|items)\b",
}
_SUPERSEDED = r"\b(?:was|previously|formerly|old|revised\s+from|down\s+from|reduced\s+from|replac\w*|instead\s+of)\s*:?\s*"
_SKU = re.compile(r"\bCC-[A-Z]{2}-\d{3}\b")


def _num(field: str, raw: str):
    raw = raw.replace(",", "")
    return float(raw) if field == "unit_price" else int(raw)


def scan_candidates(text: str, fact: str) -> list[dict]:
    """Every value stated for a fact, with its line, whether it sits in a labelled field, and
    whether that same labelled line explicitly marks it as superseded."""
    out = []
    label, value = _LABELS[fact], _VALUE[fact]
    for ln_no, line in enumerate(text.splitlines()):
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", line):
            lab = re.search(label, sentence, re.I)
            if not lab:
                continue
            tail = sentence[lab.end():]
            labeled = bool(re.match(rf"^\s*(?:[-*•]\s*)?(?:{label})\s*(?::|\t|\s{{2,}}|-\s)", sentence, re.I))
            for m in re.finditer(value, tail, re.I):
                if m.start() > 120:
                    break
                before = tail[max(0, m.start() - 25):m.start()]
                out.append({"value": _num(fact, m.group(1)), "line": ln_no, "text": sentence.strip()[:200],
                            "labeled": labeled, "superseded": labeled and bool(re.search(_SUPERSEDED + r"\$?\s*$", before, re.I))})
    return out


def analyse_conflict(cands: list[dict]) -> dict:
    """A value is resolved only if the document's formal (labelled) terms establish it.
    Clearly authoritative revision: the labelled field itself carries the new value and marks the
    old value as superseded, or the document states only one value. A prose note contradicting the
    labelled terms is an unresolved conflict (a purchasing-safety judgment, not an accusation)."""
    if not cands:
        return {"status": "not_found", "values": []}
    superseded = {c["value"] for c in cands if c["superseded"]}
    labeled = {c["value"] for c in cands if c["labeled"] and not c["superseded"]}
    prose = {c["value"] for c in cands if not c["labeled"]}
    values = sorted({c["value"] for c in cands})
    if len(labeled) == 1 and prose <= labeled | superseded:
        status = "authoritative_revision" if superseded else "single_value"
        return {"status": status, "resolved": next(iter(labeled)), "values": values, "superseded": sorted(superseded)}
    if not labeled and len(prose) == 1:
        return {"status": "single_value", "resolved": next(iter(prose)), "values": values}
    return {"status": "unresolved_conflict", "values": values,
            "formal_value": next(iter(labeled)) if len(labeled) == 1 else None,
            "evidence": [c["text"] for c in cands]}


# --- Evidence validation -------------------------------------------------------------

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", INVISIBLE_CHARS.sub("", s or "")).strip().casefold()


def _quote_supports(quote: str | None, visible: str, value, fact: str) -> dict:
    """Is the model's quote really in the visible document, does it contain the value, and is it
    in the right context (the fact's label)?"""
    if not quote:
        return {"in_document": False, "contains_value": False, "label_context": False}
    q = _norm(quote)
    in_doc = bool(q) and q in _norm(visible)
    if value is None:
        contains = False
    elif fact == "unit_price":
        contains = any(abs(float(m.replace(",", "")) - float(value)) < 0.005 for m in re.findall(r"\d[\d,]*\.?\d*", quote))
    else:
        contains = _norm(str(value)) in q
    context = bool(re.search(_LABELS[fact], quote, re.I)) if fact in _LABELS else True
    return {"in_document": in_doc, "contains_value": contains, "label_context": context}


def validate(extraction: FactExtraction, visible: VisibleDocument, policy: HandbookPolicy) -> dict:
    text = visible.text
    report = {}
    for fact in ("unit_price", "lead_time_days", "min_order"):
        value = getattr(extraction, fact)
        quote = getattr(extraction, "lead_time_evidence" if fact == "lead_time_days" else f"{fact}_evidence")
        support = _quote_supports(quote, text, value, fact)
        conflict = analyse_conflict(scan_candidates(text, fact))
        if conflict["status"] == "unresolved_conflict":
            status, final = "conflict", conflict.get("formal_value") if conflict.get("formal_value") is not None else value
        elif conflict["status"] in ("single_value", "authoritative_revision"):
            if value is not None and abs(float(value) - float(conflict["resolved"])) < 0.005:
                status, final = "verified", conflict["resolved"]
            else:
                status, final = "contradicts_document", conflict["resolved"]
        elif value is not None and all(support.values()):
            status, final = "verified_by_quote", value      # unfamiliar layout: quote checks only
        else:
            status, final = ("not_stated" if value is None else "unverified"), value
        report[fact] = {"model_value": value, "final_value": final, "status": status,
                        "quote": quote, "quote_checks": support, "document_values": conflict}

    # SKU: must be visible; several different SKUs is a conflict.
    skus = sorted(set(_SKU.findall(text)))
    sku = extraction.sku
    if sku and sku in skus and len(skus) == 1:
        sku_status = "verified"
    elif len(skus) > 1:
        sku_status = "conflict"
    elif sku and sku in skus:
        sku_status = "verified"
    else:
        sku_status = "not_stated" if not sku else "unverified"
    report["sku"] = {"model_value": sku, "final_value": sku if sku_status != "unverified" else sku,
                     "status": sku_status, "document_values": {"values": skus},
                     "quote_checks": _quote_supports(extraction.sku_evidence, text, sku, "sku")}

    # Vendor identity: visible name, handbook-listed names, and contact domains (trusted handbook vs vendor claim).
    vendor = (extraction.vendor or "").strip()
    vtext = _norm(text)
    named = sorted({disp for key, disp in {**policy.approved, **policy.removed_or_pending}.items()
                    if re.search(rf"\b{re.escape(key)}\b", vtext)})
    domains = sorted({d.casefold() for d in re.findall(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)", text)})
    registered = policy.order_domains.get(vendor.casefold())
    issues = []
    if vendor and _norm(vendor) not in vtext:
        issues.append("vendor name not in the visible document")
    if vendor.casefold() in policy.approved and any(n.casefold() in policy.removed_or_pending for n in named):
        issues.append("document also names a removed or pending vendor")
    if len([n for n in named if n.casefold() in policy.approved]) > 1:
        issues.append("document names more than one approved vendor")
    if registered and domains and registered not in domains:
        issues.append(f"contact domain(s) {domains} do not include the handbook's registered domain {registered}")
    if not vendor:
        v_status = "not_stated"
    elif issues:
        v_status = "conflict"
    else:
        v_status = "verified"
    report["vendor"] = {"model_value": extraction.vendor, "final_value": extraction.vendor, "status": v_status,
                        "issues": issues, "handbook_vendors_named": named, "contact_domains": domains,
                        "handbook_registered_domain": registered,
                        "quote_checks": _quote_supports(extraction.vendor_evidence, text, extraction.vendor, "vendor")}
    report["model_reported_conflicts"] = extraction.conflicting_values
    return report


# --- Policy engine and reason --------------------------------------------------------

GOOD = ("verified", "verified_by_quote")
LABEL = {"vendor": "vendor", "sku": "SKU", "unit_price": "unit price", "lead_time_days": "lead time", "min_order": "minimum order"}


def _fmt(fact: str, v) -> str:
    if v is None:
        return "unknown"
    return f"${v:,.2f}" if fact == "unit_price" else f"{v}"


def decide(report: dict, policy: HandbookPolicy) -> tuple[str, str, dict]:
    """Handbook section 4, applied by code. Returns (decision, one-sentence reason, checks)."""
    f = {k: report[k]["final_value"] for k in FACTS}
    ok = {k: report[k]["status"] in GOOD for k in FACTS}
    vendor_key = (f["vendor"] or "").casefold()
    max_cost = policy.max_unit_cost.get(f["sku"]) if ok["sku"] else None
    checks = {
        "approved_vendor": ok["vendor"] and vendor_key in policy.approved and vendor_key not in policy.removed_or_pending,
        "price": ok["unit_price"] and max_cost is not None and f["unit_price"] <= max_cost,
        "lead_time": ok["lead_time_days"] and f["lead_time_days"] <= policy.max_lead_time_days,
        "min_order": ok["min_order"] and f["min_order"] <= policy.max_min_order,
    }
    # 1. Definitive failures from verified facts.
    if ok["vendor"] and vendor_key in policy.removed_or_pending:
        return "do_not_recommend", f"Approved-vendor check fails: {f['vendor']} is on the handbook's removed or pending vendor list.", checks
    if ok["vendor"] and vendor_key not in policy.approved:
        return "do_not_recommend", f"Approved-vendor check fails: {f['vendor']} is not on the handbook's approved vendor list.", checks
    if ok["unit_price"] and ok["sku"] and max_cost is not None and f["unit_price"] > max_cost:
        return "do_not_recommend", f"Price check fails: the quoted unit price of {_fmt('unit_price', f['unit_price'])} exceeds the {_fmt('unit_price', max_cost)} maximum for {f['sku']}.", checks
    if ok["lead_time_days"] and f["lead_time_days"] > policy.max_lead_time_days:
        return "do_not_recommend", f"Lead-time check fails: the {f['lead_time_days']}-day lead time exceeds the {policy.max_lead_time_days}-day maximum.", checks
    if ok["min_order"] and f["min_order"] > policy.max_min_order:
        return "do_not_recommend", f"Minimum-order check fails: the {f['min_order']}-unit minimum exceeds the {policy.max_min_order}-unit maximum.", checks
    # 2. Unresolved conflicts: purchasing-safety hold for human review.
    for k in FACTS:
        if report[k]["status"] in ("conflict", "contradicts_document"):
            vals = report[k].get("document_values", {}).get("values") or []
            if k == "vendor":
                detail = "; ".join(report[k]["issues"])
                return "do_not_recommend", f"Vendor identity could not be confirmed ({detail}), so the approved-vendor check needs buyer review before purchase.", checks
            shown = " and ".join(_fmt(k, v) for v in vals) if len(vals) > 1 else _fmt(k, report[k]["final_value"])
            return "do_not_recommend", f"The document states conflicting {LABEL[k]} values ({shown}) with no clearly authoritative revision, so the {LABEL[k]} check needs buyer review before purchase.", checks
    # 3. Facts that could not be verified or are missing.
    for k in FACTS:
        if not ok[k]:
            what = "is not stated" if report[k]["status"] == "not_stated" else "could not be verified in the visible document"
            return "do_not_recommend", f"The {LABEL[k]} {what}, so the purchasing checks cannot all be confirmed.", checks
    if max_cost is None:
        return "do_not_recommend", f"Price check cannot be confirmed: {f['sku']} is not in the handbook catalogue.", checks
    return "recommend", (f"All four purchasing checks pass: {f['vendor']} is approved, {_fmt('unit_price', f['unit_price'])} is within the "
                         f"{_fmt('unit_price', max_cost)} maximum, the {f['lead_time_days']}-day lead time is within {policy.max_lead_time_days} days, "
                         f"and the {f['min_order']}-unit minimum is within {policy.max_min_order}."), checks


def finalize(extraction: FactExtraction, visible: VisibleDocument, policy: HandbookPolicy) -> tuple[VendorRecommendation, dict]:
    """Design layer: validate the model's proposed facts, then let the policy engine decide."""
    if not visible.render_ok:
        rec = VendorRecommendation(vendor=None, sku=None, unit_price=None, lead_time_days=None, min_order=None,
                                   decision="do_not_recommend",
                                   reason="The document could not be safely rendered for verification, so it needs buyer review before purchase.")
        return rec, {"validation": None, "policy_checks": None, "review_required": True}
    report = validate(extraction, visible, policy)
    decision, reason, checks = decide(report, policy)
    final = {k: report[k]["final_value"] for k in FACTS}
    if isinstance(final["unit_price"], int):
        final["unit_price"] = float(final["unit_price"])
    # Keep the required output schema valid without inventing values: malformed facts become null
    # (and their checks have already failed above).
    if not (final["vendor"] or "").strip():
        final["vendor"] = None
    if final["sku"] is not None and not _SKU.fullmatch(final["sku"]):
        final["sku"] = None
    for k in ("unit_price", "lead_time_days", "min_order"):
        if final[k] is not None and final[k] <= 0:
            final[k] = None
    if len(reason) > 400:
        reason = reason[:396].rsplit(" ", 1)[0] + " ..."
    rec = VendorRecommendation(**final, decision=decision, reason=reason)
    review = any(report[k]["status"] not in GOOD for k in FACTS) or bool(visible.flags and "hidden_content_is_material" in visible.flags)
    return rec, {"validation": report, "policy_checks": checks, "review_required": review}
