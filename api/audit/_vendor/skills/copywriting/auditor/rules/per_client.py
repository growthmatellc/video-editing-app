"""per_client.py — per-client voice rules, retired terminology, locked AHAs.

Loads from clients/<slug>/info.json, style-guide.md, term-mappings.json (via lib/per_client.py,
which delegates parsing to lib/voice.py and lib/term_mappings.py).

Rules:
  PC-0 · the client's voice rules parse at all (HARD · the parse guard)
  PC-1 · banned literal phrases not present in output (HARD)
  PC-2 · retired terminology not present in output (HARD when settled, YELLOW when not)

Rewritten 2026-07-16. What was here before:

  - **PC-1 was dead on every client.** It read `## Banned phrases`, a heading no style guide
    uses (all 22 write `## Off-brand phrases`), so it loaded an empty list and passed.
  - **PC-2 was hardcoded to one client** — `DEPRECATED_MECHANISMS = {"trent-harrison": [...]}`
    — and returned clean for the other 21, while every one of them had retired terminology
    sitting in term-mappings.json in machine-readable form.
  - **PC-3 (locked AHA) was documented in the docstring and never registered.** It is still
    not implemented; it is no longer claimed either. See skills/tone-of-voice/SKILL.md.

Both live rules were HARD, which is what made this expensive: an auditor run reported two
green per-client gates, and the greenness was manufactured. Per README § "The `-0` parse
guard": a gate that blesses what it cannot parse is worse than no gate. PC-0 now exists so
this failure can never again be silent.
"""

from __future__ import annotations

from typing import List

from skills.copywriting.auditor.lib.parser import ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation
from skills.copywriting.auditor.lib.voice import matches_literal


LAYER = "Per-Client"
APPLIES_TO = {"*"}


def check_pc0_voice_rules_parse(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """The client's style guide exists but no voice section could be read.

    This is the `-0` guard for the per-client layer. Without it, a style guide that drifts
    off-schema silently disarms PC-1: no phrases load, nothing fires, the run reads clean.
    That is exactly what happened for six weeks, and nothing surfaced it.

    Fires only when there IS a guide to read. A client with no folder or no style-guide.md
    is a different situation (nothing to enforce), not a broken one.
    """
    client_data = ctx.get("client_data")
    if not client_data or not client_data.available:
        return []
    voice = client_data.voice
    if not voice or not voice.style_guide_present:
        return []
    if voice.parseable:
        return []
    return [Violation(
        rule_id="PC-0",
        rule_name=f"voice rules parse ({client_data.slug})",
        severity=HARD,
        section_id="(document)",
        line_no=0,
        line_content=f"clients/{client_data.slug}/style-guide.md",
        message=(
            f"`{client_data.slug}/style-guide.md` exists but no voice section could be parsed "
            f"(looked for: Off-brand phrases, Don'ts, On-brand phrases). Every per-client "
            f"voice check is silently disabled for this run."
        ),
        fix_hint=(
            "The guide has drifted off the schema in skills/onboard/references/output-schemas.md "
            "§ style-guide.md. Restore the `## Off-brand phrases` / `## Don'ts` headings, or add "
            "the guide's heading to OFF_BRAND_HEADINGS in auditor/lib/voice.py."
        ),
    )]


def check_pc1_banned_phrases(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Literal phrases the client's style guide enumerates as off-brand.

    Only literals reach this rule. Prose categories ("Passive voice") go to SEM-VR, and
    retracted rules go nowhere — see lib/voice.py.
    """
    violations = []
    client_data = ctx.get("client_data")
    if not client_data or not client_data.banned_phrases:
        return violations
    for section in bundle.all_communication_sections:
        for line_no, content in section.body_lines:
            for phrase in client_data.banned_phrases:
                if not matches_literal(phrase, content):
                    continue
                violations.append(Violation(
                    rule_id="PC-1",
                    rule_name=f"per-client banned phrase ({client_data.slug})",
                    severity=HARD,
                    section_id=section.section_id,
                    line_no=line_no,
                    line_content=content.strip(),
                    message=f"Off-brand phrase `{phrase}` detected (per {client_data.slug}/style-guide.md).",
                    fix_hint=(
                        f"Remove or rephrase. See `clients/{client_data.slug}/style-guide.md` "
                        f"§ Off-brand phrases, and § On-brand phrases for what to reach for instead."
                    ),
                ))
    return violations


def check_pc2_retired_terminology(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Terminology the client has retired, read from term-mappings.json.

    Severity follows what the client's own file claims:
      - a settled retirement (`retired_term`, `do_not_resurrect`, status resolved) → HARD
      - a preference (`avoid_terms`) or an unratified call (`pending_lauren_confirm`,
        `status: ORANGE`) → YELLOW

    Blocking a draft on a rule nobody has agreed to is how a gate gets routed around.
    """
    violations = []
    client_data = ctx.get("client_data")
    if not client_data or not client_data.retired_terms:
        return violations

    # Longest first: "5M Method" is a substring of "Ransomed 5M Method", and both are
    # retired. Reporting one line twice for the same offence is noise, not rigour.
    terms = sorted(client_data.retired_terms, key=lambda r: len(r.retired), reverse=True)

    for section in bundle.all_communication_sections:
        for line_no, content in section.body_lines:
            claimed = []
            for rt in terms:
                if not matches_literal(rt.retired, content):
                    continue
                if any(rt.retired.lower() in c for c in claimed):
                    continue
                claimed.append(rt.retired.lower())
                replacement = f"Use `{rt.replacement}`." if rt.replacement else "No replacement recorded."
                qualifier = "" if rt.hard else " (not ratified — confirm before changing)"
                violations.append(Violation(
                    rule_id="PC-2",
                    rule_name=f"retired terminology ({client_data.slug})",
                    severity=HARD if rt.hard else YELLOW,
                    section_id=section.section_id,
                    line_no=line_no,
                    line_content=content.strip(),
                    message=(
                        f"Retired term `{rt.retired}` detected{qualifier}. {replacement}"
                        + (f" Reason: {rt.reason[:160]}" if rt.reason else "")
                    ),
                    fix_hint=(
                        f"Replace with `{rt.replacement}`." if rt.replacement
                        else f"See `clients/{client_data.slug}/term-mappings.json`."
                    ),
                ))
    return violations


RULES = [
    Rule(id="PC-0", name="voice rules parse",         severity=HARD,   layer=LAYER, check=check_pc0_voice_rules_parse,     applies_to=APPLIES_TO),
    Rule(id="PC-1", name="per-client banned phrases", severity=HARD,   layer=LAYER, check=check_pc1_banned_phrases,        applies_to=APPLIES_TO),
    Rule(id="PC-2", name="retired terminology",       severity=HARD,   layer=LAYER, check=check_pc2_retired_terminology,   applies_to=APPLIES_TO),
]
