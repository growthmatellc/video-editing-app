"""webinar_deck.py — WD-1 to WD-9 · webinar deck slide checks.

Decks aren't email bundles, so this module parses slides itself. The canonical slide
shape (from the Lauren-PASS Erinne anchor, clients/erinne-full-circle/outputs/webinar-decks/
2026-06-02_test-w1_v2.md):

    **SLIDE 7 — PROOF** ⟢ ENGAGEMENT CUE 3

    Headline: ...
    Bullets:
    • ...

    SCRIPT:
    ...

    DESIGN BRIEF:
    Layout: ...
    Photo type: Founder — ...

Sources (citation on each check):
  skills/copywriting/references/tom-craft-rules.md        T-1 to T-7 deck grounding
  skills/copywriting/references/alec-qc-checklists.md     Slides section + Stage E fail conditions
  skills/webinar-presentation-copy/01-agent-specification.md  §8 Slide Rules table (the numbers:
                                                          50 words, ~150-word script, min 4 case
                                                          studies, no consecutive founder images)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple

from skills.copywriting.auditor.lib.parser import ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation
from skills.copywriting.auditor.lib import sections as S


LAYER = "WebinarDeck"
APPLIES_TO = {"webinar_deck"}


# Two slide formats are in the wild, and both are legitimate:
#
#   SCRIPTED (the Erinne Lauren-PASS anchor) — copywriter-facing, carries the presenter script:
#       **SLIDE 7 — PROOF** ⟢ ENGAGEMENT CUE 3
#       Headline: ...
#       SCRIPT: ...
#       DESIGN BRIEF: ...
#
#   COMPRESSED (Trent's deck v2) — designer-facing, one line per slide, no script by design:
#       **S11 CASE STUDY MARY** — Mary. Lost 60 lbs. ... DESIGN: Mary before/after full slide.
#
# The three-layer rule (WD-1) only applies to the scripted format — demanding a SCRIPT block
# from a designer-facing doc would be inventing a rule the deck was never meant to satisfy.
# A deck inserts a slide as 61A / 61B rather than renumbering everything after it. A purely
# numeric pattern silently swallowed such a slide into its predecessor, and the predecessor then
# failed the word cap carrying content that was never on it.
SLIDE_HEADER_RE = re.compile(
    r"^\*\*SLIDE\s+(?P<number>\d+)(?P<suffix>[A-Z]?)\s*[—–-]\s*(?P<tag>[^*]+)\*\*(?P<rest>.*)$", re.I
)
COMPRESSED_SLIDE_RE = re.compile(
    r"^\*\*S(?P<number>\d+)\s+(?P<tag>[^*]+?)\*\*\s*[—–-]?\s*(?P<content>.*)$", re.I
)
DESIGN_INLINE_RE = re.compile(r"\bDESIGN:\s*(?P<text>.+?)$", re.I)
ENGAGEMENT_CUE_RE = re.compile(r"ENGAGEMENT\s+CUE", re.I)
HEADLINE_RE = re.compile(r"^Headline:\s*(?P<text>.+)$", re.I)
SUBHEAD_RE = re.compile(r"^Sub[-\s]?headline:\s*(?P<text>.+)$", re.I)
# The captured-deck format writes the subtitle as a `- Sub: "…"` bullet under the title slide.
CAPTURED_SUB_RE = re.compile(r"^[-•*]?\s*Sub(?:head(?:line)?)?:\s*(?P<text>.+)$", re.I)
BULLETS_RE = re.compile(r"^Bullets:\s*$", re.I)
SCRIPT_RE = re.compile(r"^SCRIPT:\s*$", re.I)
DESIGN_BRIEF_RE = re.compile(r"^DESIGN BRIEF:\s*$", re.I)
PHOTO_TYPE_RE = re.compile(r"^Photo type:\s*(?P<text>.+)$", re.I)

# Slide craft numbers. Grounding + severity rationale: references/craft/webinar-and-video-structure-rules.md
MAX_HEADLINE_WORDS = 15    # WD-2 · YELLOW legibility flag (Ogilvy's data opposes a short-headline cap)
MAX_ON_SLIDE_WORDS = 50    # WD-3 · HARD · Duarte glance test (~50 warn zone, >75 = a document on a slide)
TARGET_SCRIPT_WORDS = 150  # WD-4 · YELLOW · ~150 wpm conversational (NCVS)
MIN_CASE_STUDIES = 3       # WD-5 · HARD · one proof moment per Perfect-Webinar "Secret" (Brunson)
ENGAGEMENT_CUE_BAND = (6, 8)  # WD-6 · YELLOW floor · aim for >=6; the convention runs denser, not sparser


@dataclass
class Slide:
    number: int
    tag: str
    start_line: int
    end_line: int = 0
    headline: str = ""
    headline_line: int = 0
    subhead: str = ""       # the Sub-headline: line, when the slide carries one
    subhead_line: int = 0
    scripted: bool = True   # False for the compressed designer-facing format
    captured: bool = False  # True for a verbatim capture of a live deck (library anchors)
    bullets: List[Tuple[int, str]] = field(default_factory=list)
    script: List[Tuple[int, str]] = field(default_factory=list)
    design: List[Tuple[int, str]] = field(default_factory=list)
    has_engagement_cue: bool = False
    lines: List[Tuple[int, str]] = field(default_factory=list)

    @property
    def section_id(self) -> str:
        return f"Slide {self.number} ({self.tag.strip()})"

    def copy_lines(self) -> List[Tuple[int, str]]:
        """Audience-facing COPY only: headline, bullets, script.

        Excludes the DESIGN BRIEF. That block is an instruction to the designer, and its
        `Photo type: Founder — Erinne on the beach` form uses the dash as a label separator,
        not as prose. Scanning it flagged 48 em-dash "violations" in Erinne's anchor that no
        viewer will ever see.
        """
        design = {n for n, _ in self.design}
        return [(n, c) for n, c in self.scan_lines() if n not in design]

    def scan_lines(self) -> List[Tuple[int, str]]:
        """The lines that are actual COPY, for craft checks.

        Excludes the format's own scaffolding. This matters on the compressed format, where
        the slide header is `**S1 TITLE** — content`: that dash is the delimiter, not prose,
        and scanning the raw line would flag an em-dash violation on every single slide.
        """
        if self.scripted:
            return list(self.lines)
        out = []
        if self.headline:
            out.append((self.headline_line, self.headline))
        out.extend(self.design)
        return out

    @property
    def photo_type(self) -> str:
        for _, c in self.design:
            m = PHOTO_TYPE_RE.match(c.strip())
            if m:
                return m.group("text").strip()
        return ""

    def on_slide_words(self) -> int:
        text = self.headline + " " + " ".join(c for _, c in self.bullets)
        return S.word_count(text)

    def script_words(self) -> int:
        return S.word_count(" ".join(c for _, c in self.script))


HEADING_SLIDE_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$")

# Headings in a captured deck that are commentary about the deck, not slides in it.
NOT_A_SLIDE_RE = re.compile(
    r"^(?:qc\s+report|session\s+debrief|handoff|hand-off|notes?|sources?|changelog|"
    r"photo\s+brief|agent\s+handoff|appendix|metadata|what\s+this\s+is)", re.I
)


def _captured_slides(bundle: ParsedBundle) -> List[Slide]:
    """The third format: a verbatim CAPTURE of a live deck.

        ## Title slide
        **The Metabolic Alignment Workshop**
        - Sub: "Learn the System that will help you lose weight…"

    Used by the golden-egg library anchors (Jane, Rachel). A capture is on-slide copy only —
    it has no SCRIPT and no DESIGN BRIEF, because the live deck it was read from didn't carry
    them in the doc. So WD-1 (three layers) and WD-7 (photo rules) do not apply to it, and
    saying they do would be inventing a contract the anchor never had.
    """
    slides: List[Slide] = []
    current: Slide = None
    n = 0
    for idx, line in enumerate(bundle.raw_lines):
        line_no = idx + 1
        m = HEADING_SLIDE_RE.match(line.strip())
        if m:
            title = m.group("title")
            if current:
                current.end_line = line_no - 1
            current = None
            if NOT_A_SLIDE_RE.match(title):
                continue
            n += 1
            current = Slide(
                number=n, tag=title, start_line=line_no, scripted=False, captured=True,
                headline=title, headline_line=line_no,
                has_engagement_cue=bool(re.search(r"engagement|chat check|1-10|poll", title, re.I)),
            )
            slides.append(current)
            continue
        if current is None or not line.strip():
            continue
        stripped = line.strip()
        sub_m = CAPTURED_SUB_RE.match(stripped)
        if sub_m and not current.subhead:
            current.subhead = sub_m.group("text").strip().strip('"').strip()
            current.subhead_line = line_no
        current.bullets.append((line_no, stripped))
        current.lines.append((line_no, line))
        current.end_line = line_no
    return slides



# A CAPTURE is a verbatim record of a deck that already ran — Jane's anchor was read live out of
# the client's Google Slides and is the deck that produced $79K at 19.75x ROAS. It is evidence,
# not a deliverable.
#
# Craft rules must NOT be applied to it. Rewriting a capture so it satisfies our em-dash rule
# would make the anchor a lie about what was actually on the slide, and the whole point of an
# anchor is that it records what worked. Structure is still checked; the prose is left alone.
def _is_capture(bundle: ParsedBundle) -> bool:
    return S.is_capture(bundle.raw_lines)


def _slides(bundle: ParsedBundle) -> List[Slide]:
    slides: List[Slide] = []
    current: Slide = None
    mode = None

    for idx, line in enumerate(bundle.raw_lines):
        line_no = idx + 1
        stripped_line = line.strip()

        m = SLIDE_HEADER_RE.match(stripped_line)
        if m:
            if current:
                current.end_line = line_no - 1
            suffix = m.group("suffix") or ""
            current = Slide(
                number=int(m.group("number")),
                tag=f"{suffix} {m.group('tag')}".strip() if suffix else m.group("tag"),
                start_line=line_no,
                scripted=True,
                has_engagement_cue=bool(ENGAGEMENT_CUE_RE.search(m.group("rest") or "")),
            )
            slides.append(current)
            mode = None
            continue

        # Compressed designer-facing slide — the whole slide is one line.
        cm = COMPRESSED_SLIDE_RE.match(stripped_line)
        if cm:
            if current:
                current.end_line = line_no - 1
            content = cm.group("content") or ""
            design_m = DESIGN_INLINE_RE.search(content)
            on_slide = content[: design_m.start()] if design_m else content
            current = Slide(
                number=int(cm.group("number")),
                tag=cm.group("tag"),
                start_line=line_no,
                end_line=line_no,
                scripted=False,
                headline=on_slide.strip(),
                headline_line=line_no,
                has_engagement_cue=bool(re.search(r"\bcue\s*\d", stripped_line, re.I)),
            )
            if design_m:
                current.design = [(line_no, design_m.group("text").strip())]
            current.lines = [(line_no, line)]
            slides.append(current)
            mode = None
            continue

        # A slide ends at the next slide OR at the next document heading. Without the heading
        # guard the LAST slide swallows everything after it — the QC report, the session debrief,
        # the handoff notes — and their content gets audited as if it were on the slide. Erinne's
        # deck was flagged for the British spelling "metres", which appears only inside its own QC
        # table, in a line saying not to use British spellings.
        if current is not None and S.HEADER_RE.match(stripped_line):
            current.end_line = line_no - 1
            current = None
            continue

        if current is None:
            continue
        if not current.scripted:
            # Compressed designer slide, MULTI-LINE form (for readability): the on-slide copy, an
            # optional `Sub:` line, and the `DESIGN:` line each sit on their own line under the
            # `**S# TAG**` header, one slide per block separated by a blank line. The old
            # all-on-one-line form still parses (it just has no continuation lines) — this only
            # folds in whatever follows the header up to the next slide/heading.
            if not stripped_line:
                continue
            design_m = DESIGN_INLINE_RE.search(stripped_line)
            if design_m:
                current.design.append((line_no, design_m.group("text").strip()))
            else:
                sub_m = CAPTURED_SUB_RE.match(stripped_line)
                if sub_m and not current.subhead:
                    current.subhead = sub_m.group("text").strip().strip('"').strip()
                    current.subhead_line = line_no
                elif not current.headline:
                    current.headline = stripped_line
                    current.headline_line = line_no
                else:
                    current.headline = f"{current.headline} {stripped_line}".strip()
            current.lines.append((line_no, line))
            current.end_line = line_no
            if ENGAGEMENT_CUE_RE.search(stripped_line) or re.search(r"\bcue\s*\d", stripped_line, re.I):
                current.has_engagement_cue = True
            continue

        current.lines.append((line_no, line))
        current.end_line = line_no
        stripped = line.strip()

        if ENGAGEMENT_CUE_RE.search(stripped):
            current.has_engagement_cue = True

        hm = HEADLINE_RE.match(stripped)
        if hm:
            current.headline = hm.group("text").strip()
            current.headline_line = line_no
            mode = None
            continue
        sm = SUBHEAD_RE.match(stripped)
        if sm:
            current.subhead = sm.group("text").strip()
            current.subhead_line = line_no
            mode = None
            continue
        if BULLETS_RE.match(stripped):
            mode = "bullets"
            continue
        if SCRIPT_RE.match(stripped):
            mode = "script"
            continue
        if DESIGN_BRIEF_RE.match(stripped):
            mode = "design"
            continue
        if not stripped:
            continue

        if mode == "bullets":
            current.bullets.append((line_no, stripped))
        elif mode == "script":
            current.script.append((line_no, stripped))
        elif mode == "design":
            current.design.append((line_no, stripped))

    if not slides:
        # No slide markers at all — this may be a verbatim capture of a live deck.
        slides = _captured_slides(bundle)

    return slides


def _v(rule_id, rule_name, severity, section_id, line_no, line, message, fix) -> Violation:
    return Violation(
        rule_id=rule_id, rule_name=rule_name, severity=severity,
        section_id=section_id, line_no=line_no, line_content=line, message=message, fix_hint=fix,
    )


# ---------------------------------------------------------------------------
# WD-0 · the deck actually parses
#
# THE most important rule in this module. If the parser recognises no slides, every other
# rule passes on an empty list and the auditor prints "ship clear" for a file it never read.
# A QC gate that blesses what it can't parse is worse than no gate — it manufactures false
# confidence. So: zero slides is a HARD failure, never a silent pass.
#
# (Caught for real on 2026-07-13: Trent's deck v2 uses the compressed slide format, the
# parser only knew the scripted one, and the deck sailed through all 9 rules with 0 slides
# parsed.)
# ---------------------------------------------------------------------------


def check_wd0_parseable(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    slides = _slides(bundle)
    if slides:
        if _is_capture(bundle):
            # Say so out loud. Silently passing every craft rule on a capture is the same
            # false-confidence failure as passing a deck we could not parse.
            return [_v(
                "WD-0", "deck parses", YELLOW, "document", 1,
                f"(verbatim capture · {len(slides)} slides)",
                "This is a verbatim capture of a deck that already ran, not a deliverable we "
                "authored. Craft rules (word caps, em dashes, US English, title rules) are NOT "
                "applied: rewriting a record to satisfy a style rule would make the anchor a lie "
                "about what was on the slide.",
                "Nothing to fix. Audit the deck this anchor is used to WRITE, not the anchor.",
            )]
        return []
    return [_v(
        "WD-0", "deck parses", HARD, "document", 1, "(0 slides parsed)",
        "No slides could be parsed from this deck, so no deck rule was actually evaluated. The "
        "auditor will not pass a file it cannot read. Supported slide headers: `**SLIDE 7 — PROOF**` "
        "(scripted) or `**S7 PROOF** — ...` (compressed).",
        "Fix the slide headers to a supported format, or extend the parser if this is a new one.",
    )]


# ---------------------------------------------------------------------------
# WD-1 · three-layer slide format
#   Every scripted slide carries on-slide copy + SCRIPT: + DESIGN BRIEF:
#   Compressed designer-facing decks are exempt — they carry no script by design.
# ---------------------------------------------------------------------------


def check_wd1_three_layer_format(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for slide in _slides(bundle):
        if not slide.scripted:
            continue  # designer-facing deck or capture — a SCRIPT block was never in the contract
        missing = []
        if not slide.headline:
            missing.append("Headline")
        if not slide.script:
            missing.append("SCRIPT")
        if not slide.design:
            missing.append("DESIGN BRIEF")
        if missing:
            violations.append(_v(
                "WD-1", "three-layer slide format", HARD, slide.section_id, slide.start_line,
                f"(missing: {', '.join(missing)})",
                f"Slide {slide.number} is missing {', '.join(missing)}. Every slide carries three "
                f"layers: on-slide copy, SCRIPT, and DESIGN BRIEF. The design and photo agents "
                f"downstream can't work without all three.",
                f"Add the {', '.join(missing)} layer(s).",
            ))
    return violations


# ---------------------------------------------------------------------------
# WD-2 · headline max 15 words
# ---------------------------------------------------------------------------


def check_wd2_headline_length(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if _is_capture(bundle):
        return []  # a capture records what shipped; we do not rewrite the record
    violations = []
    for slide in _slides(bundle):
        # Only the scripted format has a discrete `Headline:` field. On a compressed slide
        # the whole on-slide copy lives in one line, and WD-3 is the rule that governs it.
        if not slide.scripted or not slide.headline:
            continue
        words = len(S.strip_markdown(slide.headline).split())
        if words > MAX_HEADLINE_WORDS:
            violations.append(_v(
                "WD-2", "headline · slide legibility (advisory)", YELLOW, slide.section_id,
                slide.headline_line, slide.headline,
                f"Headline is {words} words, over {MAX_HEADLINE_WORDS}. This is a slide-legibility flag "
                f"only — copy canon actually runs against a short-headline cap (Ogilvy: 10+ word "
                f"headlines sold more), so it is never a block, just a glance-test nudge.",
                "Tighten for the glance test if you can; a strong longer headline can stay.",
            ))
    return violations


# ---------------------------------------------------------------------------
# WD-3 · 50 words max of on-slide text
#   Duarte glance test · references/craft/webinar-and-video-structure-rules.md (WD-3)
# ---------------------------------------------------------------------------


def check_wd3_on_slide_words(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if _is_capture(bundle):
        return []  # a capture records what shipped; we do not rewrite the record
    violations = []
    for slide in _slides(bundle):
        words = slide.on_slide_words()
        if words > MAX_ON_SLIDE_WORDS:
            violations.append(_v(
                "WD-3", "on-slide text · max 50 words", HARD, slide.section_id, slide.start_line,
                f"({words} words on slide)",
                f"Slide {slide.number} carries {words} words of on-slide text, over {MAX_ON_SLIDE_WORDS}. "
                f"Duarte's glance test: past ~50 the audience reads the slide instead of listening, and "
                f"over 75 it is a document on a slide, not a slide.",
                "Move the detail into the SCRIPT and leave the slide with the idea.",
            ))
    return violations


# ---------------------------------------------------------------------------
# WD-4 · script ~150 words (one minute of speech)
#   YELLOW — the source says "~150", an approximation, not a cap.
# ---------------------------------------------------------------------------


def check_wd4_script_length(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for slide in _slides(bundle):
        words = slide.script_words()
        if words > TARGET_SCRIPT_WORDS * 1.2:
            violations.append(_v(
                "WD-4", "script · ~150 words", YELLOW, slide.section_id, slide.start_line,
                f"({words} words)",
                f"Slide {slide.number}'s script is {words} words, over the ~{TARGET_SCRIPT_WORDS}-word "
                f"target (about a minute of speech). The source says '~150', so this is a flag rather "
                f"than a block.",
                "Tighten the script, or split the slide.",
            ))
    return violations


# ---------------------------------------------------------------------------
# WD-5 · minimum 4 case studies, interspersed
#   one proof per Perfect-Webinar "Secret" (Brunson) · references/craft/webinar-and-video-structure-rules.md (WD-5)
# ---------------------------------------------------------------------------

CASE_STUDY_RE = re.compile(r"\bcase\s+stud|\btestimonial|\bproof\b|\bresult\b", re.I)


def check_wd5_case_studies(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if _is_capture(bundle):
        return []  # a record of what shipped, not a deliverable
    slides = _slides(bundle)
    if not slides:
        return []
    proof_slides = [s for s in slides if CASE_STUDY_RE.search(s.tag) or CASE_STUDY_RE.search(s.headline)]
    if len(proof_slides) >= MIN_CASE_STUDIES:
        return []
    return [_v(
        "WD-5", "min 3 case studies", HARD, "deck", slides[0].start_line,
        f"({len(proof_slides)} proof slides)",
        f"Deck carries {len(proof_slides)} case-study slides. The minimum is {MIN_CASE_STUDIES} — one "
        f"proof moment per Perfect-Webinar 'Secret' (Brunson) — interspersed rather than stacked.",
        f"Add case-study slides until there are at least {MIN_CASE_STUDIES}, spread through the deck.",
    )]


# ---------------------------------------------------------------------------
# WD-6 · engagement cues — 6 to 8, not clustered
# ---------------------------------------------------------------------------


def check_wd6_engagement_cues(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if _is_capture(bundle):
        return []  # a record of what shipped, not a deliverable
    slides = _slides(bundle)
    if not slides:
        return []
    cued = [s for s in slides if s.has_engagement_cue]
    low, _high = ENGAGEMENT_CUE_BAND
    if len(cued) >= low:
        return []
    return [_v(
        "WD-6", "engagement cues · floor", YELLOW, "deck", slides[0].start_line,
        f"({len(cued)} engagement cues)",
        f"Deck has {len(cued)} engagement cues, under ~{low}. Practitioner convention runs DENSER, not "
        f"sparser (Brunson chains trial closes at roughly one a minute), so only the floor is flagged — "
        f"there is no upper cap.",
        f"Add engagement cues (aim for at least {low}), spread through the deck.",
    )]


# ---------------------------------------------------------------------------
# WD-7 · no consecutive founder images
#   §8 Slide Rules · "no consecutive founder images", "founder foreground only"
# ---------------------------------------------------------------------------

FOUNDER_RE = re.compile(r"\bfounder\b", re.I)
BACKGROUND_RE = re.compile(r"\bbackground\b", re.I)
FOREGROUND_RE = re.compile(r"\bforeground\b", re.I)


# `Photo type: None — clean era slide (avoid back-to-back founder photos).`
# The VALUE is "None". The word "founder" only appears in the guidance note after the dash.
# Matching it anywhere in the line read that slide as a founder photo — a false positive on
# a slide whose entire point was that it has no founder photo.
NO_PHOTO_RE = re.compile(r"^\s*(none|no photo|n/?a|stock|client|graphic|text)\b", re.I)


def check_wd7_founder_images(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    slides = _slides(bundle)
    prev_founder = False
    for slide in slides:
        if slide.captured:
            continue  # a capture carries no design brief — there is nothing to check
        photo = slide.photo_type
        # Only the declared VALUE counts, not a parenthetical warning about founder photos.
        value = re.split(r"[—–(]", photo)[0] if photo else ""
        is_founder = bool(FOUNDER_RE.search(value)) and not NO_PHOTO_RE.match(value.strip())

        if is_founder and prev_founder:
            violations.append(_v(
                "WD-7", "founder image rules", HARD, slide.section_id, slide.start_line, photo,
                f"Slide {slide.number} uses a founder photo, and so does the slide before it. No two "
                f"consecutive founder images — the deck needs visual variety.",
                "Swap one of them for a stock, proof, or graphic slide.",
            ))

        # Founder foreground only, never background.
        for line_no, content in slide.design:
            if FOUNDER_RE.search(content) and BACKGROUND_RE.search(content) and not FOREGROUND_RE.search(content):
                violations.append(_v(
                    "WD-7", "founder image rules", HARD, slide.section_id, line_no, content.strip(),
                    "Founder photo specified as background. The founder is foreground only, never a "
                    "background wash.",
                    "Respecify as foreground.",
                ))
        prev_founder = is_founder
    return violations


# ---------------------------------------------------------------------------
# WD-8 / WD-9 · craft
# ---------------------------------------------------------------------------


def check_wd8_no_em_dashes(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if _is_capture(bundle):
        return []  # a capture records what shipped; we do not rewrite the record
    violations = []
    for slide in _slides(bundle):
        for line_no, content in slide.copy_lines():
            if S.EM_DASH_RE.search(content):
                violations.append(_v(
                    "WD-8", "no em dashes", HARD, slide.section_id, line_no, content.strip(),
                    "Em dash. Growth Mate copy uses a comma, a period, or a rewrite.",
                    "Replace the em dash.",
                ))
    return violations


def check_wd9_us_english(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if _is_capture(bundle):
        return []  # a capture records what shipped; we do not rewrite the record
    violations = []
    for slide in _slides(bundle):
        for line_no, content in slide.copy_lines():
            for m in S.BRITISH_RE.finditer(content):
                word = m.group(0)
                violations.append(_v(
                    "WD-9", "US English", HARD, slide.section_id, line_no, content.strip(),
                    f"British spelling `{word}`. Copy ships in US English.",
                    f"Use `{S.BRITISH_SPELLINGS.get(word.lower(), 'the US spelling')}`.",
                ))
    return violations


RULES = [
    Rule(id="WD-0", name="deck parses",               severity=HARD,   layer=LAYER, check=check_wd0_parseable,          applies_to=APPLIES_TO),
    Rule(id="WD-1", name="three-layer slide format",  severity=HARD,   layer=LAYER, check=check_wd1_three_layer_format, applies_to=APPLIES_TO),
    Rule(id="WD-2", name="headline · slide legibility", severity=YELLOW, layer=LAYER, check=check_wd2_headline_length,    applies_to=APPLIES_TO),
    Rule(id="WD-3", name="on-slide · max 50 words",   severity=HARD,   layer=LAYER, check=check_wd3_on_slide_words,     applies_to=APPLIES_TO),
    Rule(id="WD-4", name="script · ~150 words",       severity=YELLOW, layer=LAYER, check=check_wd4_script_length,      applies_to=APPLIES_TO),
    Rule(id="WD-5", name="min 3 case studies",        severity=HARD,   layer=LAYER, check=check_wd5_case_studies,       applies_to=APPLIES_TO),
    Rule(id="WD-6", name="engagement cues · 6-8",     severity=YELLOW, layer=LAYER, check=check_wd6_engagement_cues,    applies_to=APPLIES_TO),
    Rule(id="WD-7", name="founder image rules",       severity=HARD,   layer=LAYER, check=check_wd7_founder_images,     applies_to=APPLIES_TO),
    Rule(id="WD-8", name="no em dashes",              severity=HARD,   layer=LAYER, check=check_wd8_no_em_dashes,       applies_to=APPLIES_TO),
    Rule(id="WD-9", name="US English",                severity=HARD,   layer=LAYER, check=check_wd9_us_english,         applies_to=APPLIES_TO),
]
