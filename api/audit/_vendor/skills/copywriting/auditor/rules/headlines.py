"""headlines.py — SL / PH / TL · subject lines, preview text, and titles.

The governing principle (Lauren, 2026-07-13):

    Voice matters less in a headline than in body copy. Subject lines, webinar titles, and
    page headlines are HEADLINES. The title carries the promise; the body carries the voice.

Grounding — this is canon, not preference:

  Hopkins, Scientific Advertising  "The purpose of a headline is to pick out people you can
                                    interest." A headline is a QUALIFIER, not entertainment.
                                    Personality does not qualify anyone.
  Caples, Tested Advertising       Self-interest, News, Curiosity, Quick-and-easy. And the
                                    enforcement rule: "curiosity by itself is seldom enough."
  Ogilvy                           5x as many people read the headline as the body.

A webinar title asks for a calendar commitment, not a two-second click. The cost of the ask is
far higher than an email open, so the promise must be MORE specific, not more charming. If voice
and clarity conflict in a title, clarity wins.

Full research, sources and the contested claims: references/craft/headline-and-subject-rules.md

What is deliberately NOT automated
----------------------------------
"Clever vs clear" is not a check here, and that is on purpose. Scientific Reports (2025)
analysed 8,977 A/B tests from the Upworthy archive and found the effect of concreteness is
CONDITIONAL: on already-concrete headlines, adding more concreteness cut clicks 9.9%. A rule
that mechanically punishes curiosity is not supported by the evidence. Direct-beats-clever
stays a human editorial standard (Lauren §B.7, §G.5), not a regex.

Nor is there a spam-word blocklist. Google's published sender guidelines contain zero
word-based rules — deliverability is authentication, complaint rate, and list hygiene. A
blocklist would reject "Free workshop", one of the highest-converting phrases we write. What
IS enforced is shouty FORMATTING (ALL CAPS, !!!, $$$) on complaint-rate grounds, and fake
Re:/Fwd: prefixes, which Google names explicitly and CAN-SPAM makes illegal.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from skills.copywriting.auditor.lib.parser import ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation
from skills.copywriting.auditor.lib import sections as S


LAYER = "Headlines"
APPLIES_TO = {"email_sequence", "email_launch", "webinar_deck", "funnel_pages"}
EMAIL_ASSETS = {"email_sequence", "email_launch"}
TITLE_ASSETS = {"webinar_deck", "funnel_pages"}
# TL rules that also grade image-ad headlines. Deliberately a subset: TL-2 (outcome verb), TL-3
# (no shouting) and TL-5 (no vague filler) transfer cleanly. TL-1 (number/audience/timeframe) and
# TL-7 (desire vocabulary) are left OFF for image ads — an image-ad headline carries the audience
# in its eyebrow/targeting and a pain-reframe headline legitimately names no number, so those two
# would HARD-fail defensible copy. The audience + tangible-result judgment for image ads is made,
# as a judge, by SEM-TL8/TL-9. TL-4's word band is replaced for image ads by IA-1 (ceiling, no floor).
TITLE_PLUS_ADS = TITLE_ASSETS | {"image_ads"}


BRACKET_PREFIX_RE = re.compile(r"^\s*\[[^\]]+\]\s*")

# Gmail's mobile app truncates the subject at roughly 30 characters; other clients land
# between 30 and 46. Past ~40 chars of subject CONTENT you are gambling that the payload
# survives the cut on the most common phone client in the world.
SUBJECT_FRONTLOAD_CHARS = 40

# Preview text. Below ~40 chars the client backfills from your email body — Litmus documents
# "View this email in your browser", unsubscribe text, and image alt-text leaking into the
# inbox. Above ~90 it is dead weight everywhere except macOS Mail.
PREHEADER_MIN_CHARS = 40
PREHEADER_MAX_CHARS = 90
PREHEADER_HARD_MAX = 100

# Similarity above this and the preview text is just restating the subject, which burns the
# second-biggest piece of inbox real estate we own for zero information gain.
SUBJECT_PREHEADER_OVERLAP = 0.6

# Accepts `**Preview text:**`, `Preheader:`, and the labelled form `**Preview A:**`.
PREHEADER_LINE_RE = S.PREVIEW_VARIANT_RE

# Litmus's documented failure mode — what leaks in when the preheader is empty or too short.
LEAKED_BOILERPLATE_RE = re.compile(
    r"view\s+(?:this\s+)?(?:email\s+)?in\s+(?:your\s+)?browser|view\s+online|"
    r"\bunsubscribe\b|if\s+you\s+can'?t\s+see|\[image\]|\balt=",
    re.I,
)

# Google's sender guidelines name faked reply/forward prefixes explicitly. CAN-SPAM makes a
# deceptive subject line illegal. This is the least ambiguous rule in the whole module.
FAKE_REPLY_RE = re.compile(r"^\s*(?:re|fwd?|fw)\s*:", re.I)

# The repo's own Stage-1 "lead-element classification" (email-sequence workflow), never encoded
# until now. A subject that opens with story setup or generic curiosity has buried the payload
# behind filler — which is the front-loading failure in its most common form.
FILLER_OPENER_RE = re.compile(
    r"^\s*(?:"
    r"i\s+(?:want|wanted)\s+to\s+(?:tell|share|talk)"
    r"|here'?s\s+what\s+happened"
    r"|let\s+me\s+tell\s+you"
    r"|quick\s+(?:question|note|one|update)"
    r"|one\s+more\s+thing"
    r"|a\s+(?:quick|little|small)\s+\w+"
    r"|just\s+checking\s+in"
    r"|thought\s+you'?d\s+like"
    r"|hey\s+there"
    r"|(?:some|a)\s+(?:news|thoughts)"
    r")\b",
    re.I,
)

# Acronyms that are legitimately capitalised and must not trip the ALL-CAPS check.
CAPS_ALLOWLIST = {
    "CEO", "ROI", "AI", "SEO", "B2B", "B2C", "CTA", "PDF", "US", "USA", "UK", "PT", "ET", "EST",
    "PST", "CST", "MST", "AM", "PM", "Q1", "Q2", "Q3", "Q4", "GLP", "HRT", "PCOS", "BP", "DM",
    "LIVE", "FAQ", "TV", "VIP", "USC", "WNBF", "NEW",
}
ALL_CAPS_RE = re.compile(r"\b[A-Z][A-Z0-9'’\-]{2,}\b")

# --- Title rules -----------------------------------------------------------

# 4 U's: Ultra-specific. Caples: self-interest and news. A title that names no number, no
# audience, and no timeframe is making a promise nobody can size.
TITLE_NUMBER_RE = re.compile(r"\d")
# An audience is named three ways, and the construction matters more than the vocabulary — a
# fixed noun list is always incomplete (this one originally missed "triathletes", which is the
# audience of one of our own anchors):
#   1. `for <someone>`                     — "for coaches"
#   2. `How <plural noun> …`                — "How Triathletes Cross the Finish Line"
#   3. a named group from the lexicon       — the fallback
TITLE_AUDIENCE_RE = re.compile(
    r"\bfor\s+\w+"
    r"|\bhow\s+[a-z]+(?:s|men|women|people)\b"
    r"|\b(?:women|men|moms|mums|dads|coaches|founders|athletes|runners|triathletes|cyclists|"
    r"swimmers|lifters|parents|nurses|physicians|doctors|therapists|entrepreneurs|executives|"
    r"leaders|creators|owners|professionals|managers|teachers|consultants|agents)\b"
    r"|\bover\s+\d+\b",
    re.I,
)
TITLE_TIMEFRAME_RE = re.compile(
    r"\bin\s+\d+\s+(?:days?|weeks?|months?|minutes?)\b|\bbefore\b|\bthis\s+(?:week|month|year)\b|"
    r"\bby\s+\w+day\b|\b\d+[-\s]?(?:day|week|month)\b", re.I
)

# ON24: outcome-focused beats topic-focused. A title with no verb is a topic LABEL, not a
# promise. "Metabolic Fuel Workshop" is a label. "How Women Over 40 Lose Weight By Eating More"
# is a headline.
# Grammar beats a word list here. `How to <X>` and `How <audience> <X>` guarantee X is a verb by
# construction, so those frames satisfy the rule outright — no lexicon needed. The word list below
# is only the fallback for titles that don't use a "how" frame.
#
# Any fixed verb list is permanently incomplete. This one originally missed "cross", and so flagged
# the Lauren-PASS Erinne anchor ("How to Cross the Finish Line — Without More Miles") as having no
# verb. That was a false positive, and it is exactly the failure mode that would erode trust in the
# whole auditor. The grammar check prevents that class of error; the lexicon just widens the net.
HOW_TO_FRAME_RE = re.compile(r"\bhow\s+(?:to|i|we|you)\s+\w+|\bhow\s+\w+(?:\s+\w+){0,3}\s+\w+", re.I)
OUTCOME_VERB_RE = re.compile(
    r"\b(?:lose|lost|losing|get|gets|getting|build|builds|building|close|closing|fix|fixes|fixing|"
    r"double|doubling|cut|cutting|launch|launching|stop|stops|stopping|turn|turning|book|booking|"
    r"land|landing|add|adding|grow|growing|scale|scaling|beat|beating|end|ending|heal|healing|"
    r"drop|dropping|earn|earning|make|making|win|winning|reverse|reversing|escape|escaping|"
    r"eat|eating|train|training|run|running|start|starting|create|creating|master|find|finding|"
    r"cross|crossing|reach|reaching|shed|shedding|"
    r"overcome|unlock|rebuild|restore|reclaim|survive|thrive|qualify|quit|ditch)\b",
    re.I,
)
# Deliberately NOT in the list: fuel, finish, break, hit, drop. Each is a verb in isolation but a
# NOUN inside our own mechanism names — "Metabolic Fuel", "Finish Line". Including them made
# `The Metabolic Fuel Workshop` pass TL-2 as though "Fuel" were a promise. A verb lexicon collides
# with product names, which is precisely why the grammar check above carries the real weight.

# Belkins: "marketing jargon / generic" is the worst-performing category. Caples on curiosity
# without substance. These are the tokens that signal a title said nothing.
TITLE_VAGUE_RE = re.compile(
    r"\b(?:masterclass|deep\s+dive|everything\s+you\s+need\s+to\s+know|the\s+ultimate\s+guide|"
    r"secrets?|unlocking|demystified|101|and\s+more|tips\s*(?:&|and)\s*tricks|"
    r"the\s+truth\s+about|game[-\s]?changer)\b",
    re.I,
)

TITLE_WORD_BAND = (6, 14)


def _v(rule_id, rule_name, severity, section_id, line_no, line, message, fix) -> Violation:
    return Violation(
        rule_id=rule_id, rule_name=rule_name, severity=severity,
        section_id=section_id, line_no=line_no, line_content=line, message=message, fix_hint=fix,
    )


def _subject_content(subject: str) -> str:
    """Subject minus the bracketed workshop-name prefix, which is a category tag, not content."""
    return BRACKET_PREFIX_RE.sub("", subject or "").strip()


def _preheader_of(section) -> Optional[Tuple[int, str]]:
    for line_no, content in section.body_lines:
        m = PREHEADER_LINE_RE.match(content)
        if m:
            return line_no, m.group("text").strip()
    return None


STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "is",
    "are", "was", "were", "be", "been", "it", "its", "this", "that", "you", "your", "i", "my",
    "me", "we", "our", "she", "he", "her", "his", "them", "they", "how", "what", "why", "here",
    "did", "do", "does", "got", "get", "s", "t",
}


def _content_words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOPWORDS}


def _overlap(subject: str, preheader: str) -> float:
    """How much of the SUBJECT the preview repeats. 1.0 = the preview said nothing new.

    Measured against the subject's content words, not the preview's. Measuring it the other way
    round lets a writer bury a full restatement under enough filler to dilute the score — the
    preview would repeat every word of the subject and still pass.
    """
    ws, wp = _content_words(subject), _content_words(preheader)
    if not ws:
        return 0.0
    return len(ws & wp) / len(ws)


def _similarity(a: str, b: str) -> float:
    """Symmetric overlap (Jaccard) between two subject variants.

    Symmetric, unlike _overlap, because neither variant is the reference — we're asking whether
    these two are the same line, not whether one echoes the other.
    """
    wa, wb = _content_words(a), _content_words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _caps_violations(text: str) -> List[str]:
    # Strip trailing possessives/punctuation before the allowlist test, or `AI's` is captured as
    # `AI'` — which is not `AI` in the allowlist, and a legitimate acronym gets flagged as shouting.
    out = []
    for w in ALL_CAPS_RE.findall(text):
        core = re.sub(r"[^A-Za-z0-9]", "", w)
        if core and core.upper() not in CAPS_ALLOWLIST:
            out.append(w)
    return out


# ---------------------------------------------------------------------------
# SL · subject lines
# ---------------------------------------------------------------------------


def check_sl1_no_filler_opener(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """The subject leads with the payload, not with story setup or generic curiosity.

    Source: email-sequence/workflow.md Stage-1 lead-element classification — "Setup/story
    preamble ... FAIL. Generic curiosity ('Quick question', 'One more thing') ... FAIL."
    Written down since 2026-05-20, never enforced until now.

    Runs on EVERY subject variant. A weak option in the set is a weak option the operator
    might pick — there is no such thing as a subject line that only half-ships.
    """
    violations = []
    for section in bundle.emails:
        for line_no, subject in S.subject_variants(section):
            content = _subject_content(subject)
            if not content:
                continue
            m = FILLER_OPENER_RE.match(content)
            if m:
                violations.append(_v(
                    "SL-1", "subject leads with the payload", HARD,
                    section.section_id, line_no, subject,
                    f"Subject opens with `{m.group(0).strip()}` — story setup or generic curiosity. "
                    f"The payload is buried behind filler, and Gmail's mobile app cuts the subject at "
                    f"about 30 characters, so the reader may never see it. Lead with the concrete result.",
                    "Rewrite so the result leads. Not `I want to tell you about Esther` — `Off her BP meds in 90 days`.",
                ))
    return violations


def check_sl2_frontload(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Gmail mobile truncates at ~30 chars. Past ~40 chars of content, check the payload survives."""
    violations = []
    for section in bundle.emails:
        for line_no, subject in S.subject_variants(section):
            content = _subject_content(subject)
            if len(content) <= SUBJECT_FRONTLOAD_CHARS:
                continue
            violations.append(_v(
                "SL-2", "subject front-loaded", YELLOW,
                section.section_id, line_no, subject,
                f"Subject content is {len(content)} chars. Gmail's mobile app shows about 30, most "
                f"phones 30 to 46. Everything past `{content[:SUBJECT_FRONTLOAD_CHARS]}…` may never be "
                f"seen. Check the payload lands before the cut.",
                "Move the concrete result to the front, or tighten the subject.",
            ))
    return violations


