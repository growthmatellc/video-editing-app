"""sales_page.py — SP-1 to SP-8 · long-form sales page + VSL structure.

Sources (citation on each check):
  skills/funnel-copy/sales-page/workflow.md + meta.json   9 locked sections, word bands,
                                                          proof stack, FAQ bounds
  skills/scripting/vsl-standalone/meta.json               11 locked timecoded sections
  references/craft/funnel-and-email-rules-lauren.md       rule L.2 (one CTA), rule J.4 (mobile-first)

Not encoded here, deliberately: "hero headline self-explanatory on first read", "reader-first
framing", "genuine vs manufactured urgency". Those need judgment, and a regex pretending to
grade them would be worse than no check. They stay in the workflow checklist and the semantic
layer.
"""

from __future__ import annotations

import re
from typing import List, Optional

from skills.copywriting.auditor.lib.parser import ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation
from skills.copywriting.auditor.lib import sections as S


LAYER = "SalesPage"
APPLIES_TO = {"sales_page", "vsl"}


# sales-page/workflow.md · the 9 locked sections. "Cannot be skipped. Cannot be reordered."
SALES_PAGE_SECTIONS = [
    ("hero",                  r"\bhero\b|headline"),
    ("problem amplification", r"problem|pain"),
    ("mechanism reveal",      r"mechanism"),
    ("proof stack",           r"proof|case\s+stud|testimonial|results"),
    ("offer breakdown",       r"offer|what.?s\s+included|deliverable"),
    ("guarantee",             r"guarantee|risk[-\s]revers"),
    ("urgency",               r"urgency|scarcity|deadline"),
    ("faq",                   r"faq|q\s*&\s*a|frequently\s+asked|objection"),
    ("final cta",             r"final\s+cta|last\s+cta|closing\s+cta"),
]

# vsl-standalone/meta.json · 11 locked timecoded sections.
VSL_SECTIONS = [
    ("hook",                  r"\bhook\b"),
    ("identity reframe",      r"identity|reframe"),
    ("problem amplification", r"problem|pain"),
    ("origin / credibility",  r"origin|credibility|story"),
    ("mechanism reveal",      r"mechanism"),
    ("proof stack",           r"proof|case\s+stud|testimonial"),
    ("offer breakdown",       r"offer|what.?s\s+included|deliverable"),
    ("guarantee",             r"guarantee|risk[-\s]revers"),
    ("urgency",               r"urgency|scarcity|deadline"),
    ("faq / objection",       r"faq|objection|q\s*&\s*a"),
    ("final cta",             r"final\s+cta|closing|last\s+cta"),
]

SALES_WORD_BAND = (1500, 4000)  # SP-7 enforces the FLOOR only; canon defends long copy, no upper cap


def _sections(bundle: ParsedBundle) -> List[S.Section]:
    return S.split_sections(bundle.raw_lines, lambda title: "section")


def _expected_for(ctx: dict):
    return VSL_SECTIONS if ctx.get("asset_type") == "vsl" else SALES_PAGE_SECTIONS


def _find_section(bundle: ParsedBundle, pattern: str) -> Optional[S.Section]:
    rx = re.compile(pattern, re.I)
    for s in _sections(bundle):
        if rx.search(s.heading):
            return s
    return None


def _v(rule_id, rule_name, severity, section_id, line_no, line, message, fix) -> Violation:
    return Violation(
        rule_id=rule_id, rule_name=rule_name, severity=severity,
        section_id=section_id, line_no=line_no, line_content=line, message=message, fix_hint=fix,
    )


# ---------------------------------------------------------------------------
# SP-0 · the document actually parses
#
# If no sections are recognised, every other SP rule passes on an empty list and the auditor
# prints "ship clear" for a file it never read. Zero sections is a HARD failure, never a
# silent pass.
# ---------------------------------------------------------------------------


