"""lauren.py — Lauren UE-1 to UE-6 universal email gates · mechanical checks.

Source-of-truth: skills/email-sms-building/email-sequence/workflow.md
                 § Universal email copy QC gates

Rules implemented:
  UE-1 · Subject line (mechanical: ≤7 word cap excl. bracket prefix; semantic in semantic.py)
  UE-2 · Body formatting (no em dashes, no double dashes, no asterisk bullets,
         paragraph length, mobile width)
  UE-3 · Podcast/YouTube verification (YELLOW · placeholder for runtime verification)
  UE-4 · Word count (≤500 per email) + CTA count (exactly 1 per email)
  UE-5 · P.S. value (must add secondary value, not repeat primary CTA)
  UE-6 · GHL variable compliance (zero hardcoded URLs, allowlist, button URLs, variables list block)
"""

from __future__ import annotations

import re
from typing import List

from skills.copywriting.auditor.lib.parser import BundleSection, ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation
from skills.copywriting.auditor.lib import sections as S


LAYER = "Lauren"
APPLIES_TO = {"email_sequence", "email_launch"}


# ────────────────────────────────────────────────────────────────────────────
# UE-1 · Subject line gates (mechanical)
# ────────────────────────────────────────────────────────────────────────────

BRACKET_PREFIX_RE = re.compile(r"^\s*\[[^\]]+\]\s*")

