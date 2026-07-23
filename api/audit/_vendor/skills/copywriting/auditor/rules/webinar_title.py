"""webinar_title.py — TL rules for webinar/workshop titles + title-output structure.

Source-of-truth: references/craft/headline-and-subject-rules.md (the TL-1..TL-9 set,
Lauren 2026-07-13: "titles are headlines, they follow headline best practice").

The title deliverable is NOT an email bundle, so these rules parse the title
output out of raw_text themselves. Mechanical rules are regex/parse; TL-2/TL-8/TL-9
are Claude-judge (skipped when ctx.skip_semantic is set); TL-7 is a lexical proxy
against the client's declared avatar_snapshot.primary_desire.

  S-1 · exactly 8 alternates            (HARD)
  S-2 · exactly 3 subtitle options      (HARD)
  S-3 · required sections present       (HARD)
  TE-1 · no em dashes in any title line (HARD)   ← headlines never take em dashes
  TL-3 · no ALL CAPS, no "!"            (HARD)
  TL-1 · specificity (number/audience/timeframe) (YELLOW)
  TL-4 · 6-14 words per title           (YELLOW)
  TL-5 · no filler (masterclass/secrets/ultimate/deep dive/101) (YELLOW)
  TL-7 · names THEIR declared desire    (HARD when primary_desire declared)
  TL-2 · outcome verb + tangible result (YELLOW · judge)
  TL-8 · title + mechanism obvious      (YELLOW · judge)
  TL-9 · audience AND tangible result carried by the headline alone (YELLOW · judge)
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from skills.copywriting.auditor.lib.parser import ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation
from skills.copywriting.auditor.rules.semantic import _call_claude_judge


LAYER = "Title"
APPLIES_TO = {"webinar_title"}

EM_DASH_RE = re.compile(r"[—–]")
ALL_CAPS_RE = re.compile(r"\b[A-Z]{4,}\b")
FILLER_RE = re.compile(
    r"\b(masterclass|secrets?|the ultimate guide|ultimate|deep dive|101|webinar training)\b",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"\d")
TIMEFRAME_RE = re.compile(r"\b(day|days|week|weeks|hour|hours|minute|minutes|min|month|months|year|years|\d+\s*(?:min|hrs?))\b", re.IGNORECASE)
AUDIENCE_RE = re.compile(r"\b(for|who|if you'?re|women|men|founders?|coaches?|professionals?|owners?)\b", re.IGNORECASE)
MARKER_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+")
STOPWORDS = {
    "the", "and", "for", "you", "your", "with", "that", "this", "from", "have",
    "what", "when", "will", "still", "after", "before", "not", "any", "all",
    "how", "why", "who", "into", "more", "less", "than", "over", "about",
}


# ── parsing ──────────────────────────────────────────────────────────────────

def _strip(line: str) -> str:
    return MARKER_RE.sub("", line.strip()).strip()

def _strip_angle(text: str) -> str:
    """Drop a trailing parenthetical angle note: 'Title (Mechanism-forward)' -> 'Title'."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()

def _is_heading(line: str, *keys: str) -> bool:
    low = line.lower()
    return any(k in low for k in keys)


def _parse_title_output(bundle: ParsedBundle):
    """Return (recommended_title, recommended_subtitle, alternates[], subtitles[], sections_found{})."""
    lines = bundle.raw_lines
    rec_title: Optional[str] = None
    rec_sub: Optional[str] = None
    alternates: List[Tuple[int, str]] = []
    subtitles: List[Tuple[int, str]] = []
    found = {"recommended": False, "alternates": False, "subtitles": False}

    section = None
    for i, raw in enumerate(lines, start=1):
        s = raw.strip()
        if not s:
            continue
        if _is_heading(s, "recommended title"):
            section, found["recommended"] = "rec", True
            continue
        if _is_heading(s, "alternate"):
            section, found["alternates"] = "alt", True
            continue
        if _is_heading(s, "subtitle option"):
            section, found["subtitles"] = "sub", True
            continue

        clean = _strip(s)
        if section == "rec":
            sub_only = re.match(r"sub(?:title)?\s*:\s*(.+)$", clean, flags=re.IGNORECASE)
            if rec_title is None:
                # First substantive line is the title; it may carry an inline "Sub:".
                m = re.split(r"\s*\bsub(?:title)?\s*:\s*", clean, maxsplit=1, flags=re.IGNORECASE)
                rec_title = m[0].strip()
                if len(m) > 1:
                    rec_sub = m[1].strip()
            elif sub_only and rec_sub is None:
                # Subtitle on its own line ("Subtitle: ...").
                rec_sub = sub_only.group(1).strip()
            # else: the "why this pick" paragraph — ignore.
        elif section == "alt":
            # Skip an angle-note annotation on its own line, e.g. "*(Mechanism-forward...)*".
            if re.match(r"^[*_]*\(", clean):
                continue
            alternates.append((i, clean))
        elif section == "sub":
            # Subtitle sections shouldn't carry parenthetical annotations, but guard anyway.
            if re.match(r"^[*_]*\(", clean):
                continue
            subtitles.append((i, clean))
    return rec_title, rec_sub, alternates, subtitles, found


