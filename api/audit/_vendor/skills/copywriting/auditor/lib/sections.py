"""sections.py — generic markdown section splitting + checks shared across rule modules.

The email bundle parser (`parser.py`) understands `**EMAIL #N**` / `**SMS #N**` headers.
Every other asset — funnel pages, sales pages, decks, ad batches — is organised by plain
markdown headers instead. This module gives those rule modules a common way to carve a
document into sections, plus the handful of checks that repeat across every asset type
(em dashes, British spellings, asterisk bullets).

One copy of each shared check, so a fix lands everywhere at once.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple


HEADER_RE = re.compile(r"^(#{1,6})\s+(?P<title>.+?)\s*$")


@dataclass
class Section:
    """A markdown section: its header, and every line beneath it."""

    key: str                       # classifier output, e.g. "registration"
    heading: str                   # the header text
    level: int                     # 1 for #, 2 for ##, ...
    start_line: int                # 1-indexed
    end_line: int = 0
    lines: List[Tuple[int, str]] = field(default_factory=list)  # (line_no, content)

    @property
    def section_id(self) -> str:
        return self.heading

    @property
    def body(self) -> str:
        return "\n".join(c for _, c in self.lines)

    def prose_lines(self) -> List[Tuple[int, str]]:
        """Non-blank, non-header lines."""
        return [(n, c) for n, c in self.lines if c.strip() and not HEADER_RE.match(c)]

    def word_count(self) -> int:
        return len(self.body.split())


def split_sections(raw_lines: List[str], classifier: Callable[[str], Optional[str]]) -> List[Section]:
    """Carve a document into sections by markdown header.

    `classifier` maps a header title to a section key, or None to ignore that header.
    A section runs from its header to the next header at the same or a higher level, so
    sub-headers nest inside their parent rather than opening a section of their own.
    """
    sections: List[Section] = []
    current: Optional[Section] = None

    for idx, line in enumerate(raw_lines):
        line_no = idx + 1
        m = HEADER_RE.match(line)
        if m:
            level = len(m.group(1))
            if current and level <= current.level:
                current.end_line = line_no - 1
                current = None
            if current is None:
                key = classifier(m.group("title"))
                if key:
                    current = Section(key=key, heading=m.group("title").strip(), level=level, start_line=line_no)
                    sections.append(current)
                    continue
        if current is not None:
            current.lines.append((line_no, line))
            current.end_line = line_no

    return sections


def all_headers(raw_lines: List[str]) -> List[Tuple[int, int, str]]:
    """Every markdown header: (line_no, level, title)."""
    out = []
    for idx, line in enumerate(raw_lines):
        m = HEADER_RE.match(line)
        if m:
            out.append((idx + 1, len(m.group(1)), m.group("title").strip()))
    return out


# ---------------------------------------------------------------------------
# Shared craft checks
# ---------------------------------------------------------------------------

# references/craft/anti-ai-tells.md + Alec's "no em dashes" hard rule, repeated in every
# asset module. The auditor bans the character outright — Growth Mate copy uses commas,
# periods, or a rewrite.
EM_DASH_RE = re.compile(r"[—–]|(?<=\w)--(?=\w)")

# Alec: "British English -> US English." The common offenders in fitness/coaching copy.
BRITISH_SPELLINGS = {
    "realise": "realize", "realised": "realized", "realising": "realizing",
    "recognise": "recognize", "recognised": "recognized",
    "organise": "organize", "organised": "organized", "organisation": "organization",
    "prioritise": "prioritize", "prioritised": "prioritized",
    "personalise": "personalize", "personalised": "personalized",
    "optimise": "optimize", "optimised": "optimized",
    "analyse": "analyze", "analysed": "analyzed",
    "behaviour": "behavior", "behaviours": "behaviors",
    "colour": "color", "colours": "colors",
    "favourite": "favorite", "favourites": "favorites",
    "programme": "program", "programmes": "programs",
    "practise": "practice",
    "licence": "license",
    "defence": "defense",
    "fibre": "fiber",
    "litre": "liter", "litres": "liters",
    "metre": "meter", "metres": "meters",
    "travelled": "traveled", "travelling": "traveling",
    "cancelled": "canceled", "cancelling": "canceling",
    "learnt": "learned",
    "whilst": "while",
    "amongst": "among",
}
BRITISH_RE = re.compile(r"\b(" + "|".join(sorted(BRITISH_SPELLINGS, key=len, reverse=True)) + r")\b", re.I)

# Lauren: bullets are "•" or "-", never "*". Asterisk bullets are a markdown/AI tell.
ASTERISK_BULLET_RE = re.compile(r"^\s*\*\s+\S")

BULLET_RE = re.compile(r"^\s*[-•*•]\s+\S|^\s*\d+[.)]\s+\S")


def is_bullet(line: str) -> bool:
    return bool(BULLET_RE.match(line))


def count_bullets(lines: List[Tuple[int, str]]) -> int:
    return sum(1 for _, c in lines if is_bullet(c))


def count_sentences(text: str) -> int:
    """Rough sentence count — terminal punctuation followed by space or end."""
    stripped = text.strip()
    if not stripped:
        return 0
    return len(re.findall(r"[.!?](?:\s|$)", stripped))


def strip_markdown(text: str) -> str:
    """Drop bold/italic markers so word counts and phrase scans see the prose."""
    return re.sub(r"[*_`#>]", "", text)


# `·`, `•`, `|` separate list items on a slide. They are punctuation, not words, and counting
# them inflates a word count by roughly the number of items — enough to push a compliant slide
# over a cap. (Trent's slide 17 counted 58 "words"; 12 of them were middots. It was always
# under the 50-word cap.)
SEPARATOR_TOKENS = {"·", "•", "|", "-", "–", "—", "/"}


def word_count(text: str) -> int:
    """Words a human would count: markdown stripped, separator glyphs excluded."""
    return sum(1 for t in strip_markdown(text).split() if t not in SEPARATOR_TOKENS)


# `- **Step 2: Add to Calendar** — "Life happens…"` — the dash after a bold block label is the
# document's own delimiter, not prose. Scanning it as copy reported an em-dash violation on every
# labelled line in the spec docs we actually write. Strip the label and its delimiter first, then
# scan what's left; an em dash later in the same line still gets caught.
BLOCK_LABEL_PREFIX_RE = re.compile(r"^\s*(?:[-•*]\s+|\d+[.)]\s+)?\*\*[^*]+\*\*\s*[—–:-]?\s*")


def copy_text(line: str) -> str:
    """The part of a line that is published COPY, with the doc's own scaffolding removed."""
    return BLOCK_LABEL_PREFIX_RE.sub("", line)


