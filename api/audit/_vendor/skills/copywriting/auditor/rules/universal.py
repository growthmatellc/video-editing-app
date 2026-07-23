"""universal.py — cross-cutting craft rules that apply to EVERY copy asset.

Source-of-truth: references/craft/anti-ai-tells.md + per-client banned phrases.

APPLIES_TO {"*"} means these run for every asset_type, so any copy output the
app routes through the auditor gets at least these code-enforced checks (the
em-dash / AI-tell / banned-phrase guarantees) regardless of whether a richer
per-asset module exists yet.

  U-1  · client banned phrases            (HARD)  — from clients/<slug> style guide + info.json
  U-2  · AI stock vocabulary              (YELLOW)
  U-3  · sycophancy / hedging stacks      (YELLOW)
  U-4  · em-dash overuse (>2 per para)    (YELLOW)
"""
from __future__ import annotations

import re
from typing import List

from skills.copywriting.auditor.lib.parser import ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation


LAYER = "Universal"
APPLIES_TO = {"*"}

# per_client.py already enforces banned phrases for email bundles; skip U-1 there
# to avoid double-flagging the same line.
_BANNED_SKIP_ASSETS = {"email_sequence", "email_launch"}

# anti-ai-tells.md · stock vocabulary (figurative/filler use)
STOCK_VOCAB = [
    "delve", "tapestry", "testament", "embark", "pivotal", "paramount",
    "seamless", "holistic", "realm", "cutting-edge", "state-of-the-art",
    "unlock", "elevate", "supercharge", "game-changer", "game changer",
]
# Hedging stacks + sycophancy openers
HEDGES = [
    "it's important to note", "it is important to note", "it's worth mentioning",
    "generally speaking", "in essence", "at its core", "it should be noted",
    "great question", "i'd be happy to help", "what a fascinating",
]
STOCK_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in STOCK_VOCAB) + r")\b", re.IGNORECASE)
HEDGE_RE = re.compile("|".join(re.escape(h) for h in HEDGES), re.IGNORECASE)
EM_DASH_RE = re.compile(r"[—–]")


def _content_lines(bundle: ParsedBundle):
    """(line_no, text) for non-empty, non-heading, non-divider lines."""
    for i, line in enumerate(bundle.raw_lines, start=1):
        s = line.strip()
        if not s or s.startswith("#") or set(s) <= {"-", "*", "_", " "}:
            continue
        yield i, line


def check_u1_banned_phrases(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if ctx.get("asset_type") in _BANNED_SKIP_ASSETS:
        return []
    client = ctx.get("client_data")
    banned = getattr(client, "banned_phrases", None) or []
    if not banned:
        return []
    violations = []
    for line_no, content in _content_lines(bundle):
        low = content.lower()
        for phrase in banned:
            if phrase and phrase.lower() in low:
                violations.append(Violation(
                    rule_id="U-1", rule_name="client banned phrase", severity=HARD,
                    section_id="body", line_no=line_no, line_content=content.strip(),
                    message=f'Uses a client banned phrase: "{phrase}".',
                    fix_hint=f'Remove "{phrase}" and rephrase in the client\'s approved language.',
                ))
                break
    return violations


def check_u2_stock_vocab(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for line_no, content in _content_lines(bundle):
        m = STOCK_RE.search(content)
        if m:
            violations.append(Violation(
                rule_id="U-2", rule_name="AI stock vocabulary", severity=YELLOW,
                section_id="body", line_no=line_no, line_content=content.strip(),
                message=f'AI-tell filler word: "{m.group(0)}".',
                fix_hint="Cut it or say the specific thing it stands in for.",
            ))
    return violations


def check_u3_hedges(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for line_no, content in _content_lines(bundle):
        m = HEDGE_RE.search(content)
        if m:
            violations.append(Violation(
                rule_id="U-3", rule_name="hedging / sycophancy stack", severity=YELLOW,
                section_id="body", line_no=line_no, line_content=content.strip(),
                message=f'Hedge/sycophancy filler: "{m.group(0)}".',
                fix_hint="Cut the hedge; state the point directly.",
            ))
    return violations


def check_u4_em_dash_overuse(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """anti-ai-tells.md: hard cap of 2 em dashes per paragraph."""
    violations = []
    line_no = 0
    for para in (bundle.raw_text or "").split("\n\n"):
        para_lines = para.split("\n")
        if len(EM_DASH_RE.findall(para)) > 2:
            first = next((ln for ln in para_lines if ln.strip()), "")
            violations.append(Violation(
                rule_id="U-4", rule_name="em-dash overuse", severity=YELLOW,
                section_id="body", line_no=line_no + 1, line_content=first.strip()[:120],
                message="More than 2 em dashes in one paragraph (AI tell).",
                fix_hint="Rewrite with commas or periods; cap at 2 per paragraph.",
            ))
        line_no += len(para_lines) + 1
    return violations


RULES = [
    Rule(id="U-1", name="client banned phrase", severity=HARD, layer=LAYER,
         check=check_u1_banned_phrases, applies_to=APPLIES_TO),
    Rule(id="U-2", name="AI stock vocabulary", severity=YELLOW, layer=LAYER,
         check=check_u2_stock_vocab, applies_to=APPLIES_TO),
    Rule(id="U-3", name="hedging / sycophancy stack", severity=YELLOW, layer=LAYER,
         check=check_u3_hedges, applies_to=APPLIES_TO),
    Rule(id="U-4", name="em-dash overuse", severity=YELLOW, layer=LAYER,
         check=check_u4_em_dash_overuse, applies_to=APPLIES_TO),
]
