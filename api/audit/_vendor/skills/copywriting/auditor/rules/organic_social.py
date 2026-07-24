"""organic_social.py — OS-1 to OS-4 · organic social posts.

Organic is not paid. The whole module hangs off one distinction, stated in
skills/scripting/organic-social/meta.json under `distinguishing_rules_organic_vs_paid`:
organic posts get SOFT CTAs only, and the post has to earn the read without the CTA.

Sources:
  skills/scripting/organic-social/meta.json    soft_ctas_only.forbidden + .acceptable arrays
  skills/scripting/organic-social/workflow.md  one-CTA rule, per-platform structures
"""

from __future__ import annotations

import re
from typing import List, Optional

from skills.copywriting.auditor.lib.parser import ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation
from skills.copywriting.auditor.lib import sections as S


LAYER = "OrganicSocial"
APPLIES_TO = {"organic_social"}


# meta.json `soft_ctas_only.forbidden` — verbatim, plus the funnel rule-1 phrases the module
# inherits ("forbid 'discovery call' / 'strategy call' language, Lauren funnel rule 1, adapted").
FORBIDDEN_CTA_RE = re.compile(
    r"("
    r"buy\s+now"
    r"|add\s+to\s+cart"
    r"|book\s+a\s+(?:discovery|strategy)\s+call"
    r"|schedule\s+a\s+(?:discovery|strategy)\s+call"
    r"|(?:discovery|strategy)\s+(?:call|session)"
    r"|free\s+consultation"
    r"|click\s+(?:the\s+)?link\s+in\s+bio\s+to\s+purchase"
    r"|enroll\s+now"
    r"|book\s+a\s+call"
    r")",
    re.IGNORECASE,
)

# meta.json `soft_ctas_only.acceptable` — CTA shapes, not literals.
SOFT_CTA_RE = re.compile(
    r"^\s*(?:comment\b|dm\s+me\b|save\s+this\b|tag\s+someone\b|follow\s+for\s+more\b"
    r"|share\s+if\b|drop\s+a\b|send\s+me\b)",
    re.IGNORECASE,
)

# Each distinct soft-CTA kind, for the "one ask" rule.
SOFT_CTA_KINDS = {
    "comment": r"\bcomment\b",
    "dm": r"\bdm\s+me\b|\bsend\s+me\s+a\s+dm\b",
    "save": r"\bsave\s+this\b|\bsave\s+it\b",
    "tag": r"\btag\s+someone\b",
    "follow": r"\bfollow\s+for\s+more\b",
    "share": r"\bshare\s+if\b",
}


def _post_classifier(title: str) -> Optional[str]:
    if re.search(r"post|carousel|reel|thread|slide|caption|tiktok|linkedin", title, re.I):
        return "post"
    return None


def _posts(bundle: ParsedBundle) -> List[S.Section]:
    posts = S.split_sections(bundle.raw_lines, _post_classifier)
    if posts:
        return posts
    # Single unsectioned post — treat the whole doc as one.
    whole = S.Section(key="post", heading="post", level=1, start_line=1)
    whole.lines = [(i + 1, l) for i, l in enumerate(bundle.raw_lines)]
    whole.end_line = len(bundle.raw_lines)
    return [whole]


def _v(rule_id, rule_name, severity, section_id, line_no, line, message, fix) -> Violation:
    return Violation(
        rule_id=rule_id, rule_name=rule_name, severity=severity,
        section_id=section_id, line_no=line_no, line_content=line, message=message, fix_hint=fix,
    )


# ---------------------------------------------------------------------------
# OS-0 · the document parses into a post with actual copy
#
# `_posts` never returns empty — it falls back to the whole doc as one post — so without this
# guard an empty or header-only file runs every OS rule on nothing and prints a pass (only OS-3
# warns). A file with no post copy is a HARD failure, never a silent one. (Same stance as VA-0.)
# ---------------------------------------------------------------------------


