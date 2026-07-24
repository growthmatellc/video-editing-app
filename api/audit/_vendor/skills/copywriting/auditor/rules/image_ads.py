"""image_ads.py — IA-0..IA-3 · Meta image-ad headline + hook checks.

The image ad is a HEADLINE artifact. Its headline does the same job as a webinar title or a
reg-page hero — it is the pick-out (Ogilvy: ~5x as many people read the headline as the body),
so it answers to the same craft canon. The shared TL rules in headlines.py grade the headline
line itself for image ads (TL-2 outcome verb, TL-3 no shouting, TL-5 no vague filler), and the
SEM-TL8 judge in semantic.py carries TL-9 — the headline must carry the audience AND a tangible
result on its own, and must not be a curiosity gap the subhead has to rescue. That judge is the
instrument that catches the failure this asset type was added for: a sweeping "hot take" headline
that gives the reader no reason to care (Caples: "curiosity by itself is seldom enough").

This module owns the parts specific to the image-ad SURFACE:

  IA-0  the document parses into ads at all — never a silent pass on a file we could not read
  IA-1  a headline length cap — an ad headline reads at thumb-stop, not at landing-page length
  IA-2  the ad carries a social-proof NUMBER (Lauren's hook rule, criterion 3 — the same digit
        VA-1 enforces on video ads, with the noun set widened for this B2B / career audience)
  IA-3  no em dashes (Growth Mate off-brand list)
  IA-4  the subhead (optional) is one point — one sentence backing the headline, not a paragraph
  IA-5  the presenter is NAMED, not a pronoun — "why do I care?" needs a real name + proof
  IA-6  a live webinar is obviously live — the word "live", or a date/time, not a replay/download

Sources (citation on each check):
  references/craft/headline-and-subject-rules.md        TL canon — why the headline IS the ask
  references/craft/image-ad-headline-length.md          the 10-word cap, grounded in the legends (IA-1)
  references/best-performers/video-ads/catalog.json     lauren_hook_rule_2026_06_03 (IA-2)
  skills/image-ads-creation/02-system-prompt.md         the Eyebrow / Headline / Subheadline copy slots
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from skills.copywriting.auditor.lib.parser import ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation
from skills.copywriting.auditor.lib import sections as S


LAYER = "ImageAds"
APPLIES_TO = {"image_ads"}


# The copy slots, as the image-ads system prompt (STEP 4) and the SOP name them. Tolerant of the
# markdown the generator actually emits — leading list markers, bold asterisks, an optional colon —
# and of the label drift between the spec ("Headline / Subheadline") and the live output
# ("Headline / Subhead"). The Headline anchor requires the word to START the label, so it never
# matches "Subheadline" or "Pre-subheadline".
_HEADLINE_RE = re.compile(r"^\s*[-*]?\s*\**\s*headline\s*:?\**\s*(?P<text>.+?)\s*\**\s*$", re.I)
_SUBHEAD_RE = re.compile(
    r"^\s*[-*]?\s*\**\s*sub[-\s]?head(?:line)?\s*:?\**\s*(?P<text>.+?)\s*\**\s*$", re.I
)
_EYEBROW_RE = re.compile(
    r"^\s*[-*]?\s*\**\s*(?:eyebrow|pre[-\s]?sub[-\s]?head(?:line)?|pre[-\s]?head(?:line)?)"
    r"\s*:?\**\s*(?P<text>.+?)\s*\**\s*$",
    re.I,
)

# A variant boundary — either the generator's `VARIANT N` header or a markdown numbered concept
# header ("1. Pain (...)"). Used only to LABEL each ad; ad blocks are delimited by the headlines
# themselves, so a doc with no variant headers still parses.
_VARIANT_HEADER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*(?P<label>(?:variant\s*\d+|concept\s*\d+|\d+\.)\s*\S.*?)\s*\**\s*$",
    re.I,
)

# A social-proof number is a COUNT, not any digit. VA-1's people-noun set is tuned for health /
# coaching avatars; this audience counts "professionals", "businesses", and "companies", which
# that set omits. Widened here rather than in video_ads so the video rule's blast radius stays
# put. A fixed noun list is always incomplete — the `trained/helped/...` verb arm is the backstop.
_PROOF_NOUNS = (
    r"women|men|people|clients|students|professionals|customers|founders|entrepreneurs|"
    r"executives|leaders|managers|teams|businesses|companies|organi[sz]ations|brands|"
    r"members|coaches|patients|owners|operators"
)
_PROOF_RE = re.compile(
    r"\b\d[\d,\.]*\s*(?:\+|k\b)?\s*(?:\w+\s+){0,2}(?:" + _PROOF_NOUNS + r")\b"
    r"|\b(?:helped|trained|served|coached|taught)\s+(?:over\s+|more\s+than\s+)?\d",
    re.IGNORECASE,
)

# The glance-read cliff. Ogilvy's own data (Starch) puts readership falling off past TEN words —
# and an image-ad headline is a ~1-second scroll-stop for a cold, low-awareness audience, which is
# exactly the market Schwartz says wants the claim SHORT (Breakthrough Advertising, stage 1). So the
# cap sits at the readership cliff, not higher. Deliberately NOT grounded on AdEspresso's "~5 words"
# 752k-ad mode — that dataset skews ecommerce, not high-ticket coaching, and it is a popularity
# count, not a lift test. Meta's 27/40-char FIELD truncation does not apply either: these headlines
# are baked into the image, not typed into the Meta headline field, so the constraint is pure
# readability, which is the legends' domain. YELLOW and ceiling-only (no floor — ad headlines are
# legitimately short, which is why image_ads is NOT in TL-4's 6-14 band). A punchy two-clause line
# of ~12-15 words can still read at a glance, so this flags "confirm it reads in one second", never
# a block. Full sourcing: references/craft/image-ad-headline-length.md
MAX_HEADLINE_WORDS = 10

# The subhead is OPTIONAL, and when present it is ONE point — one sentence that backs the headline
# with a single proof beat, not a paragraph and not two points. Most people read only the headline
# (Ogilvy), so the subhead gets a fraction of that attention. ~15 words is about one supporting
# sentence; IA-4 also flags more than one sentence. YELLOW. (Nothing requires a subhead at all.)
MAX_SUBHEAD_WORDS = 15


@dataclass
class AdBlock:
    label: str
    headline_line: int
    headline: str
    subhead: str
    block_lines: List[Tuple[int, str]]
    subhead_line: int = 0

    @property
    def block_text(self) -> str:
        return " ".join(c for _, c in self.block_lines)


def _v(rule_id, rule_name, severity, section_id, line_no, line, message, fix) -> Violation:
    return Violation(
        rule_id=rule_id, rule_name=rule_name, severity=severity,
        section_id=section_id, line_no=line_no, line_content=line, message=message, fix_hint=fix,
    )


def _nearest_label(raw_lines: List[str], headline_idx: int, fallback: str) -> str:
    """The variant/concept header just above this headline, or a positional fallback."""
    for i in range(headline_idx - 1, max(-1, headline_idx - 12), -1):
        line = raw_lines[i]
        if not line.strip():
            continue
        m = _VARIANT_HEADER_RE.match(line)
        if m:
            return S.strip_markdown(m.group("label")).strip().rstrip(":").strip()[:60]
    return fallback


# Operator notes and designer instructions are not shipped ad copy, so the off-brand / proof
# checks skip them — a `Design:` / `Design note:` line with an em dash never blocks ship. Matches a
# bare `Design:` too (the generator dropped "note"), which otherwise slipped through and false-flagged.
_NOTE_RE = re.compile(r"^\s*[-*]?\s*\**\s*(?:design|reviewer\s+note|note|qc)\b", re.I)


def _segment_ranges(raw: List[str]) -> List[Tuple[int, int]]:
    """The document split into one clean, non-overlapping range per ad.

    Prefer explicit `VARIANT N` / numbered-concept headers as delimiters — that is the generator's
    own output format (STEP 4). A doc with no variant headers falls back to headline-delimited
    ranges, with a directly-preceding eyebrow pulled into the ad it introduces (the following
    headline), never the one before it — which is what stops one eyebrow being counted twice.
    """
    variant_idxs = [i for i, l in enumerate(raw) if _VARIANT_HEADER_RE.match(l)]
    if variant_idxs:
        bounds = variant_idxs + [len(raw)]
        return [(bounds[k], bounds[k + 1]) for k in range(len(variant_idxs))]

    headline_idxs = [i for i, l in enumerate(raw) if _HEADLINE_RE.match(l)]
    starts = []
    for idx in headline_idxs:
        start = idx
        for j in range(idx - 1, max(-1, idx - 4), -1):
            if not raw[j].strip():
                continue
            if _EYEBROW_RE.match(raw[j]):
                start = j
            break
        starts.append(start)
    return [(s, starts[k + 1] if k + 1 < len(starts) else len(raw)) for k, s in enumerate(starts)]


def _ad_blocks(bundle: ParsedBundle) -> List[AdBlock]:
    """Every ad in the doc, one per segment.

    `block_lines` is the ad's shipped COPY only — eyebrow, headline, subhead, button, bullets,
    quote card. Markdown/variant headers and operator notes are excluded, so IA-2 (proof) and
    IA-3 (em dash) grade what actually ships, not the document's scaffolding.
    """
    raw = bundle.raw_lines
    blocks: List[AdBlock] = []
    for (s, e) in _segment_ranges(raw):
        hl_idx = next((i for i in range(s, e) if _HEADLINE_RE.match(raw[i])), None)
        if hl_idx is None:
            continue  # a segment with no Headline slot (intro, trailing notes) is not an ad
        subhead = ""
        subhead_line = 0
        for i in range(hl_idx + 1, e):
            sm = _SUBHEAD_RE.match(raw[i])
            if sm:
                subhead = sm.group("text").strip()
                subhead_line = i + 1
                break
        copy_lines = [
            (i + 1, raw[i]) for i in range(s, e)
            if raw[i].strip()
            and not S.HEADER_RE.match(raw[i])
            and not _VARIANT_HEADER_RE.match(raw[i])
            and not _NOTE_RE.match(raw[i])
        ]
        blocks.append(AdBlock(
            label=_nearest_label(raw, hl_idx, f"Image ad {len(blocks) + 1}"),
            headline_line=hl_idx + 1,
            headline=_HEADLINE_RE.match(raw[hl_idx]).group("text").strip(),
            subhead=subhead,
            subhead_line=subhead_line or (hl_idx + 1),
            block_lines=copy_lines,
        ))
    return blocks


def headline_units(bundle: ParsedBundle) -> List[Tuple[int, str, str, str]]:
    """The shared accessor headlines.py imports for the TL rules and the SEM-TL8 judge.

    -> [(headline_line, label, headline, subhead)]
    """
    return [(b.headline_line, b.label, b.headline, b.subhead) for b in _ad_blocks(bundle)]


# ---------------------------------------------------------------------------
# IA-0 · the document parses into ads
#
# If no headline slot is recognised, every TL rule and every IA rule passes on an empty list and
# the auditor prints "ship clear" for a file it never read — the vacuous pass. Zero ads is a HARD
# failure, never a silent one. (Same stance as VA-0.)
# ---------------------------------------------------------------------------


def check_ia0_parseable(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if _ad_blocks(bundle):
        return []
    return [_v(
        "IA-0", "document parses", HARD, "document", 1, "(0 image ads parsed)",
        "No image-ad headlines could be parsed, so no headline rule was actually evaluated. The "
        "auditor will not pass a file it cannot read. Expected a `Headline:` slot per variant (see "
        "skills/image-ads-creation/02-system-prompt.md STEP 4).",
        "Give each variant a `Headline:` line (and a `Subheadline:`), or extend the parser if this "
        "is a new format.",
    )]


# ---------------------------------------------------------------------------
# IA-1 · headline length cap — reads at thumb-stop, not at landing-page length
#   docs/sops/image-ads.md · copy must be "easy to read" and fit the design format
# ---------------------------------------------------------------------------


def check_ia1_headline_length(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for block in _ad_blocks(bundle):
        n = len(S.strip_markdown(block.headline).split())
        if n <= MAX_HEADLINE_WORDS:
            continue
        violations.append(_v(
            "IA-1", "headline reads at thumb-stop length", YELLOW, block.label,
            block.headline_line, block.headline,
            f"Headline is {n} words. Ogilvy's data puts readership falling off past {MAX_HEADLINE_WORDS}, "
            f"and an ad headline is a one-second scroll-stop for a cold audience, not a landing-page "
            f"read. Confirm it still lands at a glance (a punchy two-clause line can pass on review).",
            "Tighten to one punchy line. Move the supporting detail to the subhead.",
        ))
    return violations


# ---------------------------------------------------------------------------
# IA-2 · the ad carries a social-proof number (Lauren's hook rule, criterion 3)
#   references/best-performers/video-ads/catalog.json · lauren_hook_rule_2026_06_03
#
# Same rule VA-1 enforces on video hooks — the count of people (or businesses) helped, in digit
# form. On an image ad the proof usually sits in the subhead, so this grades the whole
# above-the-fold unit (eyebrow + headline + subhead), not the headline alone. The other two
# criteria — a specific WHO and a hot take / value statement / shocking truth — need a human read
# (and the TL-9 judge covers the WHO + tangible-result half); the auditor does not fake them.
# ---------------------------------------------------------------------------


def check_ia2_social_proof_number(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for block in _ad_blocks(bundle):
        if _PROOF_RE.search(block.block_text):
            continue
        violations.append(_v(
            "IA-2", "ad carries a social-proof number", HARD, block.label,
            block.headline_line, block.headline,
            "This ad carries no social-proof number. Lauren's hook rule requires the count of "
            "people (or businesses) helped, in digit form, somewhere in the above-the-fold unit — "
            "the headline or the subhead. A hot take with no proof number is the failure this asset "
            "type was added to catch.",
            "Put the count into the headline or subhead, e.g. `2,000+ professionals` or `39 businesses`.",
        ))
    return violations


# ---------------------------------------------------------------------------
# IA-3 · no em dashes (Growth Mate off-brand list)
# ---------------------------------------------------------------------------


def check_ia3_no_em_dashes(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for block in _ad_blocks(bundle):
        for line_no, content in block.block_lines:
            if S.EM_DASH_RE.search(content):
                violations.append(_v(
                    "IA-3", "no em dashes", HARD, block.label, line_no, content.strip(),
                    "Em dash. Growth Mate copy uses a comma, a period, or a rewrite.",
                    "Replace the em dash.",
                ))
    return violations


# ---------------------------------------------------------------------------
# IA-4 · subhead reads at a glance — not a paragraph
#   The "too much text on the image" failure. The subhead supports the headline at a glance; a
#   paragraph-length subhead means the ad is carrying landing-page copy. references/craft/image-ad-headline-length.md
# ---------------------------------------------------------------------------


def check_ia4_subhead_length(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """The subhead, if present, is ONE point — one sentence backing the headline. Optional: an ad
    with no subhead is fine (this only fires on a subhead that exists and does too much)."""
    violations = []
    for block in _ad_blocks(bundle):
        if not block.subhead:
            continue  # a subhead is optional — nothing requires one
        sub = S.strip_markdown(block.subhead).strip()
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", sub) if s.strip()]
        n_words = len(sub.split())
        if len(sentences) <= 1 and n_words <= MAX_SUBHEAD_WORDS:
            continue
        if len(sentences) > 1:
            message = (
                f"Subhead is {len(sentences)} sentences. It should be ONE point — a single sentence "
                f"that backs the headline with one proof beat. The extra points belong on the landing "
                f"page, not on the image."
            )
        else:
            message = (
                f"Subhead is {n_words} words. Keep it to one short sentence (~{MAX_SUBHEAD_WORDS} words) "
                f"that backs the headline with a single beat; the rest goes to the landing page, not "
                f"onto the image."
            )
        violations.append(_v(
            "IA-4", "subhead is one supporting sentence", YELLOW, block.label, block.subhead_line,
            block.subhead, message,
            "Cut the subhead to one sentence, one point — or drop it if the headline stands alone.",
        ))
    return violations


# ---------------------------------------------------------------------------
# IA-5 · the presenter is NAMED, not a pronoun
#   "Why do I care?" is answered by a real name + proof, never "she" / "he". Every ad names the
#   presenter (from the client's display_name, when that is a person). HARD.
# ---------------------------------------------------------------------------

_PERSON_NAME_RE = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z'’.\-]+)+$")


def _presenter_name(ctx: dict) -> Optional[str]:
    client = ctx.get("client_data")
    name = (getattr(client, "display_name", None) or "").strip() if client else ""
    return name if _PERSON_NAME_RE.match(name) else None


def check_ia5_presenter_named(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    name = _presenter_name(ctx)
    if not name:
        return []  # no person-presenter on file to require (company brand, or no --client)
    last = re.escape(name.split()[-1])
    violations = []
    for block in _ad_blocks(bundle):
        text = block.block_text
        if name in text or re.search(rf"\b{last}\b", text):
            continue
        violations.append(_v(
            "IA-5", "presenter named (not a pronoun)", HARD, block.label, block.headline_line,
            block.headline,
            f"This ad names no presenter — the authority and proof are riding on a pronoun. People "
            f"ask \"why do I care?\", and \"she\" / \"he\" doesn't answer it. Name {name} on the image, "
            f"next to the proof.",
            f"Put {name}'s name with the proof (e.g. \"{name} has trained 2,000+ professionals\").",
        ))
    return violations


# ---------------------------------------------------------------------------
# IA-6 · a live webinar is obviously live
#   If the ad drives to a live training, the viewer must be able to tell it's LIVE — the word
#   "live", or a date/time — not a replay or a download. YELLOW.
#
# NOTE — there is deliberately NO mechanical "the unique mechanism must be on the image" rule.
# Relevance via a named mechanism matters, but image ads TEST different mechanisms — a regex tied
# to the client's declared mechanism would false-flag an ad testing a new one. That relevance call
# lives in the SEM-TL8 judge (what it solves / what solution it brings) and the generation prompt.
# ---------------------------------------------------------------------------

_WEBINAR_AD_RE = re.compile(
    r"\b(webinar|masterclass|workshop|training|session|register|registration|reserve|save\s+my\s+seat)\b",
    re.I,
)
_LIVE_SIGNAL_RE = re.compile(
    r"\blive\b"
    r"|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b"
    r"|\b(?:jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)\.?\s+\d"
    r"|\b(?:mon|tues?|wed|thurs?|fri|sat|sun)(?:day)?\b"
    r"|\b\d{1,2}\s*[:.]\s*\d{2}\s*(?:am|pm|et|pt|est|pst)\b",
    re.I,
)


def check_ia6_live_is_obvious(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for block in _ad_blocks(bundle):
        text = block.block_text
        if not _WEBINAR_AD_RE.search(text):
            continue  # not obviously a webinar / training ad
        if _LIVE_SIGNAL_RE.search(text):
            continue
        violations.append(_v(
            "IA-6", "live webinar is obvious", YELLOW, block.label, block.headline_line,
            block.headline,
            "This reads like a live-webinar ad, but nothing on the image says it's LIVE. If the offer "
            "is a live training, make that obvious — the word 'live', or the date/time — so the viewer "
            "knows it's a real event, not a replay or a download.",
            "Add a 'LIVE TRAINING' eyebrow or the date/time to the ad (not on the button).",
        ))
    return violations


RULES = [
    Rule(id="IA-0", name="document parses",                    severity=HARD,   layer=LAYER, check=check_ia0_parseable,           applies_to=APPLIES_TO),
    Rule(id="IA-1", name="headline reads at thumb-stop length", severity=YELLOW, layer=LAYER, check=check_ia1_headline_length,     applies_to=APPLIES_TO),
    Rule(id="IA-2", name="ad carries a social-proof number",   severity=HARD,   layer=LAYER, check=check_ia2_social_proof_number, applies_to=APPLIES_TO),
    Rule(id="IA-3", name="no em dashes",                       severity=HARD,   layer=LAYER, check=check_ia3_no_em_dashes,        applies_to=APPLIES_TO),
    Rule(id="IA-4", name="subhead is one supporting sentence", severity=YELLOW, layer=LAYER, check=check_ia4_subhead_length,      applies_to=APPLIES_TO),
    Rule(id="IA-5", name="presenter named (not a pronoun)",    severity=HARD,   layer=LAYER, check=check_ia5_presenter_named,     applies_to=APPLIES_TO),
    Rule(id="IA-6", name="live webinar is obvious",            severity=YELLOW, layer=LAYER, check=check_ia6_live_is_obvious,     applies_to=APPLIES_TO),
]