def check_sp0_parseable(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if _sections(bundle):
        return []
    return [_v(
        "SP-0", "document parses", HARD, "document", 1, "(0 sections parsed)",
        "No sections could be parsed, so no sales-page rule was actually evaluated. The auditor will "
        "not pass a file it cannot read. Expected markdown headers, one per locked section.",
        "Add section headers, or extend the parser if this is a new format.",
    )]


# ---------------------------------------------------------------------------
# SP-1 · locked section order (9 for a sales page, 11 for a VSL)
# ---------------------------------------------------------------------------


def check_sp1_locked_sections(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    expected = _expected_for(ctx)
    label = "VSL" if ctx.get("asset_type") == "vsl" else "Sales page"
    headings = [(s.start_line, s.heading) for s in _sections(bundle)]
    blob = " || ".join(h for _, h in headings)

    violations = []
    for name, pattern in expected:
        if not re.search(pattern, blob, re.I):
            violations.append(_v(
                "SP-1", "locked section order", HARD, "structure", 1, f"({len(headings)} sections found)",
                f"{label} is missing the `{name}` section. All {len(expected)} sections are locked — "
                f"none can be skipped, none can be reordered.",
                f"Add the `{name}` section in its locked position.",
            ))

    positions = []
    for i, (name, pattern) in enumerate(expected):
        for line_no, heading in headings:
            if re.search(pattern, heading, re.I):
                positions.append((i, name, line_no))
                break
    for j in range(1, len(positions)):
        rank, name, line_no = positions[j]
        prev_rank, prev_name, _ = positions[j - 1]
        if rank < prev_rank:
            violations.append(_v(
                "SP-1", "locked section order", HARD, "structure", line_no, name,
                f"`{name}` appears after `{prev_name}`, but the locked order puts it before. "
                f"Sections cannot be reordered.",
                "Reorder to the locked sequence.",
            ))
    return violations


# ---------------------------------------------------------------------------
# SP-2 · one CTA only — identical button text at every placement (rule L.2)
#   "must be identical" · no competing or alternative path
# ---------------------------------------------------------------------------

CTA_LINE_RE = re.compile(r"^\s*\**\s*(?:CTA|Button|Button text)\s*\**\s*:\s*(?P<text>.+?)\s*$", re.I)


def check_sp2_one_cta(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    ctas = []
    for idx, line in enumerate(bundle.raw_lines):
        m = CTA_LINE_RE.match(line)
        if m:
            text = S.strip_markdown(m.group("text")).strip().strip('"“”').rstrip(".")
            if text:
                ctas.append((idx + 1, text))
    if len(ctas) < 2:
        return []

    first_line, first_text = ctas[0]
    violations = []
    for line_no, text in ctas[1:]:
        if text.lower() != first_text.lower():
            violations.append(_v(
                "SP-2", "one CTA · identical everywhere", HARD, "CTA", line_no, text,
                f"CTA reads `{text}`, but the first CTA on the page reads `{first_text}`. Every CTA "
                f"placement carries the identical button text and URL — one ask, one path. Competing "
                f"or alternative CTAs are forbidden.",
                f"Change this CTA to `{first_text}`, or fix the first one if this is the correct ask.",
            ))
    return violations


# ---------------------------------------------------------------------------
# SP-3 · FAQ — 6 to 12 questions, zero sales language
# ---------------------------------------------------------------------------

FAQ_FORBIDDEN_RE = re.compile(r"\b(price|cost|investment|buy|purchase|package)\b", re.I)


def check_sp3_faq(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    section = _find_section(bundle, r"faq|q\s*&\s*a|frequently\s+asked|objection")
    if not section:
        return []  # SP-1 owns the missing-section case
    count = sum(c.count("?") for _, c in section.lines)
    if 6 <= count <= 12:
        return []
    return [_v(
        "SP-3", "FAQ · handle the live objections (count advisory)", YELLOW, section.section_id,
        section.start_line, f"({count} questions)",
        f"FAQ carries {count} questions, outside the 6-12 convention. DR handles the real objections, "
        f"which is offer-specific, not a fixed count (the FAQ section's presence is already gated HARD "
        f"by SP-1). Treat this as a nudge to check objection coverage, not a block.",
        "Cover every live objection the buyer has; 6-12 is the usual span. "
        "See references/craft/long-form-structure-rules.md.",
    )]


# ---------------------------------------------------------------------------
# SP-4 · Problem Amplification — 3 to 5 pain points ("no more, no less")
# ---------------------------------------------------------------------------


def check_sp4_problem_amplification(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    section = _find_section(bundle, r"problem|pain")
    if not section:
        return []
    count = S.count_bullets(section.lines)
    if 3 <= count <= 5:
        return []
    return [_v(
        "SP-4", "problem amp · agitate the dominant desire (count advisory)", YELLOW,
        section.section_id, section.start_line, f"({count} pain points)",
        f"Problem Amplification has {count} pain points, outside the 3-5 convention. PAS is a structure, "
        f"not a quota — Schwartz says agitate the ONE dominant desire deeply. A flag to check the "
        f"agitation lands, not a block.",
        "Go deep on the dominant pain rather than counting points. "
        "See references/craft/long-form-structure-rules.md.",
    )]


# ---------------------------------------------------------------------------
# SP-5 · Proof Stack — 5 to 7 case studies
# ---------------------------------------------------------------------------


def check_sp5_proof_stack(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    section = _find_section(bundle, r"proof|case\s+stud|testimonial")
    if not section:
        return []
    quotes = len(re.findall(r"[\"“][^\"”]{15,}[\"”]", section.body))
    if quotes >= 5:
        return []
    return [_v(
        "SP-5", "proof stack · at least ~5 cases (floor, advisory)", YELLOW, section.section_id,
        section.start_line, f"({quotes} quoted case studies)",
        f"Proof Stack carries {quotes} case studies with a verbatim quote. Social proof scales UP "
        f"(Cialdini) — there is no upper bound, so this is a floor, not a band: aim for at least ~5, "
        f"each with photo + video + verbatim quote + result, star case first. A newer client with "
        f"fewer is a nudge, not a block.",
        "Add case studies (verbatim, not paraphrased); more relevant proof helps. "
        "See references/craft/long-form-structure-rules.md.",
    )]


# ---------------------------------------------------------------------------
# SP-6 · mobile-first — no paragraph longer than 3 lines (rule J.4)
# ---------------------------------------------------------------------------


def check_sp6_mobile_first(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    run = 0
    run_start = 0
    for idx, line in enumerate(bundle.raw_lines + [""]):
        is_prose = bool(line.strip()) and not S.HEADER_RE.match(line) and not S.is_bullet(line)
        if is_prose:
            if run == 0:
                run_start = idx + 1
            run += 1
            continue
        if run > 3:
            violations.append(_v(
                "SP-6", "mobile-first · no wall of text", HARD, "body", run_start,
                bundle.raw_lines[run_start - 1].strip()[:80],
                f"Paragraph runs {run} lines with no break. Mobile-first formatting caps a paragraph "
                f"at 3 lines — one new idea, one line break.",
                "Break the paragraph. One idea per block.",
            ))
        run = 0
    return violations


# ---------------------------------------------------------------------------
# SP-7 · word count band (YELLOW — the source calls it guidance, not a cap)
# ---------------------------------------------------------------------------


def check_sp7_word_count(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    words = len(S.strip_markdown(bundle.raw_text).split())
    low, _high = SALES_WORD_BAND
    if words >= low:
        return []
    return [_v(
        "SP-7", "word count · soft floor", YELLOW, "document", 1, f"({words} words)",
        f"Sales page is {words} words, under the ~{low}-word floor. A considered high-ticket purchase "
        f"needs enough copy to build the case, and canon defends long copy (Ogilvy, Schwartz) — so "
        f"there is no upper cap, only a floor, flagged as a nudge.",
        f"If the offer is high-ticket, make sure the argument is fully built (~{low}+ words). "
        f"See references/craft/long-form-structure-rules.md.",
    )]


# ---------------------------------------------------------------------------
# SP-8 · shared craft rules · no em dash, no asterisk bullets, US English
# ---------------------------------------------------------------------------


def check_sp8_craft(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for idx, line in enumerate(bundle.raw_lines):
        line_no = idx + 1
        if S.EM_DASH_RE.search(line):
            violations.append(_v(
                "SP-8", "craft · dashes, bullets, US EN", HARD, "body", line_no, line.strip(),
                "Em dash. Growth Mate copy uses a comma, a period, or a rewrite.",
                "Replace the em dash.",
            ))
        if S.ASTERISK_BULLET_RE.match(line):
            violations.append(_v(
                "SP-8", "craft · dashes, bullets, US EN", HARD, "body", line_no, line.strip(),
                "Asterisk bullet. Bullets are `•` or `-`.",
                "Swap the `*` for a `•` or `-`.",
            ))
        for m in S.BRITISH_RE.finditer(line):
            word = m.group(0)
            violations.append(_v(
                "SP-8", "craft · dashes, bullets, US EN", HARD, "body", line_no, line.strip(),
                f"British spelling `{word}`. Copy ships in US English.",
                f"Use `{S.BRITISH_SPELLINGS.get(word.lower(), 'the US spelling')}`.",
            ))
    return violations


RULES = [
    Rule(id="SP-0", name="document parses",                severity=HARD,   layer=LAYER, check=check_sp0_parseable,             applies_to=APPLIES_TO),
    Rule(id="SP-1", name="locked section order",           severity=HARD,   layer=LAYER, check=check_sp1_locked_sections,       applies_to=APPLIES_TO),
    Rule(id="SP-2", name="one CTA · identical everywhere", severity=HARD,   layer=LAYER, check=check_sp2_one_cta,               applies_to=APPLIES_TO),
    Rule(id="SP-3", name="FAQ · objection coverage",       severity=YELLOW, layer=LAYER, check=check_sp3_faq,                   applies_to={"sales_page"}),
    Rule(id="SP-4", name="problem amp · dominant desire",  severity=YELLOW, layer=LAYER, check=check_sp4_problem_amplification, applies_to=APPLIES_TO),
    Rule(id="SP-5", name="proof stack · ≥5 floor",         severity=YELLOW, layer=LAYER, check=check_sp5_proof_stack,           applies_to=APPLIES_TO),
    Rule(id="SP-6", name="mobile-first · no wall of text", severity=HARD,   layer=LAYER, check=check_sp6_mobile_first,          applies_to={"sales_page"}),
    Rule(id="SP-7", name="word count band",                severity=YELLOW, layer=LAYER, check=check_sp7_word_count,            applies_to={"sales_page"}),
    Rule(id="SP-8", name="craft · dashes, bullets, US EN", severity=HARD,   layer=LAYER, check=check_sp8_craft,                 applies_to=APPLIES_TO),
]
