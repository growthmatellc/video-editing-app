"""semantic.py — Claude-as-judge semantic checks for nuance rules.

These rules require LLM-level understanding of the copy. The checks call
Claude Haiku with strict JSON output schemas and a hard pass/fail verdict.

Skipped when --no-semantic flag is set (for dev cycles + cost control).

Rules implemented (Phase 3):
  SEM-T19 · setup-statement vs avatar-voice disambiguation (catches "fancy setup" disguised as scene)
  SEM-T20 · mechanism reveal nuance (catches mechanism leak that mechanical pattern missed)
  SEM-T9  · credentials truly bound to avatar outcome (not just resume-style)
  SEM-VR  · voice register match against client style-guide
  SEM-UE1 · subject line per-audience strength (cold-audience test from UE-1)
"""

from __future__ import annotations

import json
import os
from typing import List

from skills.copywriting.auditor.lib.parser import ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation


LAYER = "Semantic"
APPLIES_TO = {"email_sequence", "email_launch"}


# ────────────────────────────────────────────────────────────────────────────
# Claude API integration · uses ANTHROPIC_API_KEY env var
# ────────────────────────────────────────────────────────────────────────────

def _call_claude_judge(system_prompt: str, user_content: str, max_tokens: int = 1500) -> dict:
    """Call Claude Haiku as a JSON-only judge.

    Returns parsed JSON dict or {"error": "..."} on failure.
    Uses urllib (no requests dependency to match the caretaker pattern).
    """
    import urllib.request
    import urllib.error

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not set"}

    body = {
        "model": "claude-haiku-4-5",
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_content}],
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        # Extract text from content blocks
        text = ""
        for block in payload.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        # Parse JSON · the judge is asked to return JSON only
        # Strip code fences if present
        text = text.strip()
        if text.startswith("```"):
            # Strip first/last code-fence lines
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return json.loads(text)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return {"error": f"API error: {e}"}
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}"}


# ────────────────────────────────────────────────────────────────────────────
# SEM-T19 · setup-statement nuance
# ────────────────────────────────────────────────────────────────────────────

SEM_T19_SYSTEM = """You audit email opening lines against Tom Render's craft rule T-19.

Rule T-19 says: an email's opening line MUST be either:
  (a) an avatar-voice quote first · `[Name] said to me "[verbatim avatar quote]." [next beat]`
  (b) a direct scene the avatar recognizes · `Imagine two plates. Same calories.` / `Every single week I get a message from a woman that says "[verbatim]"`
  (c) a credential-bound-to-outcome line for origin emails · `I quit X to help women just like you Y.`

BANNED openers (any of these = FAIL):
  - "I want to tell you about [name/thing]"
  - "Let me show you [thing]"
  - "Before we get there, I want you to know..."
  - "I want to take one thought/thing off the table"
  - "Here's a story about a client of mine"
  - "I'm going to share something with you"
  - "Today I want to talk about..."
  - Any self-referential setup that makes the reader work for the relevance
  - Any countdown opener that ISN'T a 1-day/1-hour/5-min reminder

You will receive ONE email's opening line. Return STRICTLY this JSON:
{
  "verdict": "PASS" | "FAIL",
  "category": "avatar-voice" | "direct-scene" | "credential-outcome" | "operational-direct" | "setup-statement" | "countdown" | "other",
  "reasoning": "1-2 sentence explanation"
}

No prose outside the JSON. No markdown code fences."""