# ---------------------------------------------------------------------------
# Subject lines
# ---------------------------------------------------------------------------

# Every email ships 2-3 subject line options for the operator to pick from. The canonical form
# pairs each subject with its own preview, a blank line between the groups (PH-6):
#
#   **EMAIL #1: CONFIRMATION (Immediate)**
#
#   **Subject A:** Off her BP meds in 90 days
#   **Preview A:** She'd been told her thyroid made this permanent.
#
#   **Subject B:** Her doctor told her it was impossible
#   **Preview B:** 12 weeks later the labs came back clean.
#
# A bare `**Subject:**` is still parsed (that's what the back catalogue uses), so old bundles
# still audit — they just fail the 2-3 variant rule, which is the point.
SUBJECT_VARIANT_RE = re.compile(
    r"^\s*\**\s*(?:alt(?:ernate)?\s+)?subject(?:\s*(?:line)?\s*[A-Z0-9])?\s*\**\s*:\s*\**\s*"
    r"(?P<text>.+?)\s*\**\s*$",
    re.I,
)


SUBJECT_LABEL_RE = re.compile(r"^\s*\**\s*(?:alt(?:ernate)?\s+)?subject(?:\s*(?:line)?\s*(?P<label>[A-Z0-9]))?", re.I)

# Each subject gets its OWN preview text. Subject and preview are a two-part pitch — the subject
# hooks, the preview pays it off — so a preview written for subject A rarely lands under subject C.
PREVIEW_VARIANT_RE = re.compile(
    r"^\s*\**\s*(?:preview(?:\s*text)?|pre-?header)(?:\s+(?P<label>[A-Z0-9]))?\s*\**\s*:\s*\**\s*"
    r"(?P<text>.*?)\s*\**\s*$",
    re.I,
)


def subject_variants(section) -> List[Tuple[int, str]]:
    """Every subject line offered for one email. -> [(line_no, text)]

    The parser lifts the FIRST subject onto `section.subject` and leaves any further ones in the
    body, so both have to be collected to see the full set.
    """
    out: List[Tuple[int, str]] = []
    if getattr(section, "subject", None):
        out.append((section.start_line, section.subject.strip()))
    for line_no, content in getattr(section, "body_lines", []):
        m = SUBJECT_VARIANT_RE.match(content)
        if m:
            text = m.group("text").strip()
            if text and text not in [t for _, t in out]:
                out.append((line_no, text))
    return out


def preview_variants(section) -> List[Tuple[int, Optional[str], str]]:
    """Every preview text offered for one email. -> [(line_no, label, text)]"""
    out = []
    for line_no, content in getattr(section, "body_lines", []):
        m = PREVIEW_VARIANT_RE.match(content)
        if m and m.group("text").strip():
            out.append((line_no, (m.group("label") or "").upper() or None, m.group("text").strip()))
    return out


# ---------------------------------------------------------------------------
# Captures
# ---------------------------------------------------------------------------

CAPTURE_FRONTMATTER_RE = re.compile(r"^captured(_by)?\s*:", re.I | re.M)


def is_capture(raw_lines: List[str]) -> bool:
    """Is this document a verbatim CAPTURE of something that already shipped?

    Jane's library anchor was read live out of the client's Google Slides; it is the deck that
    produced $79K at 19.75x ROAS. It is EVIDENCE, not a deliverable.

    Craft rules must not be applied to a capture. "Fixing" its em dashes would make the anchor
    a lie about what was actually on the slide, and the entire value of an anchor is that it
    records what worked. Structure is still checked; the prose is left alone.
    """
    return bool(CAPTURE_FRONTMATTER_RE.search("\n".join(raw_lines[:25])))