def check_sl3_shouting(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """No ALL CAPS, no punctuation pile-ups.

    Justified by complaint rate and brand trust, NOT by spam filters — Google's sender
    guidelines contain no formatting rules. Complaints are the real deliverability killer
    (Google enforces a user-reported spam rate below 0.30%), and shouty subjects earn them.
    """
    violations = []
    for section in bundle.emails:
        for line_no, subject in S.subject_variants(section):
            caps = _caps_violations(subject)
            if caps:
                violations.append(_v(
                    "SL-3", "no shouting in the subject", HARD,
                    section.section_id, line_no, subject,
                    f"ALL-CAPS word(s) in the subject: {', '.join(caps)}. Shouty subjects earn spam "
                    f"complaints, and complaint rate is what actually governs deliverability.",
                    "Use sentence case.",
                ))
            if subject.count("!") >= 2:
                violations.append(_v(
                    "SL-3", "no shouting in the subject", HARD,
                    section.section_id, line_no, subject,
                    f"{subject.count('!')} exclamation marks in the subject. One at most.",
                    "Cut the exclamation marks. The claim should carry the energy.",
                ))
            if re.search(r"\${2,}|!{2,}|\?{2,}", subject):
                violations.append(_v(
                    "SL-3", "no shouting in the subject", HARD,
                    section.section_id, line_no, subject,
                    "Punctuation pile-up (`$$$`, `!!!`, `???`) in the subject.",
                    "Remove it.",
                ))
    return violations


def check_sl4_fake_reply(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """No faked Re:/Fwd: prefixes.

    Google's sender guidelines name this explicitly, and CAN-SPAM makes a deceptive subject
    line ILLEGAL. This is the one hard, non-negotiable subject-line rule.
    """
    violations = []
    for section in bundle.emails:
        for line_no, subject in S.subject_variants(section):
            content = _subject_content(subject)
            if content and FAKE_REPLY_RE.match(content):
                violations.append(_v(
                    "SL-4", "no fake Re:/Fwd: prefix", HARD,
                    section.section_id, line_no, subject,
                    "Subject fakes a reply or forward. Google names this as a sender-guideline "
                    "violation, and CAN-SPAM makes a deceptive subject line illegal. Not a grey area.",
                    "Remove the Re:/Fwd: prefix.",
                ))
    return violations


# ---------------------------------------------------------------------------
# SL-5 · every email ships 2-3 subject line options
# SL-6 · the options are different ANGLES, not the same line reworded
# ---------------------------------------------------------------------------

SUBJECT_VARIANT_BAND = (2, 3)

# Two subjects sharing this much of their content words aren't two subjects. They're one
# subject and a paraphrase, and they hand the operator a choice that isn't a choice.
VARIANT_SIMILARITY = 0.6


def check_sl5_variant_count(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Give the operator a real choice: 2-3 subject lines per email.

    Source: Lauren, 2026-07-13. The subject line is the highest-leverage single decision in the
    email (email-launch/workflow.md: "Subject line = the headline"), and one option is not a
    decision. Two or three lets the operator pick the angle that fits the list, and gives a
    real A/B to test.
    """
    violations = []
    low, high = SUBJECT_VARIANT_BAND
    for section in bundle.emails:
        variants = S.subject_variants(section)
        n = len(variants)
        if low <= n <= high:
            continue
        if n < low:
            violations.append(_v(
                "SL-5", "2-3 subject line options", HARD,
                section.section_id, section.start_line,
                variants[0][1] if variants else "(no subject)",
                f"Only {n} subject line offered. Every email ships {low} to {high} options so the "
                f"operator picks the angle — one subject is not a choice, and the subject is the "
                f"highest-leverage decision in the email.",
                "Add a second and third subject line, each taking a different angle "
                "(`**Subject A:** …` / `**Subject B:** …` / `**Subject C:** …`).",
            ))
        else:
            violations.append(_v(
                "SL-5", "2-3 subject line options", YELLOW,
                section.section_id, section.start_line, variants[0][1],
                f"{n} subject lines offered. {low} to {high} is the band — past that it stops being a "
                f"choice and starts being a shortlist nobody reads.",
                f"Cut to the best {high}.",
            ))
    return violations


def check_sl6_variants_are_distinct(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """The options must be different ANGLES, not one line reworded.

    Three variants that all say the same thing hand the operator a fake choice and a useless
    A/B test. Distinct angle means distinct content words: a result, a story hook, an objection,
    a contrarian claim — not a synonym swap.
    """
    violations = []
    for section in bundle.emails:
        variants = S.subject_variants(section)
        for i in range(len(variants)):
            for j in range(i + 1, len(variants)):
                (_, a), (line_no, b) = variants[i], variants[j]
                ca, cb = _subject_content(a), _subject_content(b)
                sim = _similarity(ca, cb)
                if sim >= VARIANT_SIMILARITY:
                    violations.append(_v(
                        "SL-6", "subject options are distinct angles", HARD,
                        section.section_id, line_no, b,
                        f"This subject is a paraphrase of `{ca}` ({int(sim * 100)}% of the content "
                        f"words are shared). Offering the same line twice is a fake choice, and it "
                        f"gives an A/B test nothing to learn from.",
                        "Take a genuinely different angle: one leads with the result, one with the "
                        "story, one with the objection or the contrarian claim.",
                    ))
    return violations


# ---------------------------------------------------------------------------
# SL-7 / SL-8 / SL-9 · the bracketed workshop tag
#
# `**Subject:** [Volume Eating Workshop] Your spot's almost confirmed`
#
# The tag groups the campaign in a crowded inbox. It is written down in
# references/craft/email-sms-output-formatting.md F-2 ("use the same bracket tag consistently
# across all emails in the same sequence") and has never been enforced.
#
# NOTE — the repo used to contradict itself here. email-sequence/workflow.md:358 said the prefix
# went on "the first 2 emails of a sequence"; the formatting rule said every email. No shipped
# bundle has ever followed the first-2 version. Resolved by operator call (Lauren, 2026-07-13):
# EVERY email in a pre-webinar or replay sequence carries the tag. The stale line is retired.
#
# Post-booking sequences (book-call, appointment nurture, strategy-session reminders) carry NO
# tag — by then the reader is a booked lead, not a workshop registrant.
# ---------------------------------------------------------------------------

TAG_RE = re.compile(r"^\s*\[(?P<tag>[^\]]+)\]")

# Sequences whose emails must carry the tag.
TAGGED_SEQUENCE_RE = re.compile(r"pre-?webinar|\bwebinar\b|\breplay\b|show-?up|organic", re.I)
# Sequences that must not be required to.
UNTAGGED_SEQUENCE_RE = re.compile(
    r"book\s*call|post-?booking|strategy\s+session|appointment|nurture|reminder|pre-?call", re.I
)
REPLAY_SEQUENCE_RE = re.compile(r"\breplay\b", re.I)


def _sequence_titles(bundle: ParsedBundle) -> dict:
    """{sequence number: header title}"""
    return {
        s.sequence: (s.description or "")
        for s in bundle.sections
        if s.section_type == "sequence_header"
    }


def _tag_of(subject: str) -> Optional[str]:
    m = TAG_RE.match(subject or "")
    return m.group("tag").strip() if m else None


def _base_tag(tag: str) -> str:
    """`Volume Eating Workshop · Replay` -> `volume eating workshop`."""
    return re.split(r"[·|]", tag)[0].strip().lower()


def _sequence_requires_tag(title: str) -> bool:
    if UNTAGGED_SEQUENCE_RE.search(title):
        return False
    return bool(TAGGED_SEQUENCE_RE.search(title))


def check_sl7_workshop_tag(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Every email in a pre-webinar or replay sequence carries the bracketed workshop tag."""
    violations = []
    titles = _sequence_titles(bundle)
    for section in bundle.emails:
        title = titles.get(section.sequence, "")
        if not _sequence_requires_tag(title):
            continue
        for line_no, subject in S.subject_variants(section):
            if _tag_of(subject):
                continue
            violations.append(_v(
                "SL-7", "workshop tag on the subject", HARD,
                section.section_id, line_no, subject,
                f"No bracketed workshop tag. Every email in the `{title.strip()}` sequence carries "
                f"it — that's what groups the campaign in a crowded inbox. Dropping it on one email "
                f"breaks the thread the reader has been following.",
                "Prefix the subject: `[Volume Eating Workshop] …`. The tag doesn't count toward the "
                "7-word limit.",
            ))
    return violations


def check_sl8_tag_consistency(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """The same tag, spelled the same way, across the whole bundle.

    A tag that changes spelling mid-sequence stops grouping the campaign and starts looking like
    two campaigns.
    """
    violations = []
    seen = {}  # base tag -> first (line_no, tag)
    for section in bundle.emails:
        for line_no, subject in S.subject_variants(section):
            tag = _tag_of(subject)
            if not tag:
                continue
            base = _base_tag(tag)
            if base not in seen:
                seen[base] = (line_no, tag, section.section_id)

    if len(seen) <= 1:
        return violations

    canonical = min(seen.values(), key=lambda t: t[0])
    for base, (line_no, tag, section_id) in seen.items():
        if base == _base_tag(canonical[1]):
            continue
        violations.append(_v(
            "SL-8", "tag consistent across the bundle", HARD,
            section_id, line_no, f"[{tag}]",
            f"Workshop tag `{tag}` doesn't match `{canonical[1]}`, used earlier in the bundle. One "
            f"campaign, one tag — a tag that changes spelling stops grouping the thread and starts "
            f"looking like a second campaign.",
            f"Use `[{canonical[1]}]` throughout, or fix the first one if this is the correct name.",
        ))
    return violations


def check_sl9_replay_suffix(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Replay-sequence emails mark the tag as a replay: `[Workshop · Replay]`.

    YELLOW — the suffix is a convention in the formatting rules, not a stated hard gate.
    """
    violations = []
    titles = _sequence_titles(bundle)
    for section in bundle.emails:
        title = titles.get(section.sequence, "")
        if not REPLAY_SEQUENCE_RE.search(title):
            continue
        for line_no, subject in S.subject_variants(section):
            tag = _tag_of(subject)
            if not tag or REPLAY_SEQUENCE_RE.search(tag):
                continue
            violations.append(_v(
                "SL-9", "replay tag carries the Replay suffix", YELLOW,
                section.section_id, line_no, subject,
                f"Replay-sequence email tagged `[{tag}]` rather than `[{tag} · Replay]`. The other "
                f"emails in this sequence mark the replay; this one doesn't, so it reads as part of "
                f"the live campaign.",
                f"Use `[{tag} · Replay]`.",
            ))
    return violations


# ---------------------------------------------------------------------------
# TL-6 · one workshop name, spelled the same way everywhere
#
# The workshop name is load-bearing: it is the reg-page headline, the deck title slide, and the
# `[Bracket]` subject prefix. If those three drift apart, the reader who registered for one thing
# arrives at another. Nothing enforced this.
# ---------------------------------------------------------------------------

# "Workshop" and "Masterclass" name the EVENT. "Training" does not — it is a brand-house word
# ("Ransomed Bodies Training"), and including it made the company name read as a second workshop.
WORKSHOP_NAME_RE = re.compile(r"\b([A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*){0,3})\s+(Workshop|Masterclass)\b")

# Words that get title-cased in a heading but aren't part of the name.
NAME_STOPWORDS = {"the", "a", "an", "free", "live", "this", "our", "my", "your", "join", "new"}


def _workshop_names(bundle: ParsedBundle) -> dict:
    """Every distinct workshop name used in the doc -> first (line_no, full name)."""
    found = {}
    for idx, line in enumerate(bundle.raw_lines):
        for m in WORKSHOP_NAME_RE.finditer(line):
            words = [w for w in m.group(1).split() if w.lower() not in NAME_STOPWORDS]
            if not words:
                continue
            name = " ".join(words)
            key = name.lower()
            if key not in found:
                found[key] = (idx + 1, f"{name} {m.group(2)}")
    return found


def check_tl6_one_workshop_name(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """One deliverable, one workshop name.

    HARD when the doc uses two different names for the same workshop. YELLOW when the name
    doesn't match the client's canonical mechanism — that may be a deliberate rebrand, so it
    warns rather than blocks.
    """
    violations = []
    names = _workshop_names(bundle)
    if not names:
        return violations

    if len(names) > 1:
        canonical_line, canonical = min(names.values(), key=lambda t: t[0])
        for key, (line_no, name) in names.items():
            if name == canonical:
                continue
            violations.append(_v(
                "TL-6", "one workshop name", HARD, "document", line_no, name,
                f"This deliverable uses two workshop names: `{canonical}` and `{name}`. The name is "
                f"the reg-page headline, the deck title slide, and the subject prefix — if they "
                f"drift, the reader registers for one thing and arrives at another.",
                f"Pick one. Use `{canonical}` throughout, or fix the first mention.",
            ))
        return violations

    # Single name — check it against the client's canonical mechanism, if one is declared.
    client = ctx.get("client_data")
    canonical_mech = getattr(client, "mechanism_source_of_truth", None) if client else None
    if not canonical_mech:
        return violations
    (line_no, name) = next(iter(names.values()))
    if canonical_mech.lower() not in name.lower():
        violations.append(_v(
            "TL-6", "one workshop name", YELLOW, "document", line_no, name,
            f"Workshop is called `{name}`, but the client's canonical mechanism is "
            f"`{canonical_mech}` (clients/{getattr(client, 'slug', '?')}/term-mappings.json). If this "
            f"is a deliberate rebrand, update term-mappings so the two stop disagreeing.",
            f"Align the name with `{canonical_mech}`, or update the canonical record.",
        ))
    return violations


# ---------------------------------------------------------------------------
# PH · preview text
# ---------------------------------------------------------------------------


def check_ph1_preheader_exists(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Every email declares preview text.

    The strongest-evidenced rule in the set, because it rests on how mail clients actually
    BEHAVE, not on a contested open-rate stat. If the preview slot is empty, Gmail and Apple
    backfill it from your email body — Litmus documents "View this email in your browser",
    unsubscribe text, and image alt-text landing in the inbox next to your subject line.
    """
    violations = []
    for section in bundle.emails:
        if _preheader_of(section):
            continue
        violations.append(_v(
            "PH-1", "preview text present", HARD,
            section.section_id, section.start_line, section.subject or section.section_id,
            "No preview text. The inbox will backfill the slot from the email body — readers see "
            "`View this email in your browser` or `unsubscribe` sitting next to your subject line.",
            "Add `**Preview text:** ...` (40-90 chars) that extends the subject rather than repeating it.",
        ))
    return violations


def check_ph2_preheader_length(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for section in bundle.emails:
        found = _preheader_of(section)
        if not found:
            continue  # PH-1 owns the missing case
        line_no, text = found
        n = len(text)
        if n < PREHEADER_MIN_CHARS:
            violations.append(_v(
                "PH-2", "preview text 40-90 chars", HARD,
                section.section_id, line_no, text,
                f"Preview text is {n} chars. Below {PREHEADER_MIN_CHARS} the client backfills the "
                f"remaining space from your email body, which is how `View in browser` ends up in "
                f"the inbox.",
                f"Extend to {PREHEADER_MIN_CHARS}-{PREHEADER_MAX_CHARS} chars.",
            ))
        elif n > PREHEADER_HARD_MAX:
            violations.append(_v(
                "PH-2", "preview text 40-90 chars", HARD,
                section.section_id, line_no, text,
                f"Preview text is {n} chars. Outlook shows about 35-55, most phones 40-90. Past "
                f"{PREHEADER_HARD_MAX} it is dead weight nobody reads.",
                f"Cut to {PREHEADER_MAX_CHARS} chars or fewer, with the message in the first 40.",
            ))
        elif n > PREHEADER_MAX_CHARS:
            violations.append(_v(
                "PH-2", "preview text 40-90 chars", YELLOW,
                section.section_id, line_no, text,
                f"Preview text is {n} chars, over the {PREHEADER_MAX_CHARS}-char target. It will be "
                f"truncated everywhere except macOS Mail.",
                f"Tighten toward {PREHEADER_MAX_CHARS} chars.",
            ))
    return violations


def check_ph3_no_subject_duplication(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Preview text complements the subject. It never repeats it.

    Subject and preview are two separate pieces of inbox real estate. Restating the subject
    burns the second one for zero information gain. Caples' rule — curiosity plus self-interest
    — is best served by splitting it across the two: subject hooks, preview pays.
    """
    violations = []
    for section in bundle.emails:
        found = _preheader_of(section)
        if not found:
            continue
        line_no, text = found
        if not text:
            continue
        # Compared against its PAIRED subject. Now that each subject has its own preview
        # (PH-5), comparing preview A against subject B is meaningless — B is a deliberately
        # different angle, and preview A is allowed to echo it.
        subjects = [_subject_content(s) for _, s in S.subject_variants(section) if _subject_content(s)]
        if not subjects:
            continue
        previews = S.preview_variants(section)
        idx = next((i for i, (ln, _, _) in enumerate(previews) if ln == line_no), 0)
        subject = subjects[idx] if idx < len(subjects) else subjects[0]
        overlap = _overlap(subject, text)
        if overlap >= SUBJECT_PREHEADER_OVERLAP:
            violations.append(_v(
                "PH-3", "preview text does not repeat subject", HARD,
                section.section_id, line_no, text,
                f"Preview text restates the subject ({int(overlap * 100)}% of the subject's words are "
                f"repeated in it). Subject: `{subject}`. The preview is the second-biggest piece of "
                f"inbox space you own — it should add the proof, the objection killer, or the "
                f"specific. Not an echo.",
                "Make the preview earn its place. Subject hooks, preview pays it off.",
            ))
    return violations


def check_ph4_no_leaked_boilerplate(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for section in bundle.emails:
        found = _preheader_of(section)
        if not found:
            continue
        line_no, text = found
        m = LEAKED_BOILERPLATE_RE.search(text)
        if m:
            violations.append(_v(
                "PH-4", "no boilerplate in preview text", HARD,
                section.section_id, line_no, text,
                f"`{m.group(0)}` in the preview text. This is the template's plumbing leaking into "
                f"the inbox.",
                "Write real preview copy.",
            ))
    return violations




# ---------------------------------------------------------------------------
# PH-5 · one preview text per subject variant
#
# Subject and preview are a two-part pitch: the subject hooks, the preview pays it off. A single
# shared preview written against subject A rarely lands under subject C — the pairing is the point.
# (Lauren, 2026-07-13.)
# ---------------------------------------------------------------------------


def check_ph5_preview_per_variant(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for section in bundle.emails:
        subjects = S.subject_variants(section)
        previews = S.preview_variants(section)
        if not subjects or not previews:
            continue  # PH-1 / SL-5 own the missing cases
        if len(previews) == len(subjects):
            continue
        violations.append(_v(
            "PH-5", "one preview per subject", HARD,
            section.section_id, previews[0][0], f"({len(subjects)} subjects, {len(previews)} previews)",
            f"{len(subjects)} subject options but {len(previews)} preview text(s). Each subject needs "
            f"its own preview — the two are a two-part pitch, and a preview written for subject A "
            f"rarely pays off subject C.",
            "Write `**Subject A:** / **Preview A:**`, `**Subject B:** / **Preview B:**`, and so on.",
        ))
    return violations


# ---------------------------------------------------------------------------
# PH-6 · subject/preview variants are paired and grouped
#
# Format the options so the operator reads them as pairs — each subject on its own line, its
# preview directly under it, and a blank line between the groups:
#
#     **Subject A:** ...
#     **Preview A:** ...
#
#     **Subject B:** ...
#     **Preview B:** ...
#
# YELLOW — a readability/layout standard. PH-5 owns the harder "one preview per subject" count and
# SL-5 owns "2-3 options"; this only governs how they're laid out. Scans raw lines directly so the
# parser lifting the first subject onto the header line doesn't confuse the pairing.
# ---------------------------------------------------------------------------


def check_ph6_subject_preview_layout(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for section in bundle.emails:
        lo, hi = max(section.start_line - 1, 0), min(section.end_line, len(bundle.raw_lines))
        markers = []  # (line_no, "S" | "P")
        for i in range(lo, hi):
            content = bundle.raw_lines[i]
            if S.SUBJECT_VARIANT_RE.match(content):
                markers.append((i + 1, "S"))
            elif S.PREVIEW_VARIANT_RE.match(content):
                markers.append((i + 1, "P"))
        if sum(1 for _, k in markers if k == "S") < 2:
            continue  # single subject, or subject inline on the header — SL-5 / PH-5 own those

        for idx, (ln, kind) in enumerate(markers):
            if kind != "S":
                continue
            if idx + 1 >= len(markers) or markers[idx + 1][1] != "P":
                violations.append(_v(
                    "PH-6", "subject/preview paired and grouped", YELLOW, section.section_id, ln,
                    bundle.raw_lines[ln - 1].strip()[:80],
                    "This subject isn't followed by its own preview. Format the options as pairs: each "
                    "subject on one line, its preview on the next, a blank line between groups.",
                    "Put `**Preview X:**` directly under `**Subject X:**`, then a blank line before the next.",
                ))
                continue
            if markers[idx + 1][0] != ln + 1:
                violations.append(_v(
                    "PH-6", "subject/preview paired and grouped", YELLOW, section.section_id, ln,
                    bundle.raw_lines[ln - 1].strip()[:80],
                    "Subject and its preview should sit on consecutive lines, grouped — no gap between a "
                    "subject and its own preview.",
                    "Move the preview directly under its subject.",
                ))

        for idx in range(len(markers) - 1):
            (ln, kind), (nxt_ln, nxt_kind) = markers[idx], markers[idx + 1]
            if kind == "P" and nxt_kind == "S":
                if not any(not b.strip() for b in bundle.raw_lines[ln:nxt_ln - 1]):
                    violations.append(_v(
                        "PH-6", "subject/preview paired and grouped", YELLOW, section.section_id, nxt_ln,
                        bundle.raw_lines[nxt_ln - 1].strip()[:80],
                        "No blank line between subject/preview groups. Put an empty line between each pair "
                        "so the operator can scan them.",
                        "Add a blank line between the groups.",
                    ))
    return violations


# ---------------------------------------------------------------------------
# TL · titles and headlines
#
# The title carries the promise; the body carries the voice.
# ---------------------------------------------------------------------------


def _titles(bundle: ParsedBundle, ctx: dict) -> List[Tuple[int, str, str]]:
    """The headline artifacts this asset owns. -> [(line_no, label, text)]"""
    out = []
    if S.is_capture(bundle.raw_lines):
        return out  # a capture records a title that already ran; we do not re-grade it
    asset = ctx.get("asset_type")

    if asset == "webinar_deck":
        from skills.copywriting.auditor.rules import webinar_deck as wd
        for slide in wd._slides(bundle):
            if re.search(r"\btitle\b", slide.tag, re.I) and slide.headline:
                out.append((slide.headline_line, f"Slide {slide.number} title", slide.headline))

    elif asset == "funnel_pages":
        from skills.copywriting.auditor.rules import funnel_pages as fpm
        page = fpm._page(bundle, "registration")
        if page:
            for line_no, content in page.lines:
                m = re.match(r"^\s*\**\s*headline\s*:?\**\s*(?P<text>.+?)\s*$", content, re.I)
                if m:
                    out.append((line_no, "Registration hero headline", m.group("text").strip()))
                    break

    elif asset == "image_ads":
        from skills.copywriting.auditor.rules import image_ads as ia
        for line_no, label, headline, _sub in ia.headline_units(bundle):
            out.append((line_no, label, headline))
    return out


# A registration hero can carry a sub-headline directly under the headline; the deck title
# slide carries a `Sub-headline:` line. TL-9 grades the two together as one title UNIT, so the
# unit helper returns the subtitle alongside the headline. The line-level TL checks
# (TL-1..TL-5, TL-7) keep using `_titles` and stay headline-only — those rules grade the
# headline line itself, not the promise as a whole.
_FUNNEL_SUBHEAD_RE = re.compile(
    r"^\s*\**\s*sub[-\s]?headline\s*:?\**\s*(?P<text>.+?)\s*$", re.I
)


def _title_units(bundle: ParsedBundle, ctx: dict) -> List[Tuple[int, str, str, str]]:
    """Title + its subtitle, for the unit-level judge. -> [(line_no, label, headline, subtitle)]"""
    out = []
    if S.is_capture(bundle.raw_lines):
        return out
    asset = ctx.get("asset_type")

    if asset == "webinar_deck":
        from skills.copywriting.auditor.rules import webinar_deck as wd
        for slide in wd._slides(bundle):
            if re.search(r"\btitle\b", slide.tag, re.I) and slide.headline:
                out.append((slide.headline_line, f"Slide {slide.number} title",
                            slide.headline, slide.subhead))

    elif asset == "funnel_pages":
        from skills.copywriting.auditor.rules import funnel_pages as fpm
        page = fpm._page(bundle, "registration")
        if page:
            headline = None
            for line_no, content in page.lines:
                if headline is None:
                    m = re.match(r"^\s*\**\s*headline\s*:?\**\s*(?P<text>.+?)\s*$", content, re.I)
                    if m:
                        headline = (line_no, "Registration hero headline", m.group("text").strip())
                    continue
                # First sub-headline after the headline is the unit's subtitle.
                sm = _FUNNEL_SUBHEAD_RE.match(content)
                if sm:
                    out.append((*headline, sm.group("text").strip()))
                    headline = None
                    break
            if headline is not None:
                out.append((*headline, ""))

    elif asset == "image_ads":
        from skills.copywriting.auditor.rules import image_ads as ia
        for line_no, label, headline, subhead in ia.headline_units(bundle):
            out.append((line_no, label, headline, subhead))
    return out


def check_tl1_ultra_specific(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """A title names a number, an audience, or a timeframe.

    4 U's: Ultra-specific. Caples: self-interest and news. Hopkins: the headline's job is to
    "pick out people you can interest" — it cannot pick anyone out if it names nobody and
    promises nothing measurable.

    HARD, by operator call (Lauren, 2026-07-13).

    This rule fails the Lauren-PASS Erinne anchor — "How to Cross the Finish Line, Without More
    Miles" — which names no number, no audience, and no timeframe. That is not a false positive.
    The title genuinely doesn't say who it's for, and the fix is one word: "How TRIATHLETES Cross
    the Finish Line Without More Miles". The anchor gets rewritten; the rule stands.
    """
    violations = []
    for line_no, label, text in _titles(bundle, ctx):
        if (TITLE_NUMBER_RE.search(text) or TITLE_AUDIENCE_RE.search(text)
                or TITLE_TIMEFRAME_RE.search(text)):
            continue
        violations.append(_v(
            "TL-1", "title is ultra-specific", HARD, label, line_no, text,
            "Title names no number, no audience, and no timeframe, so it makes a promise nobody can "
            "size. A headline's job is to pick out the people you can interest — this one picks out "
            "nobody. Voice does not qualify a reader; specificity does.",
            "Add at least one: a number (`3,300 women`), a named audience (`for women over 40`), "
            "or a timeframe (`in 30 days`).",
        ))
    return violations


# ---------------------------------------------------------------------------
# TL-7 · the title names the audience's OWN desire
#
# TL-1 checks that a title names *a* desire. It cannot tell whether that desire is *theirs*.
#
# The rule exists because of a real miss. Erinne's deck was titled "How to Cross the Finish
# Line, Without More Miles". Her avatar is "The Time-Starved Professional Triathlete" —
# attorneys and physicians with kids, who already finish races. Finishing is a desire they
# solved years ago. What they actually want is to get FASTER without surrendering more hours,
# which is what the deck itself argues ("It's the Order, Not the Hours", "You Don't Need 20
# Hours a Week"). The title named an outcome nobody in the room wanted, and passed every
# mechanical check while doing it.
#
# HONEST LIMIT: this is a lexical proxy, not comprehension. It checks that the title shares
# vocabulary with the declared desire. A title could share a word and still miss the desire,
# and the auditor cannot tell. What it CAN do is stop a writer inventing a desire the client
# record does not support — which is the failure that actually happened.
# ---------------------------------------------------------------------------

DESIRE_STOPWORDS = STOPWORDS | {
    "without", "more", "less", "keep", "off", "and", "or", "not", "their", "them", "on", "up",
}


def check_tl7_names_their_desire(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    client = ctx.get("client_data")
    desire = getattr(client, "primary_desire", None) if client else None
    titles = _titles(bundle, ctx)
    if not titles:
        return []

    if not desire:
        line_no, label, text = titles[0]
        return [_v(
            "TL-7", "title names their desire", YELLOW, label, line_no, text,
            "This client declares no primary desire, so the auditor cannot check that the title "
            "names the outcome the audience actually wants. Without it, a title can promise "
            "something the avatar solved years ago and still pass every other rule.",
            "Add `avatar_snapshot.primary_desire` to clients/<slug>/info.json, sourced from the "
            "Target Audience Brief.",
        )]

    desire_words = {w for w in _content_words(desire) if w not in DESIRE_STOPWORDS}
    violations = []
    for line_no, label, text in titles:
        title_words = _content_words(text)
        if desire_words & title_words:
            continue
        violations.append(_v(
            "TL-7", "title names their desire", HARD, label, line_no, text,
            f"The title shares no language with what this audience actually wants: "
            f"\"{desire}\". A headline's job is to pick out the people you can interest, and it "
            f"cannot do that by promising an outcome they are not chasing.",
            f"Rewrite the promise around their desire. Their words: "
            f"{', '.join(sorted(desire_words)[:8])}.",
        ))
    return violations


def check_tl2_outcome_verb(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """A title with no verb is a topic label, not a promise.

    `Metabolic Fuel Workshop` is a label — it tells the reader nothing about what changes.
    `How Women Over 40 Lose Weight By Eating More` is a headline.

    Scope: this check grades the VERB only. The doc's TL-2 also asks for a *tangible result*
    attached to the verb (`How to Optimize Your Metabolism` has a verb, no result) — but
    "tangible" is a meaning call, not a pattern, so that half is enforced by the SEM-TL8 judge
    (TL-9), not here. See semantic.py and references/craft/headline-and-subject-rules.md.
    """
    violations = []
    # On an image ad this is ADVISORY, not a gate. The verb-presence proxy is too crude for an ad
    # headline, where a vivid noun-phrase result ("a new title and a $25,000 raise") carries the
    # promise with no verb at all. Whether the headline names a tangible result is the SEM-TL8
    # (TL-9) judge's call for image ads; here it is only a flag. It stays HARD for a webinar title
    # or reg-page hero, where a verbless line really is a topic label.
    is_ad = ctx.get("asset_type") == "image_ads"
    severity = YELLOW if is_ad else HARD
    for line_no, label, text in _titles(bundle, ctx):
        # A "How to X" / "How <audience> X" frame guarantees a verb by grammar. No lexicon can be
        # complete, so check the construction first and only fall back to the word list.
        if HOW_TO_FRAME_RE.search(text) or OUTCOME_VERB_RE.search(text):
            continue
        if is_ad:
            message = (
                "Headline carries no outcome verb — it may be naming a topic rather than a change. "
                "Advisory for an image ad: a vivid noun-phrase result (`a new title and a $25,000 "
                "raise`) can still carry the promise, so this is a flag to check, not a block. "
                "Whether the headline names a tangible result is graded by SEM-TL8 (TL-9)."
            )
            fix = "Confirm the headline names a concrete result, in the headline or its paired subhead."
        else:
            message = (
                "Title has no outcome verb, which makes it a topic label rather than a promise. "
                "`Metabolic Fuel Workshop` says what the thing is called. It never says what changes "
                "for the reader."
            )
            fix = "Name the outcome: `How Women Over 40 Lose Weight By Eating More, Not Less`."
        violations.append(_v(
            "TL-2", "title carries an outcome verb", severity, label, line_no, text, message, fix,
        ))
    return violations


def check_tl3_no_shouting(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for line_no, label, text in _titles(bundle, ctx):
        caps = _caps_violations(text)
        if caps:
            violations.append(_v(
                "TL-3", "no shouting in the title", HARD, label, line_no, text,
                f"ALL-CAPS word(s) in the title: {', '.join(caps)}. A title asks for a calendar "
                f"commitment. Shouting reads as low-status and undercuts the promise.",
                "Use sentence or title case.",
            ))
        if "!" in text:
            violations.append(_v(
                "TL-3", "no shouting in the title", HARD, label, line_no, text,
                "Exclamation mark in the title. The specificity should carry the energy.",
                "Cut the exclamation mark.",
            ))
    return violations


def check_tl4_word_band(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """6 to 14 words. YELLOW — the sources for this band are practitioner heuristics that don't
    fully agree with each other, so it is a flag to check, not a blocker.
    """
    violations = []
    low, high = TITLE_WORD_BAND
    for line_no, label, text in _titles(bundle, ctx):
        n = len(S.strip_markdown(text).split())
        if low <= n <= high:
            continue
        violations.append(_v(
            "TL-4", "title 6-14 words", YELLOW, label, line_no, text,
            f"Title is {n} words, outside the {low}-{high} band. Under {low} it usually can't carry a "
            f"specific promise; over {high} it stops working as an ad headline and a page H1.",
            f"Aim for {low}-{high} words.",
        ))
    return violations


def check_tl5_no_vagueness(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for line_no, label, text in _titles(bundle, ctx):
        m = TITLE_VAGUE_RE.search(text)
        if m:
            violations.append(_v(
                "TL-5", "no vague filler in the title", YELLOW, label, line_no, text,
                f"`{m.group(0)}` is filler. It signals a topic without making a promise, and generic "
                f"marketing language is consistently the worst-performing category.",
                "Replace it with the actual outcome.",
            ))
    return violations


RULES = [
    Rule(id="SL-1", name="subject leads with the payload",   severity=HARD,   layer=LAYER, check=check_sl1_no_filler_opener,      applies_to=EMAIL_ASSETS),
    Rule(id="SL-2", name="subject front-loaded",             severity=YELLOW, layer=LAYER, check=check_sl2_frontload,             applies_to=EMAIL_ASSETS),
    Rule(id="SL-3", name="no shouting in the subject",       severity=HARD,   layer=LAYER, check=check_sl3_shouting,              applies_to=EMAIL_ASSETS),
    Rule(id="SL-4", name="no fake Re:/Fwd: prefix",          severity=HARD,   layer=LAYER, check=check_sl4_fake_reply,            applies_to=EMAIL_ASSETS),
    Rule(id="SL-5", name="2-3 subject line options",         severity=HARD,   layer=LAYER, check=check_sl5_variant_count,         applies_to=EMAIL_ASSETS),
    Rule(id="SL-6", name="subject options are distinct",     severity=HARD,   layer=LAYER, check=check_sl6_variants_are_distinct, applies_to=EMAIL_ASSETS),
    Rule(id="SL-7", name="workshop tag on the subject",      severity=HARD,   layer=LAYER, check=check_sl7_workshop_tag,          applies_to=EMAIL_ASSETS),
    Rule(id="SL-8", name="tag consistent across bundle",     severity=HARD,   layer=LAYER, check=check_sl8_tag_consistency,       applies_to=EMAIL_ASSETS),
    Rule(id="SL-9", name="replay tag carries · Replay",      severity=YELLOW, layer=LAYER, check=check_sl9_replay_suffix,         applies_to=EMAIL_ASSETS),
    Rule(id="PH-1", name="preview text present",             severity=HARD,   layer=LAYER, check=check_ph1_preheader_exists,      applies_to=EMAIL_ASSETS),
    Rule(id="PH-2", name="preview text 40-90 chars",         severity=HARD,   layer=LAYER, check=check_ph2_preheader_length,      applies_to=EMAIL_ASSETS),
    Rule(id="PH-3", name="preview doesn't repeat subject",   severity=HARD,   layer=LAYER, check=check_ph3_no_subject_duplication, applies_to=EMAIL_ASSETS),
    Rule(id="PH-4", name="no boilerplate in preview text",   severity=HARD,   layer=LAYER, check=check_ph4_no_leaked_boilerplate, applies_to=EMAIL_ASSETS),
    Rule(id="PH-5", name="one preview per subject",          severity=HARD,   layer=LAYER, check=check_ph5_preview_per_variant,   applies_to=EMAIL_ASSETS),
    Rule(id="PH-6", name="subject/preview paired and grouped", severity=YELLOW, layer=LAYER, check=check_ph6_subject_preview_layout, applies_to=EMAIL_ASSETS),
    Rule(id="TL-1", name="title is ultra-specific",          severity=HARD,   layer=LAYER, check=check_tl1_ultra_specific,        applies_to=TITLE_ASSETS),
    Rule(id="TL-2", name="title carries an outcome verb",    severity=HARD,   layer=LAYER, check=check_tl2_outcome_verb,          applies_to=TITLE_PLUS_ADS),
    Rule(id="TL-3", name="no shouting in the title",         severity=HARD,   layer=LAYER, check=check_tl3_no_shouting,           applies_to=TITLE_PLUS_ADS),
    Rule(id="TL-4", name="title 6-14 words",                 severity=YELLOW, layer=LAYER, check=check_tl4_word_band,             applies_to=TITLE_ASSETS),
    Rule(id="TL-5", name="no vague filler in the title",     severity=YELLOW, layer=LAYER, check=check_tl5_no_vagueness,          applies_to=TITLE_PLUS_ADS),
    Rule(id="TL-6", name="one workshop name",                severity=HARD,   layer=LAYER, check=check_tl6_one_workshop_name,     applies_to=APPLIES_TO),
    Rule(id="TL-7", name="title names their desire",         severity=HARD,   layer=LAYER, check=check_tl7_names_their_desire,    applies_to=TITLE_ASSETS),
]
