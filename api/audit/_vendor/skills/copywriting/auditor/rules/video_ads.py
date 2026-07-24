"""video_ads.py — VA-1 to VA-6 · video ad hook + craft checks.

Sources (citation on each check):
  skills/scripting/video-ad/workflow.md               the hook 3-criteria HARD STOP (Lauren,
                                                      Slack 2026-06-03), the ~60s / 120-220 word band
  skills/copywriting/references/alec-qc-checklists.md Video Ads section + Stage E fail conditions
  references/best-performers/video-ads/catalog.json   lauren_hook_rule_2026_06_03

About the hook rule. Lauren's rule has three criteria:

  1. specific WHO       — needs judgment. Not encoded.
  2. hot take / value statement / shocking truth — needs judgment. Not encoded.
  3. number of people helped — a digit. THIS one is mechanical, and it's VA-1.

Encoding only criterion 3 is deliberate. Criteria 1 and 2 are exactly the kind of rule a regex
would fake — it could check for the word "women" and call it a specific WHO. The auditor checks
what it can actually prove and leaves the rest to the Stage E human pass, rather than issuing a
green tick nobody should trust.
"""

from __future__ import annotations

import math
import re
from typing import List, Optional, Tuple

from skills.copywriting.auditor.lib.parser import ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation
from skills.copywriting.auditor.lib import sections as S


LAYER = "VideoAds"
APPLIES_TO = {"video_ads"}


# Spoken-delivery ceiling for the word-count math. The old 220 wpm was unsourced and sits in a
# no-man's-land — above the comprehensible-fast band (~200 wpm news-anchor max) yet below the
# auctioneer tier — which inflated the word budget. 180 wpm is honest-fast-but-intelligible (TED
# talks 133-188; audiobook narration ~155; news anchors 175-200), with 200 as the never-cross wall.
# Grounding: references/craft/webinar-and-video-structure-rules.md.
WPM_FAST = 180
SEVENTY_SECOND_WORD_CEILING = math.floor(WPM_FAST * 70 / 60)  # 210

AD_HEADER_RE = re.compile(r"^#{1,4}\s+.*\bad\b\s*#?\s*\d+|^\*\*AD\s*#?\s*\d+", re.I)

# Cue tags and stage directions are not spoken words.
CUE_TAG_RE = re.compile(r"^\s*\[?(CAMERA|B-ROLL|CUT TO|ON-SCREEN|GRAPHIC|AUDIO|HOOK|CTA|VISUAL)\b.*$", re.I)

# A social-proof number is a COUNT OF PEOPLE, not any digit. "a woman over 40" is an age;
# "3,300 women" is proof. Requiring the number to attach to a people-noun (or to the verb
# "helped") is what separates the two — a bare \d+ would wave through every age, price, and
# calorie count in the script.
PEOPLE_NOUNS = (
    r"women|men|people|clients|students|athletes|families|customers|coaches|moms|mums|dads|"
    r"guys|folks|founders|entrepreneurs|patients|members|runners|lifters"
)
SOCIAL_PROOF_RE = re.compile(
    r"\b\d[\d,\.]*\s*(?:\+|k\b)?\s*(?:\w+\s+){0,2}(?:" + PEOPLE_NOUNS + r")\b"
    r"|\bhelped\s+(?:over\s+|more\s+than\s+)?\d",
    re.IGNORECASE,
)

SELF_RATING_RE = re.compile(r"(\d(?:\.\d)?)\s*/\s*10")


def _ad_classifier(title: str) -> Optional[str]:
    if re.search(r"\bad\b|\bscript\b|\bvariation\b|\bhook\b", title, re.I):
        return "ad"
    return None


def _ads(bundle: ParsedBundle) -> List[S.Section]:
    return S.split_sections(bundle.raw_lines, _ad_classifier)


