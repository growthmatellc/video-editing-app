"""voice.py — parse the voice sections of clients/<slug>/style-guide.md.

Every client style guide carries an authored `## Off-brand phrases` list, a `## Don'ts`
list and an `## On-brand phrases` library. Until 2026-07-16 nothing could read them:
`lib/per_client.py::_extract_banned_phrases` grepped for `## Banned phrases`, a heading
that appears in zero of the 22 style guides, so PC-1 (a HARD rule) loaded an empty list
and passed every client silently.

Fixing the heading alone would have been worse than the bug. These sections are not lists
of literal strings — they are three different kinds of content mixed together:

  1. LITERAL phrases, quoted     · `"crush it," "hustle," "grind"`      → matchable
  2. PROSE categories            · `Passive voice`, `Fear-only language` → NOT matchable;
                                    only a judge can see these. Literal-matching them
                                    fires never, which reads as "clean."
  3. RETRACTED rules             · `~~"leverage"~~ — CORRECTED: not off-brand`
                                    → must NEVER fire. rachel-woods retracted exactly this
                                    after a video sweep proved she says it herself; a naive
                                    parser resurrects the false rule the guide killed.

So this module sorts them, and the caller routes each kind to the check that can actually
see it: literals to PC-1, prose to SEM-VR, retractions to nothing at all.

See skills/tone-of-voice/SKILL.md for the enforcement contract this feeds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# Heading → bucket. Matched case-insensitively, allowing any parenthetical/dash suffix
# ("## Off-brand phrases (must-avoid from TAB Section 11.6)", "## Don'ts (DRAFT)").
OFF_BRAND_HEADINGS = [
    r"Off-?brand\s+phrases",
    r"Don[''`]?ts",
    r"Banned\s+phrases",      # not used by any live guide · kept so a future guide can
    r"Banned\s+patterns",     # use the obvious name without silently going unread
    r"Banned\s+words",
    r"Do\s+NOT\s+use",
]

ON_BRAND_HEADINGS = [
    r"On-?brand\s+phrases",
]

# A bullet carrying any of these is a rule the guide has TAKEN BACK. It must not fire.
# Strikethrough is the repo-wide convention for this (erinne resolved-gates, jake's
# RESOLVED count lock, rachel's "leverage" correction); the word markers catch guides
# that retracted in prose without striking the text.
RETRACTION_MARKERS = [
    r"~~",
    r"\bCORRECTED\b",
    r"\bRESOLVED\b",
    r"\bnot\s+off-?brand\b",
    r"\btreat\s+as\s+unverified\b",
    r"\bno\s+independent\s+evidence\b",
]

_BULLET = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(.*)$")
# Double quotes + smart quotes only. Single quotes are unusable here: apostrophes in
# "Don'ts" and "she doesn't" would open phantom quotes on half the corpus.
_QUOTED = re.compile(r'"([^"]{2,120})"|“([^”]{2,120})”')


@dataclass
class VoiceRules:
    """What a client's style guide actually says about voice, sorted by enforceability."""

    slug: str
    style_guide_present: bool = False
    # Quoted literal phrases. Safe for word-boundary matching. → PC-1
    banned_literals: List[str] = field(default_factory=list)
    # Prose categories ("Passive voice"). Only a judge can see these. → SEM-VR
    voice_prohibitions: List[str] = field(default_factory=list)
    # The must-use library. Advisory context. → SEM-VR
    on_brand_phrases: List[str] = field(default_factory=list)
    # Rules the guide retracted. Recorded so we can PROVE we didn't fire them.
    retracted: List[str] = field(default_factory=list)
    # Which voice headings were found at all. Empty + present guide → PC-0 fires.
    sections_found: List[str] = field(default_factory=list)

    @property
    def parseable(self) -> bool:
        """True if we found any voice section to read.

        False on a non-empty style guide means the guide drifted off-schema and every
        voice rule is about to no-op. That is PC-0's trigger, not a pass.
        """
        return bool(self.sections_found)