def check_os0_parseable(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    copy = [l for l in bundle.raw_lines if l.strip() and not S.HEADER_RE.match(l)]
    if copy:
        return []
    return [_v(
        "OS-0", "document parses", HARD, "document", 1, "(no post copy parsed)",
        "No organic-post copy could be parsed, so no OS rule was actually evaluated. The auditor "
        "will not pass a file it cannot read — only headers or blank lines were found.",
        "Add the post copy, or fix the format if this is a new structure.",
    )]


# ---------------------------------------------------------------------------
# OS-1 · no hard / direct-sale CTAs
# ---------------------------------------------------------------------------


def check_os1_no_hard_cta(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for post in _posts(bundle):
        for line_no, content in post.lines:
            for m in FORBIDDEN_CTA_RE.finditer(content):
                violations.append(_v(
                    "OS-1", "soft CTAs only", HARD, post.section_id, line_no, content.strip(),
                    f"`{m.group(0)}` is a direct-sale ask. Organic posts get soft CTAs only — comment, "
                    f"DM, save, tag, follow, share. Hard asks belong in paid.",
                    "Swap it for a soft ask, e.g. `comment YES if this hit home` or `DM me [keyword]`.",
                ))
    return violations


# ---------------------------------------------------------------------------
# OS-2 · one CTA only — no CTA stacking
#   workflow.md · "Organic social gets ONE soft CTA per post. Never two."
# ---------------------------------------------------------------------------


def check_os2_one_cta(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for post in _posts(bundle):
        kinds = set()
        first_line = None
        for line_no, content in post.lines:
            for kind, pattern in SOFT_CTA_KINDS.items():
                if re.search(pattern, content, re.I):
                    if kind not in kinds and first_line is None:
                        first_line = line_no
                    kinds.add(kind)
        if len(kinds) > 1:
            violations.append(_v(
                "OS-2", "one CTA only", HARD, post.section_id, first_line or post.start_line,
                f"(asks: {', '.join(sorted(kinds))})",
                f"Post stacks {len(kinds)} competing asks ({', '.join(sorted(kinds))}). Organic gets ONE "
                f"soft CTA. Never two. No 'save this AND follow AND DM me.'",
                "Pick one ask. Repeat the same ask if the platform needs it, but never a second one.",
            ))
    return violations


# ---------------------------------------------------------------------------
# OS-3 · a soft CTA is actually present
# ---------------------------------------------------------------------------


def check_os3_soft_cta_present(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for post in _posts(bundle):
        if any(re.search(p, post.body, re.I) for p in SOFT_CTA_KINDS.values()):
            continue
        violations.append(_v(
            "OS-3", "soft CTA present", YELLOW, post.section_id, post.start_line,
            "(no soft CTA found)",
            "No soft CTA found in the post. Organic still asks for something — a comment, a save, a DM.",
            "Add one soft ask, e.g. `save this for when you're ready`.",
        ))
    return violations


# ---------------------------------------------------------------------------
# OS-4 · shared craft rules
# ---------------------------------------------------------------------------


def check_os4_craft(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for idx, line in enumerate(bundle.raw_lines):
        # Markdown headers are the doc's own scaffolding ("## IG Carousel — Metabolism"),
        # not copy the audience ever sees. Only the published lines get scanned.
        if S.HEADER_RE.match(line):
            continue
        if S.EM_DASH_RE.search(line):
            violations.append(_v(
                "OS-4", "craft · no em dashes", HARD, "body", idx + 1, line.strip(),
                "Em dash. Growth Mate copy uses a comma, a period, or a rewrite.",
                "Replace the em dash.",
            ))
    return violations


RULES = [
    Rule(id="OS-0", name="document parses",      severity=HARD,   layer=LAYER, check=check_os0_parseable,        applies_to=APPLIES_TO),
    Rule(id="OS-1", name="soft CTAs only",       severity=HARD,   layer=LAYER, check=check_os1_no_hard_cta,      applies_to=APPLIES_TO),
    Rule(id="OS-2", name="one CTA only",         severity=HARD,   layer=LAYER, check=check_os2_one_cta,          applies_to=APPLIES_TO),
    Rule(id="OS-3", name="soft CTA present",     severity=YELLOW, layer=LAYER, check=check_os3_soft_cta_present, applies_to=APPLIES_TO),
    Rule(id="OS-4", name="craft · no em dashes", severity=HARD,   layer=LAYER, check=check_os4_craft,            applies_to=APPLIES_TO),
]