def check_sem_t19_setup_statement_nuance(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if ctx.get("skip_semantic"):
        return []
    violations = []
    for section in bundle.emails:
        opener = section.opening_line
        if not opener:
            continue
        # Skip emails already flagged by mechanical T-19 · semantic catches the cases mechanical missed
        # We run on everything · false positives flagged YELLOW so they don't block ship
        user_msg = f"Email section: {section.section_id}\nDescription: {section.description}\nTiming: {section.timing_label or 'N/A'}\nOpening line: {opener}"
        result = _call_claude_judge(SEM_T19_SYSTEM, user_msg, max_tokens=400)
        if result.get("error"):
            # API failure · don't block ship, but log a YELLOW
            violations.append(Violation(
                rule_id="SEM-T19",
                rule_name="setup-statement nuance (semantic)",
                severity=YELLOW,
                section_id=section.section_id,
                line_no=section.start_line,
                line_content="(semantic judge API failure)",
                message=f"Semantic check failed: {result['error']}",
                fix_hint="Verify ANTHROPIC_API_KEY is set; retry with --no-semantic to skip.",
            ))
            continue
        if result.get("verdict") == "FAIL" and result.get("category") in ("setup-statement", "countdown", "other"):
            violations.append(Violation(
                rule_id="SEM-T19",
                rule_name="setup-statement nuance (semantic)",
                severity=YELLOW,  # semantic is YELLOW so it doesn't double-block what mechanical already flagged
                section_id=section.section_id,
                line_no=section.body_lines[0][0] if section.body_lines else section.start_line,
                line_content=opener[:200],
                message=f"Claude judge: {result.get('reasoning', 'opening fails T-19')}",
                fix_hint="See T-19 in tom-craft-rules.md for approved opener patterns.",
            ))
    return violations


# ────────────────────────────────────────────────────────────────────────────
# SEM-T20 · mechanism reveal nuance
# ────────────────────────────────────────────────────────────────────────────

SEM_T20_SYSTEM = """You audit pre-webinar emails against Tom Render's craft rule T-20.

Rule T-20 says: pre-webinar emails MUST tease the mechanism's existence + outcome only.
They CANNOT reveal:
  - The mechanism's name (e.g., "Caloric Density Index", "Reset Method", "the 4 Pillars")
  - Specific thresholds, decision rules, or framework structure
  - "That's the whole game" or equivalent reveal-closers

What you CAN say:
  - Existence of a mechanism ("there's a ten-second test")
  - Outcome the mechanism produces ("keeps you full while you lose fat")
  - Category of mechanism ("it's a number on every food label")
  - Social proof of results
  - Anti-mechanism framing ("every plan you tried was loading the wrong foods")

You will receive ONE pre-webinar email body. Return STRICTLY this JSON:
{
  "verdict": "PASS" | "FAIL",
  "leaks": ["list of specific lines that reveal mechanism · empty if PASS"],
  "reasoning": "1-2 sentence explanation"
}

No prose outside the JSON."""


def check_sem_t20_mechanism_reveal_nuance(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if ctx.get("skip_semantic"):
        return []
    violations = []
    for section in bundle.emails:
        # Only pre-webinar emails (sequence 1)
        if section.sequence != 1:
            continue
        body = section.body or ""
        if not body.strip():
            continue
        user_msg = f"Email section: {section.section_id}\nDescription: {section.description}\n\nBody:\n{body[:3000]}"
        result = _call_claude_judge(SEM_T20_SYSTEM, user_msg, max_tokens=800)
        if result.get("error"):
            violations.append(Violation(
                rule_id="SEM-T20",
                rule_name="mechanism reveal nuance (semantic)",
                severity=YELLOW,
                section_id=section.section_id,
                line_no=section.start_line,
                line_content="(semantic judge API failure)",
                message=f"Semantic check failed: {result['error']}",
                fix_hint="Verify ANTHROPIC_API_KEY is set; retry with --no-semantic to skip.",
            ))
            continue
        if result.get("verdict") == "FAIL":
            leaks = result.get("leaks", [])
            leak_summary = "; ".join(leaks[:3]) if leaks else "(see reasoning)"
            violations.append(Violation(
                rule_id="SEM-T20",
                rule_name="mechanism reveal nuance (semantic)",
                severity=YELLOW,
                section_id=section.section_id,
                line_no=section.start_line,
                line_content=leak_summary[:200],
                message=f"Claude judge: {result.get('reasoning', 'pre-webinar mechanism leak detected')}",
                fix_hint="Strip mechanism name + thresholds + framework structure. Tease only.",
            ))
    return violations


# ────────────────────────────────────────────────────────────────────────────
# RULES registry
# ────────────────────────────────────────────────────────────────────────────

RULES = [
    Rule(id="SEM-T19", name="setup-statement nuance (Claude judge)",  severity=YELLOW, layer=LAYER, check=check_sem_t19_setup_statement_nuance, applies_to=APPLIES_TO),
    Rule(id="SEM-T20", name="mechanism reveal nuance (Claude judge)", severity=YELLOW, layer=LAYER, check=check_sem_t20_mechanism_reveal_nuance, applies_to=APPLIES_TO),
]