def _section_body(style_guide: str, heading_pattern: str) -> Optional[tuple]:
    """Return (matched_heading, body_text) for an H2 whose title matches, else None."""
    pat = re.compile(
        r"^##\s+(" + heading_pattern + r")[^\n]*\n(.*?)(?=^##\s|\Z)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    m = pat.search(style_guide)
    if not m:
        return None
    return (m.group(1).strip(), m.group(2))


def _is_retracted(line: str) -> bool:
    return any(re.search(p, line, re.IGNORECASE) for p in RETRACTION_MARKERS)


def _extract_quoted(line: str) -> List[str]:
    """Pull quoted literals out of a bullet, stripping markdown and trailing punctuation.

    `Bro-fitness buzzwords: "crush it," "hustle," "grind"` → ["crush it", "hustle", "grind"]

    The trailing-comma-inside-the-quote style is common in the corpus, so `"crush it,"`
    must yield `crush it` — otherwise the literal never matches real copy.
    """
    out = []
    for m in _QUOTED.finditer(line):
        raw = m.group(1) or m.group(2) or ""
        cleaned = raw.strip().strip("*_`").strip()
        cleaned = cleaned.rstrip(",.;:!?").strip()
        if len(cleaned) >= 3:
            out.append(cleaned)
    return out


def _enumerated_literals(line: str) -> List[str]:
    """Quoted terms from a bullet, but ONLY when the bullet enumerates them.

    A quoted string inside an off-brand bullet is one of two opposite things, and they
    look identical:

      ENUMERATION (2+ quotes) · the bullet IS a list of banned terms
        `Bro-fitness buzzwords: "crush it," "hustle," "grind," "beast mode"`
        `Hype register generally: "revolutionary", "unlock", "supercharge"`
        → ban each.

      ILLUSTRATION (1 quote) · the bullet is a prose rule that cites an example, the
      founder's own words, or even the OPPOSITE of a ban
        `Never use passive or distant language — always direct, always "you."`
            ← erinne PRESCRIBES "you". Banning it flags every line of copy she has.
        `Deep technical/engineering register. "This is not a technical role."`
            ← rachel's own words, quoted as the evidence FOR the rule.
        `Erinne's message is "anyone can do this with the right system."`
            ← an on-brand quote living inside a Don't.
        → do not ban. The prose goes to SEM-VR, which can read what the quote is doing.

    So: enumerate → literal; illustrate → judge. Both real false positives this guard
    catches (erinne's "you", rachel's "This is not a technical role") were found by
    running the parser over all 22 live guides, not by reasoning about the schema.
    """
    quoted = _extract_quoted(line)
    if len(quoted) < 2:
        return []
    return [q for q in quoted if q.lower() not in _NEVER_LITERAL]


# Words that are never a bannable literal even inside an enumeration. A style guide that
# appears to ban a pronoun or article has been misparsed; firing HARD on "you" would
# flag every line of copy in the repo.
_NEVER_LITERAL = {
    "you", "your", "we", "our", "us", "i", "me", "my",
    "the", "and", "but", "for", "not", "it", "is", "are", "was", "this", "that",
}


def _strip_markdown(text: str) -> str:
    text = re.sub(r"[*_`~]+", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # links → label
    return re.sub(r"\s+", " ", text).strip()


def parse_voice_rules(slug: str, style_guide_text: str) -> VoiceRules:
    """Sort a style guide's voice sections into literals / prose / retractions."""
    rules = VoiceRules(slug=slug)
    if not style_guide_text or not style_guide_text.strip():
        return rules
    rules.style_guide_present = True

    for pattern in OFF_BRAND_HEADINGS:
        found = _section_body(style_guide_text, pattern)
        if not found:
            continue
        heading, body = found
        rules.sections_found.append(heading)
        for line in body.splitlines():
            bullet = _BULLET.match(line)
            if not bullet:
                continue
            content = bullet.group(1).strip()
            if not content:
                continue
            if _is_retracted(content):
                rules.retracted.append(_strip_markdown(content)[:200])
                continue
            rules.banned_literals.extend(_enumerated_literals(content))
            # The prose carries the rule even when it also quotes examples
            # ("Formal/academic language (...)"), so the judge gets every live bullet.
            prose = _strip_markdown(content)
            if prose:
                rules.voice_prohibitions.append(prose[:300])

    for pattern in ON_BRAND_HEADINGS:
        found = _section_body(style_guide_text, pattern)
        if not found:
            continue
        heading, body = found
        rules.sections_found.append(heading)
        for line in body.splitlines():
            bullet = _BULLET.match(line)
            if not bullet:
                continue
            content = bullet.group(1).strip()
            if not content or _is_retracted(content):
                continue
            rules.on_brand_phrases.extend(_extract_quoted(content))

    rules.banned_literals = _dedupe(rules.banned_literals)
    rules.on_brand_phrases = _dedupe(rules.on_brand_phrases)
    rules.voice_prohibitions = _dedupe(rules.voice_prohibitions)
    return rules


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for i in items:
        k = i.lower()
        if k not in seen:
            seen.add(k)
            out.append(i)
    return out


def matches_literal(phrase: str, content: str) -> bool:
    """Word-boundary match a banned literal against a line of copy.

    Word-boundary, not substring: the corpus bans short words ("hack", "grind", "unlock")
    and a substring match flags "shack" and "hacked" as violations. term-mappings entries
    already declare `word_boundary: true`, so this is the house intent, just enforced.
    """
    if not phrase or len(phrase) < 3:
        return False
    return re.search(r"\b" + re.escape(phrase) + r"\b", content, re.IGNORECASE) is not None