def _spoken_lines(ad: S.Section) -> List[Tuple[int, str]]:
    """Only the words the talent actually says — no cue tags, no headers, no metadata."""
    return [
        (n, c) for n, c in ad.lines
        if c.strip() and not CUE_TAG_RE.match(c) and not S.HEADER_RE.match(c)
        and not re.match(r"^\s*\*\*[^*]+:\*\*\s*$", c)
    ]


def _spoken_text(ad: S.Section) -> str:
    return S.strip_markdown(" ".join(c for _, c in _spoken_lines(ad)))


def _v(rule_id, rule_name, severity, section_id, line_no, line, message, fix) -> Violation:
    return Violation(
        rule_id=rule_id, rule_name=rule_name, severity=severity,
        section_id=section_id, line_no=line_no, line_content=line, message=message, fix_hint=fix,
    )


# ---------------------------------------------------------------------------
# VA-0 · the document actually parses
#
# If no ads are recognised, every other VA rule passes on an empty list and the auditor
# prints "ship clear" for a file it never read. Zero ads is a HARD failure, never a
# silent pass.
# ---------------------------------------------------------------------------


def check_va0_parseable(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if _ads(bundle):
        return []
    return [_v(
        "VA-0", "document parses", HARD, "document", 1, "(0 ads parsed)",
        "No ads could be parsed, so no video-ad rule was actually evaluated. The auditor will not "
        "pass a file it cannot read. Expected headers like `## Ad 1` or `## Video Ad 1 — Hook`.",
        "Fix the ad headers, or extend the parser if this is a new format.",
    )]


# ---------------------------------------------------------------------------
# VA-1 · hook carries a social-proof NUMBER (Lauren's hook rule, criterion 3)
#   catalog.json lauren_hook_rule_2026_06_03 · "creator_social_proof_number"
#   workflow.md · HARD STOP · "No video_ad script generates ... unless the opening hook
#   passes ALL three criteria"
# ---------------------------------------------------------------------------

HOOK_SENTENCES = 3  # workflow.md defines the hook as the opening 1-3 sentences


def check_va1_hook_social_proof(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for ad in _ads(bundle):
        spoken = _spoken_lines(ad)
        if not spoken:
            continue
        # The hook is the opening 1-3 sentences of the script.
        text = " ".join(c for _, c in spoken)
        parts = re.split(r"(?<=[.!?])\s+", S.strip_markdown(text))
        hook = " ".join(parts[:HOOK_SENTENCES])
        if SOCIAL_PROOF_RE.search(hook):
            continue
        violations.append(_v(
            "VA-1", "hook · social-proof number", HARD, ad.section_id, spoken[0][0], hook[:90],
            "Hook carries no social-proof number. Lauren's hook rule requires the number of people "
            "helped, in digit form, in the hook. (The other two criteria — a specific WHO and a hot "
            "take / value statement / shocking truth — need a human read; the auditor does not fake "
            "them.)",
            "Put the count of people helped into the hook, e.g. `3,300+ women`.",
        ))
    return violations


# ---------------------------------------------------------------------------
# VA-2 · at least half the ads under 70 seconds
#   alec-qc-checklists.md:67 "are at least HALF of these ads under 70 seconds"
#   :82 Stage E fail condition · "Fewer than half the ads under 70 seconds"
# ---------------------------------------------------------------------------


def check_va2_length_floor(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    ads = _ads(bundle)
    if len(ads) < 2:
        return []  # batch-level rule — needs a batch

    definitely_over = []
    for ad in ads:
        words = len(_spoken_text(ad).split())
        if words > SEVENTY_SECOND_WORD_CEILING:
            definitely_over.append((ad, words))

    under_or_unknown = len(ads) - len(definitely_over)
    required = math.ceil(len(ads) / 2)
    if under_or_unknown >= required:
        return []

    return [_v(
        "VA-2", "length · half the ads under 70s (advisory)", YELLOW, "batch", ads[0].start_line,
        f"({len(definitely_over)} of {len(ads)} ads over 70s)",
        f"Only {under_or_unknown} of {len(ads)} ads are likely under 70 seconds. {len(definitely_over)} "
        f"exceed {SEVENTY_SECOND_WORD_CEILING} spoken words (over 70s even at {WPM_FAST} wpm). Advisory: "
        f"the sub-70s norm is an ecommerce / paid-social convention with no post-Andromeda coaching-DR "
        f"basis, and high-ticket coaching often runs multi-minute VSL-style ads. Confirm the length "
        f"fits the funnel stage rather than treating it as a block.",
        "For a cold, high-consideration coaching offer a longer ad can win; keep short ads where the "
        "placement rewards them. See references/craft/webinar-and-video-structure-rules.md.",
    )]


# ---------------------------------------------------------------------------
# VA-3 · no hyphens in the spoken script
#   alec-qc-checklists.md:77 "Don't use hyphens." · :83 fail condition "Any ad with hyphens"
# ---------------------------------------------------------------------------

# Hyphens inside URLs and inside {{variables}} aren't spoken, so they don't count.
URL_OR_VAR_RE = re.compile(r"https?://\S+|\{\{[^}]+\}\}|\[[^\]]+\]\([^)]+\)")
HYPHEN_RE = re.compile(r"(?<=\w)-(?=\w)")


def check_va3_no_hyphens(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for ad in _ads(bundle):
        for line_no, content in _spoken_lines(ad):
            scrubbed = URL_OR_VAR_RE.sub("", content)
            m = HYPHEN_RE.search(scrubbed)
            if m:
                violations.append(_v(
                    "VA-3", "no hyphens", HARD, ad.section_id, line_no, content.strip(),
                    "Hyphen in the spoken script. Alec's video-ad rule is zero tolerance — any ad "
                    "with hyphens fails Stage E.",
                    "Rewrite the hyphenated word as two words, or pick a different word.",
                ))
    return violations


# ---------------------------------------------------------------------------
# VA-4 · no bullets or lists in a spoken script
#   alec-qc-checklists.md:77 "Don't use bullet points or lists."
# ---------------------------------------------------------------------------


def check_va4_no_bullets(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for ad in _ads(bundle):
        for line_no, content in _spoken_lines(ad):
            if S.is_bullet(content):
                violations.append(_v(
                    "VA-4", "no bullets or lists", HARD, ad.section_id, line_no, content.strip(),
                    "Bullet in a spoken script. Video ad copy flows conversationally — nobody speaks "
                    "in bullet points.",
                    "Rewrite the list as flowing spoken sentences.",
                ))
    return violations


# ---------------------------------------------------------------------------
# VA-5 · no em dashes
# ---------------------------------------------------------------------------


def check_va5_no_em_dashes(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for ad in _ads(bundle):
        for line_no, content in _spoken_lines(ad):
            if S.EM_DASH_RE.search(content):
                violations.append(_v(
                    "VA-5", "no em dashes", HARD, ad.section_id, line_no, content.strip(),
                    "Em dash. Growth Mate copy uses a comma, a period, or a rewrite.",
                    "Replace the em dash.",
                ))
    return violations


# ---------------------------------------------------------------------------
# VA-6 · self-rating gate present
#   alec-qc-checklists.md:69 "rate each ad 1-10 ... Target 8.5/10 or better"
#   YELLOW: the Video Ads section states a target but no matching Stage E fail line (the
#   documented fail condition lives in the Slides section). The auditor can only verify the
#   rating EXISTS and that a sub-8.5 score came with documented improvements — never that
#   the rating is honest.
# ---------------------------------------------------------------------------


def check_va6_self_rating(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    m = SELF_RATING_RE.search(bundle.raw_text)
    if not m:
        return [_v(
            "VA-6", "self-rating gate", YELLOW, "document", 1, "(no self-rating found)",
            "No self-rating found. Alec's checklist asks for a 1-10 rating per ad, targeting 8.5 or "
            "better.",
            "Add the self-rating block, with what's good and what could be improved.",
        )]
    score = float(m.group(1))
    if score >= 8.5:
        return []
    if re.search(r"improve|could be better|weakness|fix", bundle.raw_text, re.I):
        return []
    return [_v(
        "VA-6", "self-rating gate", YELLOW, "document", 1, m.group(0),
        f"Self-rating is {score}/10, below the 8.5 target, with no documented improvements.",
        "Either lift the copy to 8.5+, or write down what could be improved.",
    )]


# ---------------------------------------------------------------------------
# VA-7 · the hooks are DIFFERENT from one another
#   Each video ad opens with a hook that pulls the viewer in — it does a headline's job, but in a
#   more conversational register. Across a batch those hooks have to be genuinely different angles,
#   not paraphrases, or the ads aren't distinct tests (same stance as SL-6 for subject lines). The
#   OTHER half of the hook — does it actually hook? — is a human/LLM read, like VA-1's criteria 1-2;
#   what's mechanical here is that two hooks are not near-duplicates.
# ---------------------------------------------------------------------------

HOOK_SIMILARITY = 0.6  # same threshold as distinct subject-line variants (SL-6)


def _hook_content_words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if len(w) > 2}


def _hook_similarity(a: str, b: str) -> float:
    wa, wb = _hook_content_words(a), _hook_content_words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _hook_text(ad: S.Section) -> str:
    spoken = " ".join(c for _, c in _spoken_lines(ad))
    parts = re.split(r"(?<=[.!?])\s+", S.strip_markdown(spoken))
    return " ".join(parts[:HOOK_SENTENCES])


def check_va7_hooks_distinct(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    ads = _ads(bundle)
    if len(ads) < 2:
        return []  # batch-level rule — needs a batch
    hooks = [(ad, _hook_text(ad)) for ad in ads]
    violations = []
    for i in range(len(hooks)):
        for j in range(i + 1, len(hooks)):
            (ad_a, a), (ad_b, b) = hooks[i], hooks[j]
            if not a.strip() or not b.strip():
                continue
            sim = _hook_similarity(a, b)
            if sim >= HOOK_SIMILARITY:
                violations.append(_v(
                    "VA-7", "hooks are distinct", HARD, ad_b.section_id, ad_b.start_line, b[:90],
                    f"This hook is {int(sim * 100)}% the same as {ad_a.section_id}'s — the two read as "
                    f"paraphrases. Each ad's opening has to hook the viewer a DIFFERENT way: it does a "
                    f"headline's job (pull them in) but conversationally, and across the batch the angles "
                    f"must genuinely differ, or these aren't distinct tests.",
                    "Give this ad a different opening angle — a different pain, proof, question, or "
                    "contrarian take — not a reworded version of another hook.",
                ))
    return violations


RULES = [
    Rule(id="VA-0", name="document parses",                severity=HARD,   layer=LAYER, check=check_va0_parseable,         applies_to=APPLIES_TO),
    Rule(id="VA-1", name="hook · social-proof number",     severity=HARD,   layer=LAYER, check=check_va1_hook_social_proof, applies_to=APPLIES_TO),
    Rule(id="VA-2", name="length · half the ads under 70s", severity=YELLOW, layer=LAYER, check=check_va2_length_floor,      applies_to=APPLIES_TO),
    Rule(id="VA-3", name="no hyphens",                     severity=HARD,   layer=LAYER, check=check_va3_no_hyphens,        applies_to=APPLIES_TO),
    Rule(id="VA-4", name="no bullets or lists",            severity=HARD,   layer=LAYER, check=check_va4_no_bullets,        applies_to=APPLIES_TO),
    Rule(id="VA-5", name="no em dashes",                   severity=HARD,   layer=LAYER, check=check_va5_no_em_dashes,      applies_to=APPLIES_TO),
    Rule(id="VA-6", name="self-rating gate",               severity=YELLOW, layer=LAYER, check=check_va6_self_rating,       applies_to=APPLIES_TO),
    Rule(id="VA-7", name="hooks are distinct",             severity=HARD,   layer=LAYER, check=check_va7_hooks_distinct,    applies_to=APPLIES_TO),
]
