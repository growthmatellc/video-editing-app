"""funnel_pages.py — FP-1 to FP-14 · the 4-page funnel deliverable.

Encodes Lauren's 10 funnel-page rules and the locked page contracts. Every rule is
ported from a written source; the citation is on each check function. Sources:

  references/craft/funnel-and-email-rules-lauren.md  (§A.1 8-section order, §G.2 forbidden
                                                      phrases, §G.4 proof, §G.5 4-page contract)
  skills/funnel-copy/funnel-pages/workflow.md        (Lauren's rules, locked page blocks,
                                                      Rule 11 section-headline rule, the
                                                      self-check scan lists)

The rules that need human or LLM judgment — "bullets anchored in lived experience",
"headline self-explanatory on first read", "pattern-match the approved anchors" — are
deliberately NOT here. A regex can't grade them, and a check that pretends to would be
worse than no check. They stay in the workflow checklist and the semantic layer.

Where sales language is allowed, per page (Lauren, 2026-07-13):

  Registration           FORBIDDEN. Its only job is winning the registration.
  Webinar Confirmation   allowed — post-conversion, the reader has to know the next step.
  Replay                 allowed in the CTA block above the typeform; flagged elsewhere.
  Book Call Confirmation allowed — that page IS the call close.
"""

from __future__ import annotations

import re
from typing import List, Optional

from skills.copywriting.auditor.lib.parser import ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation
from skills.copywriting.auditor.lib import sections as S


LAYER = "FunnelPages"
APPLIES_TO = {"funnel_pages"}


PAGE_LABELS = {
    "registration": "Registration",
    "webinar_confirmation": "Webinar Confirmation",
    "replay": "Replay",
    "book_call_confirmation": "Book Call Confirmation",
}
PAGE_ORDER = ("registration", "webinar_confirmation", "replay", "book_call_confirmation")

# Page headers. Book-call is matched first — its heading also contains "confirmation".
PAGE_PATTERNS = [
    ("book_call_confirmation", re.compile(r"\b(?:call[-\s]?booking|book(?:ing)?[-\s]?(?:a[-\s]?)?call)\b", re.I)),
    ("webinar_confirmation", re.compile(r"\bwebinar\s+confirmation\b|\bconfirmation\s+page\b", re.I)),
    ("replay", re.compile(r"\breplay\b", re.I)),
    ("registration", re.compile(r"\bopt[-\s]?in\b|\bregistration\b|\blanding\s+page\b", re.I)),
]


def _page_classifier(title: str) -> Optional[str]:
    for key, pattern in PAGE_PATTERNS:
        if pattern.search(title):
            return key
    return None


def _pages(bundle: ParsedBundle) -> List[S.Section]:
    return S.split_sections(bundle.raw_lines, _page_classifier)


def _page(bundle: ParsedBundle, key: str) -> Optional[S.Section]:
    for s in _pages(bundle):
        if s.key == key:
            return s
    return None


def _blocks_in(page: S.Section) -> List[tuple]:
    """Sub-headings and bolded block labels inside a page, in order. -> [(line_no, label)]

    A block label may be bulleted (`- **Step 1: Watch This Video**`) or numbered. Requiring the
    line to START with `**` missed every step on Trent's confirmation pages and reported the steps
    as absent when they were right there.
    """
    out = []
    for line_no, content in page.lines:
        m = S.HEADER_RE.match(content)
        if m:
            out.append((line_no, m.group("title").strip()))
            continue
        # `**Headline:**`, `- **Step 1: …**`, `1. **Proof:**`
        #
        # A bolded run inside a LIST item is only a block label if it actually carries a colon.
        # Without that guard, `1. **What if I cannot make it live?**` (an FAQ question) and
        # `1. **Mary** — [PHOTO…]` (a proof card) both register as new blocks, which truncates
        # the section they belong to. That made the registration FAQ report zero questions when
        # it had four.
        m = re.match(r"^\s*(?P<lead>[-•*]\s+|\d+[.)]\s+)?\*\*(?P<label>[^*]{2,80}?)\*\*", content.strip())
        if m:
            label = m.group("label").strip()
            if m.group("lead") and ":" not in label:
                continue  # a list item, not a block label
            out.append((line_no, label.split(":")[0].strip()))
    return out


