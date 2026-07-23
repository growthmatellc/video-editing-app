"""per_client.py — per-client locked AHAs, banned phrases, mechanism source-of-truth.

Loads from clients/<slug>/info.json, style-guide.md, term-mappings.json (via lib/per_client.py).

Rules:
  PC-1 · banned phrases not present in output
  PC-2 · mechanism source-of-truth respected (don't reframe Trent's "Volume Eating" to "5M Method", etc.)
  PC-3 · locked AHA reference present in core copy assets (advisory · YELLOW)
"""

from __future__ import annotations

import re
from typing import List

from skills.copywriting.auditor.lib.parser import ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation


LAYER = "Per-Client"
APPLIES_TO = {"*"}


def check_pc1_banned_phrases(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    client_data = ctx.get("client_data")
    if not client_data or not client_data.banned_phrases:
        return violations
    for section in bundle.all_communication_sections:
        for line_no, content in section.body_lines:
            for phrase in client_data.banned_phrases:
                if not phrase or len(phrase) < 3:  # skip 1-2 char "phrases" · false positives
                    continue
                if phrase.lower() in content.lower():
                    violations.append(Violation(
                        rule_id="PC-1",
                        rule_name=f"per-client banned phrase ({client_data.slug})",
                        severity=HARD,
                        section_id=section.section_id,
                        line_no=line_no,
                        line_content=content.strip(),
                        message=f"Banned phrase `{phrase}` detected (per {client_data.slug}/style-guide.md).",
                        fix_hint=f"Remove or rephrase. Check `clients/{client_data.slug}/style-guide.md` for alternative.",
                    ))
    return violations


def check_pc2_mechanism_source_of_truth(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """If client has a locked mechanism name (e.g., Trent: 'Volume Eating'), warn on deprecated names."""
    violations = []
    client_data = ctx.get("client_data")
    if not client_data or not client_data.mechanism_source_of_truth:
        return violations

    # Known deprecated alternates per client
    DEPRECATED_MECHANISMS = {
        "trent-harrison": ["5M Method", "Five M", "Maintenance Inversion"],
    }
    deprecated = DEPRECATED_MECHANISMS.get(client_data.slug, [])
    if not deprecated:
        return violations

    for section in bundle.all_communication_sections:
        for line_no, content in section.body_lines:
            for old_name in deprecated:
                if re.search(r"\b" + re.escape(old_name) + r"\b", content, re.IGNORECASE):
                    violations.append(Violation(
                        rule_id="PC-2",
                        rule_name=f"mechanism source-of-truth ({client_data.slug})",
                        severity=HARD,
                        section_id=section.section_id,
                        line_no=line_no,
                        line_content=content.strip(),
                        message=(
                            f"Deprecated mechanism name `{old_name}` detected. "
                            f"Locked source-of-truth: `{client_data.mechanism_source_of_truth}`."
                        ),
                        fix_hint=f"Replace `{old_name}` with `{client_data.mechanism_source_of_truth}`.",
                    ))
    return violations


RULES = [
    Rule(id="PC-1", name="per-client banned phrases",        severity=HARD, layer=LAYER, check=check_pc1_banned_phrases,             applies_to=APPLIES_TO),
    Rule(id="PC-2", name="mechanism source-of-truth",        severity=HARD, layer=LAYER, check=check_pc2_mechanism_source_of_truth,  applies_to=APPLIES_TO),
]
