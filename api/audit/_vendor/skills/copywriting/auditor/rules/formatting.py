"""formatting.py — F-1 to F-12 output formatting standard.

Source-of-truth: skills/copywriting/references/craft/email-sms-output-formatting.md

Most formatting rules are about presentation · ensures every bundle looks like
the canonical Alec Project Transform X layout.

Rules implemented:
  F-1 · bolded email headers (**EMAIL #N: DESCRIPTION (TIMING)**)
  F-2 · bolded subject prefix (**Subject:** ...)
  F-5 · `---` divider between every email/SMS section
  F-6 · SMS callout prefix (**SMS #N (TIMING):**) + sign-off
  F-7 · sequence headers (# SEQUENCE N — TITLE (counts))
  F-8 · bundle title block
  F-9 · END OF BUNDLE metadata block
  F-10 · variable placeholders stay plain text (no escaping)
"""

from __future__ import annotations

import re
from typing import List

from skills.copywriting.auditor.lib.parser import ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation


LAYER = "Formatting"
APPLIES_TO = {"email_sequence", "email_launch"}


def check_f8_bundle_title_block(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """F-8: bundle MUST start with `**EMAIL + SMS LAUNCH BUNDLE — CLIENT NAME**` title block."""
    violations = []
    if not bundle.bundle_title:
        violations.append(Violation(
            rule_id="F-8",
            rule_name="bundle title block at top",
            severity=HARD,
            section_id="metadata",
            line_no=1,
            line_content=(bundle.raw_lines[0] if bundle.raw_lines else ""),
            message="Bundle is missing the canonical `**EMAIL + SMS LAUNCH BUNDLE — <CLIENT>**` title block.",
            fix_hint="Add the title block as the first line of the file (per F-8).",
        ))
    return violations


def check_f9_end_of_bundle_block(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """F-9: bundle MUST end with `**END OF BUNDLE...**` metadata block."""
    violations = []
    raw_text = bundle.raw_text or ""
    if not re.search(r"\*\*END OF BUNDLE", raw_text, re.IGNORECASE):
        violations.append(Violation(
            rule_id="F-9",
            rule_name="END OF BUNDLE metadata block",
            severity=YELLOW,
            section_id="metadata",
            line_no=len(bundle.raw_lines) or 1,
            line_content="(end of file)",
            message="Bundle is missing the `**END OF BUNDLE**` metadata block at the end.",
            fix_hint="Add `**END OF BUNDLE · vN**` followed by source-deck attribution + audit trail.",
        ))
    return violations


def check_f5_dividers_between_sections(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """F-5: every email/SMS section should be separated by `---` divider."""
    violations = []
    # Count emails + SMS; should have N+1 dividers minimum (between each)
    sections = bundle.all_communication_sections
    if len(sections) < 2:
        return violations
    divider_count = sum(1 for line in bundle.raw_lines if re.match(r"^-{3,}\s*$", line))
    # Expect at least len(sections) - 1 dividers between sections
    # Plus dividers around sequence headers (typically 2 per sequence header)
    sequence_header_count = sum(1 for s in bundle.sections if s.section_type == "sequence_header")
    expected_min = len(sections) - 1 + sequence_header_count
    if divider_count < expected_min:
        violations.append(Violation(
            rule_id="F-5",
            rule_name="divider between email/SMS sections",
            severity=YELLOW,
            section_id="metadata",
            line_no=1,
            line_content=f"(found {divider_count} dividers, expected ≥ {expected_min})",
            message=f"Found {divider_count} `---` dividers, expected at least {expected_min} for {len(sections)} sections.",
            fix_hint="Add `---` between every email and SMS section per F-5.",
        ))
    return violations


def check_f10_variable_placeholders_plain(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """F-10: variable placeholders {{...}} stay plain text (not escaped / not in code blocks).

    Catches: `\\{\\{contact.first_name\\}\\}`, `\`{{contact.first_name}}\``, etc.
    """
    violations = []
    ESCAPED_VAR_RE = re.compile(r"\\?\\\{\\?\\\{")  # \{\{
    BACKTICK_VAR_RE = re.compile(r"`\{\{[^}]+\}\}`")
    for section in bundle.all_communication_sections:
        for line_no, content in section.body_lines:
            if ESCAPED_VAR_RE.search(content):
                violations.append(Violation(
                    rule_id="F-10",
                    rule_name="variable placeholders stay plain text",
                    severity=HARD,
                    section_id=section.section_id,
                    line_no=line_no,
                    line_content=content.strip(),
                    message="Escaped variable placeholder `\\{\\{...\\}\\}` detected.",
                    fix_hint="Use plain `{{contact.X}}` without backslash escaping.",
                ))
            if BACKTICK_VAR_RE.search(content):
                violations.append(Violation(
                    rule_id="F-10",
                    rule_name="variable placeholders stay plain text",
                    severity=YELLOW,
                    section_id=section.section_id,
                    line_no=line_no,
                    line_content=content.strip(),
                    message="Variable placeholder wrapped in backticks · live copy should not be in code blocks.",
                    fix_hint="Remove backticks · live copy uses plain `{{contact.X}}`.",
                ))
    return violations


# ────────────────────────────────────────────────────────────────────────────
# RULES registry
# ────────────────────────────────────────────────────────────────────────────

RULES = [
    Rule(id="F-5",  name="dividers between sections",       severity=YELLOW, layer=LAYER, check=check_f5_dividers_between_sections,     applies_to=APPLIES_TO),
    Rule(id="F-8",  name="bundle title block at top",       severity=HARD,   layer=LAYER, check=check_f8_bundle_title_block,            applies_to=APPLIES_TO),
    Rule(id="F-9",  name="END OF BUNDLE metadata block",    severity=YELLOW, layer=LAYER, check=check_f9_end_of_bundle_block,           applies_to=APPLIES_TO),
    Rule(id="F-10", name="variable placeholders plain",     severity=HARD,   layer=LAYER, check=check_f10_variable_placeholders_plain,  applies_to=APPLIES_TO),
]
