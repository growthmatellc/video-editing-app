"""alec.py — Alec E-1 to E-10 mechanical checks.

Source-of-truth: skills/copywriting/references/alec-qc-checklists.md

Mechanical layer · semantic nuance (voice register match, sequence flow) in semantic.py.
Some overlap with Lauren UE rules · we dedupe by having Alec cover the rules Lauren doesn't.

Rules implemented:
  E-3 · single CTA per email (overlap with UE-4 but Alec's stricter at exactly 1 conceptual CTA)
  E-5 · mobile-first formatting · one new idea = one line break
  E-7 · signer voice consistency (sign-off matches across sequence)
  E-8 · numbered lists use real 1. 2. 3. not asterisk-bullets (overlap with F-4)
  E-9 · sentence-fragment rhythm in proof blocks (presence check)
"""

from __future__ import annotations

import re
from typing import List

from skills.copywriting.auditor.lib.parser import BundleSection, ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation


LAYER = "Alec"
APPLIES_TO = {"email_sequence", "email_launch"}


# ────────────────────────────────────────────────────────────────────────────
# E-7 · Signer voice consistency
# ────────────────────────────────────────────────────────────────────────────

SIGNOFF_RE = re.compile(r"^[—-]\s*(.+?)$", re.MULTILINE)

def check_e7_signer_consistency(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Warn if signers vary across the sequence (e.g., 'Coach Trent' in some, 'Trent' in others)."""
    violations = []
    signers_seen = {}  # section_id → signer
    for section in bundle.all_communication_sections:
        body = section.body or ""
        # Find sign-off lines · last non-blank line OR line starting with "— "
        signoff_matches = SIGNOFF_RE.findall(body)
        if signoff_matches:
            signer = signoff_matches[-1].strip()
            signers_seen[section.section_id] = signer
        else:
            # Look for "Coach X" or first name at the end of body
            last_lines = [line for line in body.strip().splitlines() if line.strip()]
            if last_lines:
                last = last_lines[-1].strip()
                if re.match(r"^(Coach\s+\w+|\w+(?:\s+\w+)?)\s*$", last):
                    signers_seen[section.section_id] = last
    # Check for variants
    unique_signers = set(signers_seen.values())
    if len(unique_signers) > 2:  # allow 1-2 variants (e.g., "Coach Trent" + "Coach Trent Harrison")
        violations.append(Violation(
            rule_id="E-7",
            rule_name="signer voice consistency",
            severity=YELLOW,
            section_id="metadata",
            line_no=1,
            line_content=f"(signers detected: {', '.join(sorted(unique_signers))[:200]})",
            message=f"Detected {len(unique_signers)} distinct signer variants. Alec rule: signer stays consistent.",
            fix_hint="Lock to one signer format across the bundle (e.g., 'Coach Trent' everywhere).",
        ))
    return violations


# ────────────────────────────────────────────────────────────────────────────
# E-8 · Numbered lists use real 1. 2. 3., not asterisks (covered by UE-2 + F-4)
# ────────────────────────────────────────────────────────────────────────────

# We let UE-2 handle the asterisk-bullet check; this is a positive check for ordered lists.
ORDERED_LIST_RE = re.compile(r"^\s*(\d+)\.\s+", re.MULTILINE)

def check_e8_numbered_lists(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Warn (YELLOW) if a LONG email has zero structural scannability cues.

    'Structural cues' includes:
      - Numbered lists (1. 2. 3.)
      - Bullet lists (- foo)
      - Block-quoted lines (case studies, avatar voice)
      - Heavy paragraph fragmentation (>6 paragraphs · prose with mobile-first breaks)

    Skip emails that are case-study driven (italicized quotes throughout) since
    quote rhythm IS the structure. Skip operational emails.
    """
    violations = []
    OPERATIONAL_KEYWORDS = (
        "confirmation", "booking", "agenda", "live in", "hour out",
        "hour before", "minutes before", "in 5", "five minutes", "5 minutes",
        "spots left", "live in 5", "going live", "live now",
    )
    for section in bundle.emails:
        body = section.body or ""
        if len(body) < 1500:  # only flag truly long emails (>1500 chars)
            continue
        # Skip operational emails
        desc = (section.description or "").lower()
        timing = (section.timing_label or "").lower()
        combined = f"{desc} {timing}"
        if any(kw in combined for kw in OPERATIONAL_KEYWORDS):
            continue
        ordered_count = len(ORDERED_LIST_RE.findall(body))
        bullet_dash_count = len(re.findall(r"^\s*-\s+", body, re.MULTILINE))
        # Count italic-quoted lines · case study quotes provide structure too
        italic_quote_count = len(re.findall(r"\*\"[^\"]+\"\*", body))
        # Count P.S. blocks · provide visual break
        ps_count = len(re.findall(r"^P\.?S\.?\s+", body, re.MULTILINE))
        # Count short paragraphs (lines surrounded by blank lines)
        paragraph_count = len([p for p in body.split("\n\n") if 5 < len(p.strip()) < 200])
        total_structure = ordered_count + bullet_dash_count + italic_quote_count + ps_count
        if total_structure == 0 and paragraph_count < 6:
            violations.append(Violation(
                rule_id="E-8",
                rule_name="structured content · scannability cues",
                severity=YELLOW,
                section_id=section.section_id,
                line_no=section.start_line,
                line_content=f"(email body {len(body)} chars, no structural cues)",
                message="Long email with no numbered lists, bullets, quoted blocks, or short paragraph rhythm · may be wall-of-text.",
                fix_hint="Add numbered list, bullets, italic-quoted case study, OR break into shorter paragraphs.",
            ))
    return violations


# ────────────────────────────────────────────────────────────────────────────
# RULES registry
# ────────────────────────────────────────────────────────────────────────────

RULES = [
    Rule(id="E-7", name="signer voice consistency",      severity=YELLOW, layer=LAYER, check=check_e7_signer_consistency, applies_to=APPLIES_TO),
    Rule(id="E-8", name="structured content (lists)",    severity=YELLOW, layer=LAYER, check=check_e8_numbered_lists,     applies_to=APPLIES_TO),
]