def _has_block(page: S.Section, pattern: str) -> bool:
    rx = re.compile(pattern, re.I)
    return any(rx.search(label) for _, label in _blocks_in(page))


def _v(rule_id, rule_name, severity, page_or_id, line_no, line, message, fix) -> Violation:
    return Violation(
        rule_id=rule_id, rule_name=rule_name, severity=severity,
        section_id=page_or_id, line_no=line_no, line_content=line,
        message=message, fix_hint=fix,
    )


# ---------------------------------------------------------------------------
# FP-0 · the document actually parses
#
# If no pages are recognised, every other FP rule passes on an empty list and the auditor
# prints "ship clear" for a file it never read. A gate that blesses what it can't parse
# manufactures false confidence. Zero pages is a HARD failure, never a silent pass.
# ---------------------------------------------------------------------------


def check_fp0_parseable(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if _pages(bundle):
        return []
    return [_v(
        "FP-0", "document parses", HARD, "document", 1, "(0 funnel pages parsed)",
        "No funnel pages could be parsed, so no funnel rule was actually evaluated. The auditor "
        "will not pass a file it cannot read. Expected page headers like `# Page 1 — Registration`.",
        "Fix the page headers, or extend the parser if this is a new format.",
    )]


# ---------------------------------------------------------------------------
# FP-1 · 4-page deliverable complete
#   workflow.md:155 "A complete funnel-pages deliverable means all 4 pages"
#   workflow.md:157 "No partial wins. If you can only produce 3 of 4 pages, the
#                    deliverable is BLOCKED, not done."
# ---------------------------------------------------------------------------

BLOCKED_HEADER_RE = re.compile(r"^\s*#*\s*\**\s*BLOCKED\b", re.I | re.M)


def check_fp1_four_pages(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    found = {p.key for p in _pages(bundle)}
    missing = [p for p in PAGE_ORDER if p not in found]
    if not missing:
        return []
    # A partial delivery may ship IF it carries a BLOCKED header naming the gap.
    if BLOCKED_HEADER_RE.search(bundle.raw_text):
        return [_v(
            "FP-1", "4-page funnel deliverable", YELLOW, "deliverable", 1,
            f"(missing: {', '.join(PAGE_LABELS[p] for p in missing)})",
            f"Deliverable is {4 - len(missing)} of 4 pages, but carries a BLOCKED header — "
            f"flagged, not silently dropped. Confirm the gap is real before shipping.",
            "Unblock the missing page(s), or confirm the BLOCKED header names the reason.",
        )]
    return [_v(
        "FP-1", "4-page funnel deliverable", HARD, "deliverable", 1,
        f"(missing: {', '.join(PAGE_LABELS[p] for p in missing)})",
        f"Missing the {', '.join(PAGE_LABELS[p] for p in missing)} page(s). A complete funnel "
        f"deliverable is all 4 pages. No partial wins.",
        "Write the missing page(s), or ship with a BLOCKED header naming the gap. Never silently drop a page.",
    ) ]


# ---------------------------------------------------------------------------
# FP-2 · registration: locked 8-section order
#   funnel-and-email-rules-lauren.md §A.1 "Required section order (8 sections, no exceptions)"
# ---------------------------------------------------------------------------

# The 8 locked sections. The rule is that the SECTION must be there in order — it does not
# dictate the client-facing label, and real pages don't use the rule's wording ("Does this sound
# familiar?" IS the This-Is-For-You-If section; "Here's What We're Covering" IS What You'll
# Discover). Matching the rule's literal names flagged four sections as missing on a page that
# had all eight.
REGISTRATION_SECTIONS = [
    ("trust bar",            r"trust\s*bar|badge|\bas\s+seen\b"),
    ("headline",             r"headline|hero|eyebrow"),
    ("this is for you if",   r"this\s+is\s+for\s+you|for\s+you\s+if|sound\s+familiar|pain\s+grid|"
                             r"does\s+this\s+sound"),
    ("what you'll discover", r"what\s+you.?ll\s+discover|what\s+you\s+will\s+discover|"
                             r"what\s+we.?re\s+covering|what\s+you.?ll\s+learn|\bagenda\b"),
    ("proof",                r"proof|case\s+stud|testimonial|results|real\s+women|before\s*/?\s*after"),
    ("meet the host",        r"meet\s+(?:the|your)\s+host|about\s+(?:the|your)\s+host|meet\s+your"),
    ("final cta",            r"final\s+cta|closing|last\s+cta"),
    ("q&a",                  r"q\s*&\s*a|faq|frequently\s+asked"),
]


def check_fp2_registration_sections(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    page = _page(bundle, "registration")
    if not page:
        return []  # FP-1 owns the missing-page case

    labels = [label for _, label in _blocks_in(page)]
    blob = " || ".join(labels).lower()

    violations = []
    for name, pattern in REGISTRATION_SECTIONS:
        if not re.search(pattern, blob, re.I):
            violations.append(_v(
                "FP-2", "registration 8-section order", HARD, page.section_id, page.start_line,
                f"(sections found: {len(labels)})",
                f"Registration page is missing the `{name}` section. The 8-section order is locked "
                f"with no exceptions: Trust Bar, Headline, This Is For You If, What You'll Discover, "
                f"Proof, Meet the Host, Final CTA, Q&A.",
                f"Add the `{name}` section in its locked position.",
            ))

    # Order check on the sections that ARE present.
    positions = []
    for i, (name, pattern) in enumerate(REGISTRATION_SECTIONS):
        for line_no, label in _blocks_in(page):
            if re.search(pattern, label, re.I):
                positions.append((i, name, line_no))
                break
    for j in range(1, len(positions)):
        (rank, name, line_no) = positions[j]
        (prev_rank, prev_name, _) = positions[j - 1]
        if rank < prev_rank:
            violations.append(_v(
                "FP-2", "registration 8-section order", HARD, page.section_id, line_no,
                name,
                f"`{name}` appears after `{prev_name}`, but the locked order puts it before. "
                f"The 8-section order has no exceptions.",
                "Reorder to the locked 8-section sequence.",
            ))
    return violations


# ---------------------------------------------------------------------------
# FP-3 · "This Is For You If" — 3 to 5 bullets
#   funnel-and-email-rules-lauren.md §A.1 "**This Is For You If** (3–5 bullets)"
# ---------------------------------------------------------------------------


def check_fp3_for_you_if_bullets(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    page = _page(bundle, "registration")
    if not page:
        return []
    blocks = _blocks_in(page)
    start = end = None
    for i, (line_no, label) in enumerate(blocks):
        if re.search(r"this\s+is\s+for\s+you", label, re.I):
            start = line_no
            end = blocks[i + 1][0] if i + 1 < len(blocks) else page.end_line
            break
    if start is None:
        return []  # FP-2 owns the missing-section case

    body = [(n, c) for n, c in page.lines if start < n < end]
    count = S.count_bullets(body)
    # The section may render its items inline with "·" separators rather than as bullets.
    if count == 0:
        inline = [c for n, c in body if c.count("·") >= 2]
        if inline:
            count = inline[0].count("·") + 1

    if 3 <= count <= 5:
        return []
    return [_v(
        "FP-3", "This Is For You If · bullets (count advisory)", YELLOW, page.section_id, start,
        f"({count} bullets)",
        f"`This Is For You If` has {count} bullets, outside the 3-5 convention. This is a practitioner "
        f"count (Brunson-style curiosity bullets), not canon — the number flexes with the hook. A "
        f"nudge, not a block.",
        "Land the qualifier bullets that fit the hook; 3-5 is the usual span. "
        "See references/craft/long-form-structure-rules.md.",
    )]


# ---------------------------------------------------------------------------
# FP-4 · registration Q&A — exactly 4 questions
#   funnel-and-email-rules-lauren.md §A.1 "**Q&A** — four objection-handling questions"
# ---------------------------------------------------------------------------

QUESTION_RE = re.compile(r"\?")


def _faq_body(page: S.Section) -> List[tuple]:
    blocks = _blocks_in(page)
    for i, (line_no, label) in enumerate(blocks):
        if re.search(r"q\s*&\s*a|faq|frequently\s+asked", label, re.I):
            end = blocks[i + 1][0] if i + 1 < len(blocks) else page.end_line
            return [(n, c) for n, c in page.lines if line_no <= n < end]
    return []


def check_fp4_faq_question_count(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    page = _page(bundle, "registration")
    if not page:
        return []
    body = _faq_body(page)
    if not body:
        return []
    count = sum(len(QUESTION_RE.findall(c)) for _, c in body)
    if count == 4:
        return []
    return [_v(
        "FP-4", "registration Q&A · question count (advisory)", YELLOW, page.section_id, body[0][0],
        f"({count} questions)",
        f"Registration Q&A has {count} questions. `Exactly four` has no DR basis, and qualifying "
        f"questions really belong on the application/booking step — a webinar opt-in wants minimal "
        f"friction. Cover the live objections (experience level, replay, the pitch, differentiation); "
        f"the count is a nudge.",
        "Answer the real objections rather than hitting a number. "
        "See references/craft/long-form-structure-rules.md.",
    )]


# ---------------------------------------------------------------------------
# FP-5 · FAQ carries zero sales language
#   workflow.md:206 "Search the Registration FAQ for: price, cost, investment, offer, buy,
#                    purchase, program, included, package. If any hit, rewrite or remove."
# ---------------------------------------------------------------------------

FAQ_FORBIDDEN = ["price", "cost", "investment", "offer", "buy", "purchase", "program", "included", "package"]
FAQ_FORBIDDEN_RE = re.compile(r"\b(" + "|".join(FAQ_FORBIDDEN) + r")\b", re.I)


def check_fp5_faq_sales_language(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    page = _page(bundle, "registration")
    if not page:
        return []
    violations = []
    for line_no, content in _faq_body(page):
        for m in FAQ_FORBIDDEN_RE.finditer(content):
            violations.append(_v(
                "FP-5", "FAQ zero sales language", HARD, page.section_id, line_no, content.strip(),
                f"`{m.group(0)}` in the registration FAQ. The FAQ is written from the audience's "
                f"point of view and never mentions selling or offers — it handles objections "
                f"(experience level, replay, what happens on the call, differentiation).",
                "Rewrite the question from the prospect's POV, or remove it.",
            ))
    return violations


# ---------------------------------------------------------------------------
# FP-6 · no sales language on the registration page; replay CTA-block only
#   funnel-and-email-rules-lauren.md §G.2 + Lauren 2026-07-13
# ---------------------------------------------------------------------------

SALES_LANGUAGE_RE = re.compile(
    r"("
    r"(?:discovery|strategy|coaching|consultation|breakthrough)\s+(?:call|session)"
    r"|(?:1[-\s]?on[-\s]?1|1:1|one[-\s]on[-\s]one)\s+(?:call|session)"
    r"|free\s+consultation"
    r"|chat\s+with\s+the\s+team"
    r"|book\s+a\s+call\s+with"
    r"|our\s+team\s+will"
    r"|book\s+a\s+call"
    r")",
    re.IGNORECASE,
)

# Structural CTA markers only. Deliberately excludes "book" / "schedule" / "claim": those
# words appear inside the forbidden phrases themselves, so a phrase would mark its own line
# as a CTA block and self-exempt.
# Lauren's rule names a SECTION, not a line range: the strategy session is pitched "on the cta
# section (above the typeform)". So the exemption is scoped to the blocks that make up that
# section — the bridge line, the CTA, the application form — and not by counting lines.
#
# A line-distance window was the first attempt and it was wrong in both directions: too narrow
# (a backward-only window flagged Trent's replay bridge line, which is the sanctioned placement)
# and then too wide (a ±4 window exempted the whole page on a short one).
CTA_BLOCK_RE = re.compile(
    r"\b(cta|call[-\s]to[-\s]action|typeform|application|apply|bridge|button|form|next\s+step)\b",
    re.IGNORECASE,
)


def _in_cta_section(page: S.Section, line_no: int) -> bool:
    """Does this line sit inside the page's CTA section?

    The CTA section runs from the CTA/bridge/application-form block label until the next block
    label that isn't part of it. That is what Lauren means by "the cta section (above the
    typeform)" — the pitch, the button, and the form, as one unit.
    """
    blocks = _blocks_in(page)
    if not blocks:
        return False
    governing = None
    for block_line, label in blocks:
        if block_line <= line_no:
            governing = label
        else:
            break
    return bool(governing and CTA_BLOCK_RE.search(governing))


def check_fp6_sales_language(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for page in _pages(bundle):
        if page.key not in ("registration", "replay"):
            continue  # confirmation pages are exempt — the reader must know the next step
        for idx, (line_no, content) in enumerate(page.lines):
            for m in SALES_LANGUAGE_RE.finditer(content):
                if page.key == "replay":
                    if _in_cta_section(page, line_no):
                        continue  # the CTA section above the typeform — exactly where it belongs
                    violations.append(_v(
                        "FP-6", "no sales language pre-conversion", YELLOW,
                        page.section_id, line_no, content.strip(),
                        f"`{m.group(0)}` on the Replay page, outside the CTA block. The strategy "
                        f"session is pitched in the CTA section above the typeform — loose in the "
                        f"page body it reads as a sales leak.",
                        "Move the mention into the CTA section above the typeform, or cut it.",
                    ))
                    continue
                violations.append(_v(
                    "FP-6", "no sales language pre-conversion", HARD,
                    page.section_id, line_no, content.strip(),
                    f"`{m.group(0)}` on the Registration page. This page's only job is winning the "
                    f"registration — a call offer here competes with it. Sales-call framing happens "
                    f"on the call itself, not on the registration page.",
                    "Cut the phrase. The call gets pitched on the replay and confirmation pages.",
                ))
    return violations


# ---------------------------------------------------------------------------
# FP-7 / FP-8 / FP-9 · locked page block contracts
#   workflow.md:137 Webinar Confirmation: "Headline → Video → Steps to confirm → Case
#                   studies. Nothing else." / :250 "No FAQ. No upsell. No social links."
#   workflow.md:143 Replay: "Headline → Video → Bridge line → Application form → Case studies."
#   workflow.md:149 Book Call Confirmation: "'Almost Confirmed' headline → 3 steps → Case studies."
# ---------------------------------------------------------------------------

LOCKED_BLOCKS = {
    "webinar_confirmation": [
        ("headline", r"headline|eyebrow"),
        ("video", r"video"),
        ("steps to confirm", r"steps?\s+to\s+confirm|step\s*\d|steps?"),
        ("case studies", r"case\s+stud|proof|testimonial|real\s+results"),
    ],
    "replay": [
        ("headline", r"headline|eyebrow"),
        ("video", r"video|replay"),
        ("bridge line", r"bridge"),
        ("application form", r"application|typeform|\bform\b"),
        ("case studies", r"case\s+stud|proof|testimonial|real\s+results"),
    ],
    "book_call_confirmation": [
        ("headline", r"headline|eyebrow"),
        ("3 steps", r"step\s*\d|steps?"),
        ("case studies", r"case\s+stud|proof|testimonial|real\s+results"),
    ],
}

# Blocks that must NOT appear on the locked pages (workflow.md:250, :285).
BANNED_BLOCKS_RE = re.compile(r"\bfaq\b|\bq\s*&\s*a\b|frequently\s+asked|upsell|bonus|social\s+link", re.I)

FP_RULE_FOR_PAGE = {
    "webinar_confirmation": ("FP-7", "webinar confirmation locked to 4 blocks"),
    "replay": ("FP-8", "replay locked to 5 blocks"),
    "book_call_confirmation": ("FP-9", "book call confirmation locked to 3 blocks"),
}


def _check_locked_page(bundle: ParsedBundle, page_key: str) -> List[Violation]:
    page = _page(bundle, page_key)
    if not page:
        return []
    rule_id, rule_name = FP_RULE_FOR_PAGE[page_key]
    expected = LOCKED_BLOCKS[page_key]
    labels = [label for _, label in _blocks_in(page)]
    # Search the page's whole text, not just its block labels. A block can be present without
    # carrying its own label — Trent's confirmation page embeds the video inside Step 1, and
    # label-only matching reported the video as missing when it was right there.
    blob = " || ".join(labels) + " || " + page.body

    violations = []
    for name, pattern in expected:
        if not re.search(pattern, blob, re.I):
            violations.append(_v(
                rule_id, rule_name, HARD, page.section_id, page.start_line, f"(blocks: {len(labels)})",
                f"{PAGE_LABELS[page_key]} page is missing the `{name}` block. The structure is locked "
                f"to {len(expected)} blocks: {' → '.join(n for n, _ in expected)}.",
                f"Add the `{name}` block in its locked position.",
            ))

    for line_no, label in _blocks_in(page):
        if BANNED_BLOCKS_RE.search(label):
            violations.append(_v(
                rule_id, rule_name, HARD, page.section_id, line_no, label,
                f"`{label}` on the {PAGE_LABELS[page_key]} page. No FAQ, no upsell, no social links, "
                f"no bonus content — {len(expected)} blocks, end of page.",
                f"Remove the `{label}` block.",
            ))
    return violations


def check_fp7_webinar_confirmation(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    return _check_locked_page(bundle, "webinar_confirmation")


def check_fp8_replay(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    return _check_locked_page(bundle, "replay")


def check_fp9_book_call_confirmation(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = _check_locked_page(bundle, "book_call_confirmation")
    page = _page(bundle, "book_call_confirmation")
    if not page:
        return violations
    # workflow.md:151 — the headline is framed around "Almost Confirmed" (or an approved
    # near-verbatim variant, e.g. the live anchor's "Your Seat Is Almost Secured").
    if not re.search(r"almost\s+(confirmed|secured|there|done)", page.body, re.I):
        violations.append(_v(
            "FP-9", "book call confirmation locked to 3 blocks", HARD,
            page.section_id, page.start_line, "(no 'Almost Confirmed' headline)",
            "Book Call Confirmation headline is not framed around `Almost Confirmed`. The locked "
            "headline is 'Almost Confirmed' or a client-approved near-verbatim variant.",
            "Reframe the headline around 'Almost Confirmed'.",
        ))
    return violations


# ---------------------------------------------------------------------------
# FP-10 · minimum 5 case studies, each photo + video + quote
#   workflow.md:95 "Proof must be photo + video + verbatim quote, listed in one column."
#   workflow.md:183 required gate · "missing case studies < 5" is a stop condition
# ---------------------------------------------------------------------------

BANNED_PROOF_LAYOUT_RE = re.compile(r"\bgrid\b|\bcarousel\b|logo\s+wall|star[-\s]rating|\bslider\b", re.I)


def check_fp10_proof_stack(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    page = _page(bundle, "registration")
    if not page:
        return []

    body = page.body
    quotes = len(re.findall(r"[\"“][^\"”]{15,}[\"”]", body))
    photos = len(re.findall(r"\bphoto\b", body, re.I))
    videos = len(re.findall(r"\bvideo\b", body, re.I))

    violations = []
    if quotes < 5:
        violations.append(_v(
            "FP-10", "proof · case-study count (floor, advisory)", YELLOW,
            page.section_id, page.start_line, f"({quotes} quoted case studies)",
            f"Only {quotes} case studies with a verbatim quote. Social proof scales up (Cialdini), so "
            f"this is a floor, not a gate: aim for ~5+, but a newer client with fewer is a nudge, not a "
            f"block. The photo + video + quote FORMAT below stays required (HARD).",
            "Add case studies where you have them. See references/craft/long-form-structure-rules.md.",
        ))
    if quotes >= 1 and (photos == 0 or videos == 0):
        missing = "photo" if photos == 0 else "video"
        violations.append(_v(
            "FP-10", "proof · 5+ case studies, photo+video+quote", HARD,
            page.section_id, page.start_line, f"(photo refs: {photos}, video refs: {videos})",
            f"Proof blocks name no {missing}. Proof is photo + video + verbatim quote, stacked in "
            f"one column — not a quote on its own.",
            f"Specify the {missing} for each case study so a human can source it.",
        ))
    # Scoped to the proof block only. Scanning the whole page flagged Trent's "pain grid" —
    # a different section entirely — as though the PROOF were laid out as a grid.
    blocks = _blocks_in(page)
    for i, (block_line, label) in enumerate(blocks):
        if not re.search(r"proof|case\s+stud|testimonial|real\s+women|results", label, re.I):
            continue
        end = blocks[i + 1][0] if i + 1 < len(blocks) else page.end_line
        for line_no, content in [(n, c) for n, c in page.lines if block_line <= n < end]:
            m = BANNED_PROOF_LAYOUT_RE.search(content)
            if not m:
                continue
            violations.append(_v(
                "FP-10", "proof · 5+ case studies, photo+video+quote", HARD,
                page.section_id, line_no, content.strip(),
                f"Proof laid out as a `{m.group(0)}`. Proof is one vertical column — not a grid, not "
                f"a carousel, not a logo wall, not a star-rating widget, not a slider.",
                "Restack the proof into a single vertical column.",
            ))
    return violations


# ---------------------------------------------------------------------------
# FP-11 / FP-12 / FP-13 · shared craft rules
# ---------------------------------------------------------------------------


def check_fp11_no_em_dashes(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Canonical craft rule · no em dashes, anywhere."""
    violations = []
    for page in _pages(bundle):
        for line_no, content in page.lines:
            # Scan the copy, not the doc's own scaffolding. `**Label:** — content` uses the dash
            # as a delimiter; flagging it reports an em-dash violation on every labelled line.
            if S.EM_DASH_RE.search(S.copy_text(content)):
                violations.append(_v(
                    "FP-11", "no em dashes", HARD, page.section_id, line_no, content.strip(),
                    "Em dash. Growth Mate copy uses a comma, a period, or a rewrite.",
                    "Replace the em dash with a comma or split the sentence.",
                ))
    return violations


def check_fp12_no_asterisk_bullets(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Lauren · bullets are • or -, never *."""
    violations = []
    for page in _pages(bundle):
        for line_no, content in page.lines:
            if S.ASTERISK_BULLET_RE.match(content):
                violations.append(_v(
                    "FP-12", "no asterisk bullets", HARD, page.section_id, line_no, content.strip(),
                    "Asterisk bullet. Bullets are `•` or `-`.",
                    "Swap the `*` for a `•` or `-`.",
                ))
    return violations


def check_fp13_us_english(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Alec · British English -> US English."""
    violations = []
    for page in _pages(bundle):
        for line_no, content in page.lines:
            for m in S.BRITISH_RE.finditer(content):
                word = m.group(0)
                fix = S.BRITISH_SPELLINGS.get(word.lower(), "the US spelling")
                violations.append(_v(
                    "FP-13", "US English", HARD, page.section_id, line_no, content.strip(),
                    f"British spelling `{word}`. Copy ships in US English.",
                    f"Use `{fix}`.",
                ))
    return violations


# ---------------------------------------------------------------------------
# FP-14 · every content section leads with its own headline
#   workflow.md Rule 11 (Lauren, 2026-07-15) "Every content section on every funnel page
#   opens with its own headline."
#
# Every below-the-fold section is DETECTED by its headline block, so by construction it has one —
# a section written with no headline just merges into its neighbour and is invisible to the parser
# (a regex can't see a topic change; that merged-section case stays a human-review catch, per this
# module's "a check that pretends to grade judgment is worse than no check" principle). The one
# section whose headline the parser CAN verify is the top-of-fold hero: it leads the page, so it
# can open straight into body copy and still parse. FP-14 enforces exactly that visible case — the
# page's first line of copy must BE a headline, not a paragraph. Per Lauren's top-of-fold rule the
# hero headline IS that section's headline, so no separate heading is required above it.
#
# Exempt openers (utility/asset blocks that carry no prose headline by design): trust bar, timer,
# video embed, application form, individual proof cards, footer, status banners. They are skipped
# so a logo strip or countdown never reads as a headless hero.
# ---------------------------------------------------------------------------

# A line that is only an asset/utility placeholder — `[PHOTO]`, `![img](…)`, `[BUTTON: Save My Seat]`.
FP14_ASSET_LINE_RE = re.compile(r"^\s*(?:[-•*]\s+)?!?\[[^\]]*\]\s*$")
# Scaffolding / status banners the deliverable carries that are not section copy.
FP14_BANNER_RE = re.compile(r"^\s*\**\s*(?:STATUS|BLOCKED|NOTE|SESSION|QC|HANDOFF)\b", re.I)
# Exempt utility blocks that may open a page with real words but need no headline of their own.
FP14_UTILITY_RE = re.compile(r"\bas\s+seen\b|\bfeatured\s+in\b|\btrust\s*bar\b|\bcountdown\b|\btimer\b", re.I)


def _is_headline_line(content: str) -> bool:
    """Does this line read as a headline — a markdown header or a bold block label?"""
    if S.HEADER_RE.match(content):
        return True
    m = re.match(r"^\s*(?P<lead>[-•*]\s+|\d+[.)]\s+)?\*\*(?P<label>[^*]{2,120}?)\*\*", content.strip())
    if m:
        label = m.group("label").strip()
        if m.group("lead") and ":" not in label:
            return False  # a list item like `- **Mary** — …`, not a headline
        return True
    return False


def _first_copy_line(page: S.Section) -> Optional[tuple]:
    """The line that decides whether the hero is headed: the first headline OR the first
    substantial prose line, whichever comes first. Utility / asset / short openers are skipped so
    a trust bar, timer, logo strip, or eyebrow never counts as a headless hero. -> (line_no, line).
    """
    for line_no, content in page.lines:
        if not content.strip():
            continue
        if _is_headline_line(content):
            return (line_no, content)
        if FP14_BANNER_RE.match(content) or FP14_ASSET_LINE_RE.match(content) or FP14_UTILITY_RE.search(content):
            continue
        if S.word_count(content) < 6:
            continue  # logos, eyebrow, timer, other short utility copy
        return (line_no, content)  # substantial prose that reached us before any headline
    return None


def check_fp14_section_headlines(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for page in _pages(bundle):
        opener = _first_copy_line(page)
        if opener is None:
            continue  # nothing but assets/utility — FP-1/2/7/8/9 own the empty-page case
        line_no, content = opener
        if _is_headline_line(content):
            continue
        violations.append(_v(
            "FP-14", "section leads with a headline", HARD, page.section_id, line_no, content.strip(),
            f"The {PAGE_LABELS[page.key]} page opens with body copy, not a headline. Every section "
            f"leads with its own headline; the top-of-fold hero's headline is that section's main "
            f"copy, so the page's first line of copy must BE that headline.",
            "Give the top-of-fold section a headline as its first line.",
        ))
    return violations


RULES = [
    Rule(id="FP-0",  name="document parses",                  severity=HARD,   layer=LAYER, check=check_fp0_parseable,              applies_to=APPLIES_TO),
    Rule(id="FP-1",  name="4-page funnel deliverable",        severity=HARD,   layer=LAYER, check=check_fp1_four_pages,             applies_to=APPLIES_TO),
    Rule(id="FP-2",  name="registration 8-section order",     severity=HARD,   layer=LAYER, check=check_fp2_registration_sections,  applies_to=APPLIES_TO),
    Rule(id="FP-3",  name="This Is For You If · bullet count", severity=YELLOW, layer=LAYER, check=check_fp3_for_you_if_bullets,     applies_to=APPLIES_TO),
    Rule(id="FP-4",  name="registration Q&A · question count", severity=YELLOW, layer=LAYER, check=check_fp4_faq_question_count,     applies_to=APPLIES_TO),
    Rule(id="FP-5",  name="FAQ zero sales language",          severity=HARD,   layer=LAYER, check=check_fp5_faq_sales_language,     applies_to=APPLIES_TO),
    Rule(id="FP-6",  name="no sales language pre-conversion", severity=HARD,   layer=LAYER, check=check_fp6_sales_language,         applies_to=APPLIES_TO),
    Rule(id="FP-7",  name="webinar confirmation · 4 blocks",  severity=HARD,   layer=LAYER, check=check_fp7_webinar_confirmation,   applies_to=APPLIES_TO),
    Rule(id="FP-8",  name="replay · 5 blocks",                severity=HARD,   layer=LAYER, check=check_fp8_replay,                 applies_to=APPLIES_TO),
    Rule(id="FP-9",  name="book call confirmation · 3 blocks", severity=HARD,  layer=LAYER, check=check_fp9_book_call_confirmation, applies_to=APPLIES_TO),
    Rule(id="FP-10", name="proof · 5+ case studies",          severity=HARD,   layer=LAYER, check=check_fp10_proof_stack,           applies_to=APPLIES_TO),
    Rule(id="FP-11", name="no em dashes",                     severity=HARD,   layer=LAYER, check=check_fp11_no_em_dashes,          applies_to=APPLIES_TO),
    Rule(id="FP-12", name="no asterisk bullets",              severity=HARD,   layer=LAYER, check=check_fp12_no_asterisk_bullets,   applies_to=APPLIES_TO),
    Rule(id="FP-13", name="US English",                       severity=HARD,   layer=LAYER, check=check_fp13_us_english,            applies_to=APPLIES_TO),
    Rule(id="FP-14", name="section leads with a headline",    severity=HARD,   layer=LAYER, check=check_fp14_section_headlines,     applies_to=APPLIES_TO),
]