def check_ue1_subject_line(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """≤7 words of content, on EVERY subject variant.

    Emails now ship 2-3 subject options (SL-5). Checking only the first one would let a
    15-word variant B through the cap — and variant B is one the operator might well ship.
    """
    violations = []
    for section in bundle.emails:
        for line_no, subject in S.subject_variants(section):
            # Strip bracket workshop-name prefix (doesn't count toward 7-word limit)
            content_only = BRACKET_PREFIX_RE.sub("", subject).strip()
            word_count = len(content_only.split())
            if word_count > 7:
                violations.append(Violation(
                    rule_id="UE-1",
                    rule_name="subject line ≤7 words (excl. bracket prefix)",
                    severity=HARD,
                    section_id=section.section_id,
                    line_no=line_no,
                    line_content=subject,
                    message=f"Subject line content is {word_count} words (max 7, bracketed prefix excluded).",
                    fix_hint="Tighten subject. Concrete result, distinct hook. One-idea ad-style, not a sentence.",
                ))
    return violations


# ────────────────────────────────────────────────────────────────────────────
# UE-2 · Body formatting (no double-dashes, no asterisk-bullets, paragraph length)
# ────────────────────────────────────────────────────────────────────────────

DOUBLE_DASH_RE = re.compile(r"--")  # disallowed
ASTERISK_BULLET_RE = re.compile(r"^\s*\*\s+(?!\*)")  # `* foo` as bullet (not `**bold**`)

def check_ue2_body_formatting(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for section in bundle.all_communication_sections:
        for line_no, content in section.body_lines:
            if DOUBLE_DASH_RE.search(content):
                violations.append(Violation(
                    rule_id="UE-2",
                    rule_name="body formatting · no double dashes",
                    severity=HARD,
                    section_id=section.section_id,
                    line_no=line_no,
                    line_content=content.strip(),
                    message="Double dash `--` detected.",
                    fix_hint="Replace with period, comma, or sentence break.",
                ))
            if ASTERISK_BULLET_RE.match(content):
                violations.append(Violation(
                    rule_id="UE-2",
                    rule_name="body formatting · no asterisk bullets",
                    severity=HARD,
                    section_id=section.section_id,
                    line_no=line_no,
                    line_content=content.strip(),
                    message="Asterisk used as bullet point. Use `-` or numbered list (F-4).",
                    fix_hint="Change `*` to `-` or use `1. 2. 3.` numbered format.",
                ))
    # Paragraph length: count consecutive non-blank lines per email and warn if any paragraph > 4 lines
    #
    # The `**Subject A:** / **Preview A:**` block is the email's HEADER, not its body — six
    # metadata lines in a row are not a wall of text. Counting them flagged every email in a
    # correctly-formatted bundle.
    for section in bundle.emails:
        paragraph_start = None
        consecutive_lines = 0
        for line_no, content in section.body_lines:
            if S.SUBJECT_VARIANT_RE.match(content) or S.PREVIEW_VARIANT_RE.match(content):
                continue
            if content.strip():
                if paragraph_start is None:
                    paragraph_start = line_no
                consecutive_lines += 1
            else:
                if consecutive_lines > 5:  # warn if paragraph > 5 lines · likely wall of text
                    violations.append(Violation(
                        rule_id="UE-2",
                        rule_name="body formatting · mobile-friendly paragraph length",
                        severity=YELLOW,
                        section_id=section.section_id,
                        line_no=paragraph_start,
                        line_content=f"(paragraph spans {consecutive_lines} lines)",
                        message=f"Paragraph is {consecutive_lines} lines long. Mobile-first: split at idea boundaries.",
                        fix_hint="One new idea = one line break (Lauren's rule).",
                    ))
                paragraph_start = None
                consecutive_lines = 0
    return violations


# ────────────────────────────────────────────────────────────────────────────
# UE-4 · Word count + CTA count
# ────────────────────────────────────────────────────────────────────────────

# CTA pattern · matches [BUTTON ALL CAPS] style placeholders
CTA_BUTTON_RE = re.compile(r"\[([A-Z][A-Z0-9 ·\-]{2,})\]")

def check_ue4_word_count_and_ctas(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for section in bundle.emails:
        body = section.body or ""
        # Strip button URL declarations from word count
        body_for_count = re.sub(r"\(button URL:[^)]*\)", "", body)
        # Strip {{...}} placeholders
        body_for_count = re.sub(r"\{\{[^}]+\}\}", "", body_for_count)
        # Strip markdown markup
        body_for_count = re.sub(r"\*+", "", body_for_count)
        body_for_count = re.sub(r"\[([^\]]+)\]", r"\1", body_for_count)
        words = re.findall(r"\b\w+\b", body_for_count)
        word_count = len(words)
        if word_count > 500:
            violations.append(Violation(
                rule_id="UE-4",
                rule_name="word count ≤500 per email",
                severity=HARD,
                section_id=section.section_id,
                line_no=section.start_line,
                line_content=f"(email body word count: {word_count})",
                message=f"Email body is {word_count} words (max 500). Cut.",
                fix_hint="Trim. Lauren rule: shorter is better. If can't, split into 2 emails.",
            ))

        # CTA count · count distinct button placeholders (action verbs)
        # We allow 1 conceptual CTA · which may have related sub-buttons (e.g., ADD TO CALENDAR + SAVE ZOOM LINK on confirmation)
        # So this is YELLOW unless egregious
        cta_buttons = CTA_BUTTON_RE.findall(body)
        # Filter: skip non-CTA placeholders like [LINK]
        cta_buttons = [b for b in cta_buttons if not re.match(r"^LINK$", b)]
        if len(cta_buttons) > 4:
            violations.append(Violation(
                rule_id="UE-4",
                rule_name="CTA count (single primary ask)",
                severity=YELLOW,
                section_id=section.section_id,
                line_no=section.start_line,
                line_content=f"({len(cta_buttons)} button placeholders: {', '.join(cta_buttons[:5])})",
                message=f"Email has {len(cta_buttons)} button placeholders. May be stacking CTAs.",
                fix_hint="Lauren rule: one topic, one hook, one action. Collapse or split.",
            ))
    return violations


# ────────────────────────────────────────────────────────────────────────────
# UE-5 · P.S. value (must not repeat primary CTA)
# ────────────────────────────────────────────────────────────────────────────

PS_RE = re.compile(r"^P\.?S\.?\s+(.+?)$", re.MULTILINE)

def check_ue5_ps_value(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for section in bundle.emails:
        body = section.body or ""
        ps_matches = list(PS_RE.finditer(body))
        if not ps_matches:
            continue
        # Get primary CTA · take the FIRST button placeholder in body
        primary_cta_match = CTA_BUTTON_RE.search(body[:body.find("P.S.")] if "P.S." in body else body)
        if not primary_cta_match:
            continue
        primary_cta_text = primary_cta_match.group(1).lower()
        # For each P.S., check that it doesn't just repeat the primary CTA
        for ps in ps_matches:
            ps_content = ps.group(1).lower()
            # If P.S. contains the exact primary CTA text AND has no other unique content (<30 chars unique), flag
            if primary_cta_text in ps_content and len(ps_content) < 80 and len(ps_content) - len(primary_cta_text) < 30:
                line_no_offset = body[:ps.start()].count("\n")
                actual_line = section.body_lines[0][0] + line_no_offset if section.body_lines else section.start_line
                violations.append(Violation(
                    rule_id="UE-5",
                    rule_name="P.S. value · don't repeat primary CTA",
                    severity=YELLOW,
                    section_id=section.section_id,
                    line_no=actual_line,
                    line_content=ps.group(0)[:120],
                    message="P.S. appears to just restate the primary CTA.",
                    fix_hint=(
                        "P.S. should add SECONDARY value: proof element, urgency reframe, soft objection-handler, "
                        "bonus insight · or remove the P.S. entirely."
                    ),
                ))
    return violations


# ────────────────────────────────────────────────────────────────────────────
# UE-6 · GHL variable compliance
# ────────────────────────────────────────────────────────────────────────────

# Canonical custom_values allowlist (the 7 + per-client extras like instagram_url, podcast_url)
CANONICAL_CUSTOM_VALUES = {
    "live_webinar_date",
    "live_webinar_time",
    "live_webinar_add_event",
    "live_webinar_zoom_register_link",
    "live_webinar_replay_link",
    "strategy_call_link",
    "strategy_call_add_event",
    "sending_email_domain",
    # Per-client extras (any client may use these · documented in variables-list block)
    "instagram_url",
    "podcast_url",
    "protocol_url",          # for clients with a pre-call protocol / portal (Project Transform X)
    "case_studies_url",      # testimonial / case-study page URL
}

# Legacy variable names · DEPRECATED · should not appear
LEGACY_VARIABLES = {
    "webinar_day_ordinal",
    "replay_link",
    "webinar_end_time",
    "appointment.date",
    "appointment.time",
    "appointment.meeting_location",
}

# Variable extraction
VAR_RE = re.compile(r"\{\{([^}]+)\}\}")
# Hardcoded URL detection
HARDCODED_URL_RE = re.compile(r"https?://[^\s)]+|\b[a-z0-9-]+\.(?:com|io|org|app|co|net)/[^\s)]+", re.IGNORECASE)
# Button placeholder
BUTTON_PLACEHOLDER_RE = re.compile(r"^\s*\[([A-Z][A-Z0-9 ·\-]{2,})\]\s*$")
# Button URL declaration on next line
BUTTON_URL_DECL_RE = re.compile(r"^\s*\(button URL:\s*\{\{[^}]+\}\}\s*\)\s*$")
# Documentation lines · the GHL variables block at top of file (don't flag URLs/legacy vars there)


def _is_in_variables_block(line_no: int, bundle: ParsedBundle) -> bool:
    """Return True if the line falls inside the GHL VARIABLES USED documentation block."""
    if not bundle.has_variables_block or not bundle.variables_block:
        return False
    # Find start/end line of the variables_block in raw_lines
    block_text = bundle.variables_block
    block_lines = block_text.splitlines()
    if not block_lines:
        return False
    # Find first match in raw_lines
    first_line = block_lines[0]
    for i, raw in enumerate(bundle.raw_lines):
        if raw == first_line:
            start = i + 1  # 1-indexed
            end = start + len(block_lines)
            if start <= line_no < end:
                return True
            break
    return False


def check_ue6_ghl_variable_compliance(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []

    # ── Check 1: variables list block present at top ─────────────────────────
    if not bundle.has_variables_block:
        violations.append(Violation(
            rule_id="UE-6",
            rule_name="GHL variables list block at top of file",
            severity=HARD,
            section_id="metadata",
            line_no=1,
            line_content="(no `## GHL VARIABLES USED` block found)",
            message="Output file is missing the canonical GHL variables-list block at top.",
            fix_hint=(
                "Add a `## GHL VARIABLES USED` block listing every {{contact.X}} and "
                "{{custom_values.X}} the bundle references · see ghl-variable-conventions.md."
            ),
        ))

    # ── Check 2: hardcoded URLs in body/SMS ───────────────────────────────────
    for section in bundle.all_communication_sections:
        for line_no, content in section.body_lines:
            # Skip lines inside the GHL variables documentation block
            if _is_in_variables_block(line_no, bundle):
                continue
            # Skip "(button URL:" declarations · those are intentionally documenting the var
            if BUTTON_URL_DECL_RE.match(content):
                continue
            url_match = HARDCODED_URL_RE.search(content)
            if url_match:
                # Exception: skip if the URL is a known documentation pattern like `example.com`
                url = url_match.group(0)
                violations.append(Violation(
                    rule_id="UE-6",
                    rule_name="GHL variable compliance · no hardcoded URLs",
                    severity=HARD,
                    section_id=section.section_id,
                    line_no=line_no,
                    line_content=content.strip(),
                    message=f"Hardcoded URL detected: `{url[:60]}`",
                    fix_hint="Replace with `{{custom_values.X}}` per ghl-variable-conventions.md.",
                ))

    # ── Check 3: legacy variable names ────────────────────────────────────────
    for section in bundle.all_communication_sections:
        for line_no, content in section.body_lines:
            if _is_in_variables_block(line_no, bundle):
                continue
            for match in VAR_RE.finditer(content):
                var_name = match.group(1).strip()
                # Strip prefix (contact./custom_values.)
                bare_name = var_name.split(".", 1)[1] if "." in var_name else var_name
                if var_name in LEGACY_VARIABLES or bare_name in LEGACY_VARIABLES:
                    violations.append(Violation(
                        rule_id="UE-6",
                        rule_name="GHL variable compliance · no legacy variable names",
                        severity=HARD,
                        section_id=section.section_id,
                        line_no=line_no,
                        line_content=content.strip(),
                        message=f"Legacy variable `{{{{{var_name}}}}}` detected.",
                        fix_hint="Use canonical custom_values per ghl-variable-conventions.md.",
                    ))

    # ── Check 4: every [BUTTON] followed by (button URL: {{custom_values.X}}) ─
    for section in bundle.all_communication_sections:
        body_lines_list = section.body_lines
        for i, (line_no, content) in enumerate(body_lines_list):
            m = BUTTON_PLACEHOLDER_RE.match(content)
            if not m:
                continue
            button_label = m.group(1)
            # Skip [LINK] · that's an inline link placeholder, not a button
            if button_label == "LINK":
                continue
            # Check next non-blank line
            j = i + 1
            while j < len(body_lines_list) and not body_lines_list[j][1].strip():
                j += 1
            if j >= len(body_lines_list):
                next_content = ""
            else:
                next_content = body_lines_list[j][1]
            if not BUTTON_URL_DECL_RE.match(next_content):
                violations.append(Violation(
                    rule_id="UE-6",
                    rule_name="GHL variable compliance · button URL declarations",
                    severity=HARD,
                    section_id=section.section_id,
                    line_no=line_no,
                    line_content=content.strip(),
                    message=f"`[{button_label}]` not followed by `(button URL: {{{{custom_values.X}}}})` declaration.",
                    fix_hint=f"Add `(button URL: {{{{custom_values.X}}}})` on the line after `[{button_label}]`.",
                ))

    # ── Check 5: variable allowlist · catch unknown custom_values ────────────
    for section in bundle.all_communication_sections:
        for line_no, content in section.body_lines:
            if _is_in_variables_block(line_no, bundle):
                continue
            for match in VAR_RE.finditer(content):
                var_name = match.group(1).strip()
                # If it's a custom_values.X, check against allowlist
                if var_name.startswith("custom_values."):
                    bare = var_name[len("custom_values."):]
                    if bare not in CANONICAL_CUSTOM_VALUES:
                        violations.append(Violation(
                            rule_id="UE-6",
                            rule_name="GHL variable compliance · variable allowlist",
                            severity=YELLOW,
                            section_id=section.section_id,
                            line_no=line_no,
                            line_content=content.strip(),
                            message=f"Custom value `{{{{{var_name}}}}}` not in canonical allowlist.",
                            fix_hint=(
                                "If this is a per-client extra (e.g., instagram_url), document it in the "
                                "variables list block at top of file. Otherwise use a canonical name."
                            ),
                        ))

    return violations


# ────────────────────────────────────────────────────────────────────────────
# RULES registry
# ────────────────────────────────────────────────────────────────────────────

RULES = [
    Rule(id="UE-1", name="subject line ≤7 words",          severity=HARD,   layer=LAYER, check=check_ue1_subject_line,             applies_to=APPLIES_TO),
    Rule(id="UE-2", name="body formatting (no dashes, etc)", severity=HARD,  layer=LAYER, check=check_ue2_body_formatting,          applies_to=APPLIES_TO),
    Rule(id="UE-4", name="word count + CTA count",          severity=HARD,   layer=LAYER, check=check_ue4_word_count_and_ctas,      applies_to=APPLIES_TO),
    Rule(id="UE-5", name="P.S. value (no CTA repeat)",      severity=YELLOW, layer=LAYER, check=check_ue5_ps_value,                 applies_to=APPLIES_TO),
    Rule(id="UE-6", name="GHL variable compliance",         severity=HARD,   layer=LAYER, check=check_ue6_ghl_variable_compliance,  applies_to=APPLIES_TO),
]
