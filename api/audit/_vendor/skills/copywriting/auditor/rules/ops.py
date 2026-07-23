"""ops.py — operations rules (scope boundary, output destination, naming, mobile-first).

These apply across all asset types. Many are RUNTIME checks (e.g., output destination)
that don't apply to a static file audit · those become structural/hint checks here.

Rules:
  OPS-1 · output file naming convention (`<client-slug>-<asset-type>-<version>.md`)
  OPS-2 · sequence headers present (multi-sequence bundles need # SEQUENCE N markers)
  OPS-3 · ordered list 4-touchpoint structure for post-booking-pre-call sequences
"""

from __future__ import annotations

import os
import re
from typing import List

from skills.copywriting.auditor.lib.parser import ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation


LAYER = "Ops"
APPLIES_TO = {"*"}  # applies to all asset types


def check_ops1_naming_convention(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Filename should match `<date>_<client-slug>-<asset-type>-<version>.md` pattern (loose)."""
    violations = []
    file_path = ctx.get("file_path", "")
    if not file_path:
        return violations
    basename = os.path.basename(file_path).lower()
    # Expect: <date>_<slug>-<asset-tag>-<version>.md
    if not re.match(r"^\d{4}-\d{2}-\d{2}_[\w-]+\.md$", basename):
        violations.append(Violation(
            rule_id="OPS-1",
            rule_name="output naming convention",
            severity=YELLOW,
            section_id="metadata",
            line_no=1,
            line_content=basename,
            message=f"Filename `{basename}` doesn't match `<YYYY-MM-DD>_<slug>-<asset>-<version>.md`.",
            fix_hint="Rename per Lauren ops · `2026-06-24_trent-w3-bundle-v6.md` style.",
        ))
    return violations


def check_ops2_sequence_headers(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Multi-section bundles should have sequence headers."""
    violations = []
    if ctx.get("asset_type") not in ("email_sequence",):
        return violations
    sequence_headers = [s for s in bundle.sections if s.section_type == "sequence_header"]
    sections = bundle.all_communication_sections
    if len(sections) > 8 and not sequence_headers:
        violations.append(Violation(
            rule_id="OPS-2",
            rule_name="sequence headers for multi-sequence bundles",
            severity=YELLOW,
            section_id="metadata",
            line_no=1,
            line_content=f"({len(sections)} sections, 0 sequence headers)",
            message=f"Bundle has {len(sections)} email/SMS sections but no `# SEQUENCE N` headers.",
            fix_hint="Add `# SEQUENCE 1 — PRE-WEBINAR (counts)` style headers per F-7.",
        ))
    return violations


RULES = [
    Rule(id="OPS-1", name="output naming convention",           severity=YELLOW, layer=LAYER, check=check_ops1_naming_convention,     applies_to=APPLIES_TO),
    Rule(id="OPS-2", name="sequence headers (multi-sequence)",  severity=YELLOW, layer=LAYER, check=check_ops2_sequence_headers,      applies_to={"email_sequence"}),
]