def _title_lines(bundle: ParsedBundle) -> List[Tuple[int, str]]:
    """Every headline-bearing line: recommended title + subtitle + alternates + subtitle options.
    Used by rules that apply to ALL title text (em dashes, ALL CAPS)."""
    rec_t, rec_s, alts, subs, _ = _parse_title_output(bundle)
    out: List[Tuple[int, str]] = []
    if rec_t:
        out.append((1, rec_t))
    if rec_s:
        out.append((1, rec_s))
    out.extend((n, _strip_angle(t)) for n, t in alts)
    out.extend(subs)
    return out


def _headline_units(bundle: ParsedBundle) -> List[Tuple[int, str]]:
    """Title units only: recommended title + the 8 alternates. Excludes subtitles,
    which legitimately carry more detail — used by length/filler/specificity rules."""
    rec_t, _, alts, _, _ = _parse_title_output(bundle)
    out: List[Tuple[int, str]] = []
    if rec_t:
        out.append((1, rec_t))
    out.extend((n, _strip_angle(t)) for n, t in alts)
    return out


def _words(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9']+", text)


# ── structural rules ─────────────────────────────────────────────────────────

def check_s1_eight_alternates(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    _, _, alts, _, found = _parse_title_output(bundle)
    if found["alternates"] and len(alts) != 8:
        return [Violation(
            rule_id="S-1", rule_name="exactly 8 alternates", severity=HARD,
            section_id="Alternates", line_no=1, line_content=f"{len(alts)} found",
            message=f"Alternates section has {len(alts)} titles; the spec requires exactly 8.",
            fix_hint="Provide exactly 8 alternates, spread across the named angles.",
        )]
    return []


def check_s2_three_subtitles(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    _, _, _, subs, found = _parse_title_output(bundle)
    if found["subtitles"] and len(subs) != 3:
        return [Violation(
            rule_id="S-2", rule_name="exactly 3 subtitle options", severity=HARD,
            section_id="Subtitle options", line_no=1, line_content=f"{len(subs)} found",
            message=f"Subtitle options has {len(subs)} lines; the spec requires exactly 3.",
            fix_hint="Provide exactly 3 subtitle options.",
        )]
    return []


def check_s3_sections_present(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    _, _, _, _, found = _parse_title_output(bundle)
    missing = [k for k, v in {
        "Recommended title": found["recommended"],
        "Alternates (8)": found["alternates"],
        "Subtitle options (3)": found["subtitles"],
    }.items() if not v]
    if missing:
        return [Violation(
            rule_id="S-3", rule_name="required sections present", severity=HARD,
            section_id="structure", line_no=1, line_content=", ".join(missing),
            message=f"Missing required section(s): {', '.join(missing)}.",
            fix_hint="Output all three sections: Recommended title, Alternates (8), Subtitle options (3).",
        )]
    return []


# ── mechanical TL rules ──────────────────────────────────────────────────────

def check_te1_no_em_dash(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for line_no, text in _title_lines(bundle):
        if EM_DASH_RE.search(text):
            violations.append(Violation(
                rule_id="TE-1", rule_name="no em dashes in titles", severity=HARD,
                section_id="title", line_no=line_no, line_content=text,
                message="Em dash in a title/subtitle. Headlines never take em dashes.",
                fix_hint="Rewrite as two lines, or use a comma/colon. Move any parenthetical angle note to its own annotation.",
            ))
    return violations


def check_tl3_no_caps_or_bang(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for line_no, text in _title_lines(bundle):
        # [PLACEHOLDER: ...] / [ASSUMPTION] tokens are an intentional convention — exempt.
        probe = re.sub(r"\[[^\]]*\]", "", text)
        if "!" in probe or ALL_CAPS_RE.search(probe):
            violations.append(Violation(
                rule_id="TL-3", rule_name="no ALL CAPS, no exclamation", severity=HARD,
                section_id="title", line_no=line_no, line_content=text,
                message="Title uses ALL-CAPS words and/or an exclamation mark.",
                fix_hint="Use sentence/title case and no exclamation marks.",
            ))
    return violations


def check_tl5_no_filler(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for line_no, text in _headline_units(bundle):
        m = FILLER_RE.search(text)
        if m:
            violations.append(Violation(
                rule_id="TL-5", rule_name="no vague filler", severity=YELLOW,
                section_id="title", line_no=line_no, line_content=text,
                message=f'Vague filler word: "{m.group(0)}".',
                fix_hint="Replace with the specific promise or mechanism.",
            ))
    return violations


def check_tl4_word_count(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for line_no, text in _headline_units(bundle):
        n = len(_words(text))
        if n and not (6 <= n <= 14):
            violations.append(Violation(
                rule_id="TL-4", rule_name="6-14 words", severity=YELLOW,
                section_id="title", line_no=line_no, line_content=text,
                message=f"Title is {n} words (guidance: 6-14).",
                fix_hint="Compress to a headline-length line; push detail into the subtitle.",
            ))
    return violations


def check_tl1_specificity(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    rec_t, _, _, _, _ = _parse_title_output(bundle)
    if not rec_t:
        return []
    if NUMBER_RE.search(rec_t) or TIMEFRAME_RE.search(rec_t) or AUDIENCE_RE.search(rec_t):
        return []
    return [Violation(
        rule_id="TL-1", rule_name="specificity: number / audience / timeframe", severity=YELLOW,
        section_id="Recommended title", line_no=1, line_content=rec_t,
        message="Recommended title names no number, audience, or timeframe.",
        fix_hint="Anchor it with a concrete number, a named audience, or a timeframe.",
    )]


# ── lexical desire proxy (TL-7) ──────────────────────────────────────────────

def _primary_desire(ctx: dict) -> Optional[str]:
    client = ctx.get("client_data")
    info = getattr(client, "info", None) or {}
    snap = info.get("avatar_snapshot") if isinstance(info, dict) else None
    if isinstance(snap, dict):
        d = snap.get("primary_desire")
        if isinstance(d, str) and d.strip():
            return d
    return None


def check_tl7_their_desire(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    desire = _primary_desire(ctx)
    rec_t, rec_s, _, _, _ = _parse_title_output(bundle)
    if not desire or not rec_t:
        return []  # no declared desire → unchecked, not a violation
    title_words = {w.lower() for w in _words(f"{rec_t} {rec_s or ''}") if len(w) > 3 and w.lower() not in STOPWORDS}
    desire_words = {w.lower() for w in _words(desire) if len(w) > 3 and w.lower() not in STOPWORDS}
    if title_words & desire_words:
        return []
    return [Violation(
        rule_id="TL-7", rule_name="names their declared desire", severity=HARD,
        section_id="Recommended title", line_no=1, line_content=rec_t,
        message="Title shares no vocabulary with the client's declared primary_desire — it may name a desire the avatar doesn't have.",
        fix_hint=f'Anchor the title to their actual desire: "{desire[:120]}".',
    )]


# ── Claude-judge rules (TL-2 / TL-8 / TL-9) ──────────────────────────────────

_JUDGE_SYS = """You audit a webinar/workshop TITLE against one direct-response headline rule.
You are given the recommended title, its subtitle (if any), and client context.
Return STRICTLY this JSON, no prose, no fences:
{"verdict": "PASS" | "FAIL", "reasoning": "1-2 sentences"}"""

def _judge(ctx: dict, rule_id: str, rule_name: str, question: str, bundle: ParsedBundle) -> List[Violation]:
    if ctx.get("skip_semantic"):
        return []
    rec_t, rec_s, _, _, _ = _parse_title_output(bundle)
    if not rec_t:
        return []
    client = ctx.get("client_data")
    info = getattr(client, "info", None) or {}
    mech = getattr(client, "mechanism_source_of_truth", None) or ""
    desire = _primary_desire(ctx) or ""
    user = (
        f"RULE: {question}\n\n"
        f"TITLE: {rec_t}\nSUBTITLE: {rec_s or '(none)'}\n"
        f"CLIENT MECHANISM: {mech or '(unknown)'}\nAVATAR PRIMARY DESIRE: {desire or '(unknown)'}"
    )
    result = _call_claude_judge(_JUDGE_SYS, user, max_tokens=300)
    if result.get("error") or result.get("verdict") != "FAIL":
        return []  # unreachable judge or PASS → no violation (fail open)
    return [Violation(
        rule_id=rule_id, rule_name=rule_name, severity=YELLOW,
        section_id="Recommended title", line_no=1, line_content=rec_t,
        message=f"Claude judge: {result.get('reasoning', 'fails ' + rule_id)}",
        fix_hint="Revise the headline so it satisfies this rule on its own.",
    )]


def check_tl2_tangible_result(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    return _judge(ctx, "TL-2", "outcome verb + tangible result", bundle=bundle,
                  question="Does the title carry an outcome verb PLUS a tangible result (a number, a named end-state, or a concrete deliverable the avatar can picture)? A verb with a vague object (e.g. 'optimize your metabolism') is a topic label and FAILS.")


def check_tl8_mechanism_obvious(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    return _judge(ctx, "TL-8", "title + mechanism obvious to the audience", bundle=bundle,
                  question="Reading the title alone from this audience's chair, are BOTH what it's for AND the method/mechanism name obvious (no insider jargon)? If either is opaque, FAIL.")


def check_tl9_audience_and_result(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    return _judge(ctx, "TL-9", "audience AND tangible result on its own", bundle=bundle,
                  question="Does the HEADLINE alone carry BOTH the audience AND the tangible desired result? If either is missing or offloaded to the subtitle, FAIL.")


RULES = [
    Rule(id="S-1", name="exactly 8 alternates", severity=HARD, layer=LAYER, check=check_s1_eight_alternates, applies_to=APPLIES_TO),
    Rule(id="S-2", name="exactly 3 subtitle options", severity=HARD, layer=LAYER, check=check_s2_three_subtitles, applies_to=APPLIES_TO),
    Rule(id="S-3", name="required sections present", severity=HARD, layer=LAYER, check=check_s3_sections_present, applies_to=APPLIES_TO),
    Rule(id="TE-1", name="no em dashes in titles", severity=HARD, layer=LAYER, check=check_te1_no_em_dash, applies_to=APPLIES_TO),
    Rule(id="TL-3", name="no ALL CAPS, no exclamation", severity=HARD, layer=LAYER, check=check_tl3_no_caps_or_bang, applies_to=APPLIES_TO),
    Rule(id="TL-1", name="specificity", severity=YELLOW, layer=LAYER, check=check_tl1_specificity, applies_to=APPLIES_TO),
    Rule(id="TL-4", name="6-14 words", severity=YELLOW, layer=LAYER, check=check_tl4_word_count, applies_to=APPLIES_TO),
    Rule(id="TL-5", name="no vague filler", severity=YELLOW, layer=LAYER, check=check_tl5_no_filler, applies_to=APPLIES_TO),
    Rule(id="TL-7", name="names their declared desire", severity=HARD, layer=LAYER, check=check_tl7_their_desire, applies_to=APPLIES_TO),
    Rule(id="TL-2", name="outcome verb + tangible result", severity=YELLOW, layer="Semantic", check=check_tl2_tangible_result, applies_to=APPLIES_TO),
    Rule(id="TL-8", name="title + mechanism obvious", severity=YELLOW, layer="Semantic", check=check_tl8_mechanism_obvious, applies_to=APPLIES_TO),
    Rule(id="TL-9", name="audience AND tangible result", severity=YELLOW, layer="Semantic", check=check_tl9_audience_and_result, applies_to=APPLIES_TO),
]
