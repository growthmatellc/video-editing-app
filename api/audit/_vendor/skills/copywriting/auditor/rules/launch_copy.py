"""launch_copy.py — launch-copy bundle (5-asset) structural checks.

The `/launch-copy` bundle is 5 assets in 5 Google Docs, generated in a locked
sequential order, with the TAB Section 13H toggles deciding which sub-assets fire
at all. This module audits the archived combined bundle doc.

Every rule here is ported from a rule that was already written down. Nothing new
is invented:

  LC-1 · scope confirmation block present
         spec-v2.md SCOPE BOUNDARY RULE · "Generating: [asset_type] for [client].
         Other assets: not in scope this run."
  LC-2 · 13H toggle declaration present
         spec-v2.md:52 · "surface a pre-flight scope confirmation listing which
         toggles are ON and which are OFF"
  LC-3 · no asset present whose 13H toggle is OFF
         spec-v2.md:627 HARD RULE · "Never generate an asset whose 13H toggle is OFF"
  LC-4 · archived section order matches the locked delivery order
         config.py LOCKED_ASSET_ORDER · presentation → funnel → ads → video → email
  LC-5 · funnel deliverable carries all 4 pages
         spec-v2.md §A13 · "A 3-of-4 delivery is incomplete"
  LC-6 · no call-booking language on the pre-conversion pages (Registration, Replay)
         config.py FUNNEL_FORBIDDEN_PHRASES + FUNNEL_FORBIDDEN_SCOPE
  LC-7 · no out-of-scope asset bundled
         spec-v2.md:83 · VSLs "live OUTSIDE that locked-order sequence"

Severity note on LC-1 and LC-2. Both are specified as *chat* output emitted before
generation starts, which a static file audit cannot observe. They are YELLOW here
rather than HARD: the audit reports that toggle compliance is unverifiable and names
what the doc would need to carry to make it verifiable. LC-3 — the actual Lauren
hard rule — is HARD, and fires whenever the toggle data is there to check against.

Origin: the 2026-06-03 scope-creep incident (Lauren: "asked for emails and it was
creating the webinar also"). See
incidents/2026-06-03_scope-creep-emails-generated-webinar.md
"""

from __future__ import annotations

import re
from typing import List, Optional

from skills.copywriting.auditor.lib.parser import ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation


LAYER = "LaunchCopy"
APPLIES_TO = {"launch_copy"}


# Locked sequential asset order (config.py LOCKED_ASSET_ORDER · Lauren directive).
LOCKED_ASSET_ORDER = (
    "webinar_presentation",
    "funnel_copy",
    "ads_copy",
    "video_scripts",
    "email_copy",
)

# 13H toggle → the asset it gates (config.py TOGGLE_TO_AGENT).
# 13H.3 gates an image brief, which has no copy asset in the bundle.
TOGGLE_TO_ASSET = {
    "13H.1": "email_copy",
    "13H.2": "funnel_copy",
    "13H.4": "ads_copy",
}

# The 4 locked funnel pages (config.py FUNNEL_PAGES). A 3-of-4 delivery fails.
FUNNEL_PAGES = ("registration", "webinar_confirmation", "replay", "book_call_confirmation")

FUNNEL_PAGE_LABELS = {
    "registration": "Registration / Opt-in",
    "webinar_confirmation": "Webinar Confirmation",
    "replay": "Replay",
    "book_call_confirmation": "Book Call Confirmation",
}

# Where call-booking language is allowed, per page (config.py FUNNEL_FORBIDDEN_SCOPE).
#
# registration          — FORBIDDEN outright. This page's only job is winning the
#                         registration; a call offer competes with it.
# webinar_confirmation  — allowed. Post-conversion. The reader has to know the next step.
# book_call_confirmation— allowed. That page IS the call close.
# replay                — allowed, but only in the CTA section above the typeform, which
#                         is where the strategy session is pitched. Scattered through the
#                         page body it's a sales leak, so that's flagged.
#
# (Lauren, 2026-07-13: "with registration page, sales language shouldn't be there.
# usually on the replay page, we mention the strategy session on the cta section
# (above the typeform)")
FUNNEL_FORBIDDEN_SCOPE = ("registration",)

# Replay is a special case: allowed in the CTA block, flagged elsewhere on the page.
FUNNEL_CTA_ONLY_SCOPE = ("replay",)

# Markers that say "this is the CTA block" — the phrase is expected here.
#
# These are STRUCTURAL markers only. Deliberately excludes "book" / "schedule" / "claim":
# those words appear inside the forbidden phrases themselves ("book a call"), so a phrase
# would mark its own line as a CTA block and self-exempt.
CTA_CONTEXT_RE = re.compile(
    r"\b(cta|call[-\s]to[-\s]action|typeform|application(?:\s+form)?|apply|bridge|"
    r"next\s+step|button|book\s+your\s+call|form)\b",
    re.IGNORECASE,
)

# The window looks BOTH ways. The strategy session is pitched "on the cta section (above the
# typeform)", so the typeform marker comes AFTER the pitch. A backward-only window flagged the
# sanctioned placement as a violation.
CTA_CONTEXT_LOOKBACK = 4

# config.py FUNNEL_FORBIDDEN_PHRASES, widened to catch "session" alongside "call".
# The literal list misses "free 1-on-1 strategy session" — same sales move, different
# noun — which is sitting on Trent's v1 registration page today.
FUNNEL_FORBIDDEN_RE = re.compile(
    r"("
    r"(?:discovery|strategy|coaching|consultation|breakthrough)\s+(?:call|session)"
    r"|(?:1[-\s]?on[-\s]?1|1:1|one[-\s]on[-\s]one)\s+(?:call|session)"
    r"|free\s+consultation"
    r"|chat\s+with\s+the\s+team"
    r"|book\s+a\s+call"
    r")",
    re.IGNORECASE,
)

# Asset-section header signatures. Order matters — first match wins, so the narrow
# patterns ("video ads") sit above the broad ones ("confirmation videos").
ASSET_HEADER_PATTERNS = [
    ("ads_copy", re.compile(r"\b(?:video|image|facebook|google|meta)\s+ads?\b|\bad\s+copy\b|\bads?\s+(?:variations?|creative)\b", re.I)),
    ("video_scripts", re.compile(r"\bconfirmation\s+videos?\b|\bvideo\s+scripts?\b|\bvsl\b", re.I)),
    ("webinar_presentation", re.compile(r"\bwebinar\s+(?:presentation|deck)\b|\bpresentation\s+copy\b|\bslides?\b|\bpresenter\s+notes?\b", re.I)),
    ("email_copy", re.compile(r"\bemail\b|\bsms\b|\bsequence\b|\bbroadcast\b", re.I)),
    ("funnel_copy", re.compile(r"\bopt[-\s]?in\b|\bregistration\b|\blanding\s+page\b|\bconfirmation\s+page\b|\breplay\s+page\b|\bfunnel\b|\bbooking\s+page\b", re.I)),
]

# Which of the 4 funnel pages a header names. Checked only inside funnel_copy sections.
# Book-call confirmation is tested first — its heading also contains "confirmation".
FUNNEL_PAGE_PATTERNS = [
    ("book_call_confirmation", re.compile(r"\b(?:call[-\s]?booking|book(?:ing)?[-\s]?(?:a[-\s]?)?call)\b", re.I)),
    ("webinar_confirmation", re.compile(r"\bwebinar\s+confirmation\b|\bconfirmation\s+page\b", re.I)),
    ("replay", re.compile(r"\breplay\b", re.I)),
    ("registration", re.compile(r"\bopt[-\s]?in\b|\bregistration\b|\blanding\s+page\b", re.I)),
]

HEADER_RE = re.compile(r"^(#{1,4})\s+(?P<title>.+?)\s*$")

# "Generating: <asset> for <client>. Other assets: not in scope this run."
SCOPE_CONFIRMATION_RE = re.compile(r"generating:.*?\bnot in scope this run\b", re.I | re.S)

# "13H.1 (Email sequence): ON"  ·  "13H.1=ON"  ·  "13H.2 — funnel — YES"
TOGGLE_DECLARATION_RE = re.compile(
    r"\b(?P<key>13H\.[1-4])\b[^\n]*?\b(?P<state>ON|OFF|YES|NO|Y|N)\b",
    re.I,
)


class AssetSection:
    """One asset block in the archived bundle doc."""

    def __init__(self, key: str, heading: str, level: int, start_line: int):
        self.key = key
        self.heading = heading
        self.level = level
        self.start_line = start_line
        self.end_line = start_line
        self.lines: List[tuple] = []  # (line_no, content)

    @property
    def section_id(self) -> str:
        return self.heading


def _classify_header(title: str) -> Optional[str]:
    for key, pattern in ASSET_HEADER_PATTERNS:
        if pattern.search(title):
            return key
    return None


def _asset_sections(bundle: ParsedBundle) -> List[AssetSection]:
    """Split the bundle doc into asset sections by markdown header.

    A section runs from its header to the next header at the same or a higher level,
    so sub-headers (`### EMAIL 1`) stay inside their parent (`## 2. EMAIL + SMS SHOW-UP
    SEQUENCE`) instead of opening a section of their own.
    """
    sections: List[AssetSection] = []
    current: Optional[AssetSection] = None

    for idx, line in enumerate(bundle.raw_lines):
        line_no = idx + 1
        m = HEADER_RE.match(line)
        if m:
            level = len(m.group(1))
            title = m.group("title")
            # Close the open section if this header is a sibling or an ancestor.
            if current and level <= current.level:
                current.end_line = line_no - 1
                current = None
            if current is None:
                key = _classify_header(title)
                if key:
                    current = AssetSection(key=key, heading=title.strip(), level=level, start_line=line_no)
                    sections.append(current)
                    continue
        if current is not None:
            current.lines.append((line_no, line))
            current.end_line = line_no

    return sections


def _declared_toggles(bundle: ParsedBundle) -> dict:
    """Read any 13H toggle declarations out of the doc. -> {"13H.1": True, ...}"""
    toggles = {}
    for m in TOGGLE_DECLARATION_RE.finditer(bundle.raw_text):
        state = m.group("state").upper()
        toggles[m.group("key").upper()] = state in ("ON", "YES", "Y")
    return toggles


def _funnel_page_of(section: AssetSection) -> Optional[str]:
    for page, pattern in FUNNEL_PAGE_PATTERNS:
        if pattern.search(section.heading):
            return page
    return None


# ---------------------------------------------------------------------------
# LC-1 · scope confirmation block present
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# LC-0 · the bundle parses into at least one recognised asset
#
# Every LC check keys off _asset_sections / toggles with `if not X: return []`, so an empty or
# unrecognised bundle runs the whole layer on nothing and prints a pass. Zero parsed assets is a
# HARD failure, never a silent one. (Same stance as FP-0 / SP-0.)
# ---------------------------------------------------------------------------


def check_lc0_parseable(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if _asset_sections(bundle):
        return []
    return [Violation(
        rule_id="LC-0", rule_name="document parses", severity=HARD,
        section_id="document", line_no=1, line_content="(0 launch-copy assets parsed)",
        message="No launch-copy assets could be parsed, so no LC rule was actually evaluated. The "
                "auditor will not pass a file it cannot read. Expected asset headers like "
                "`# Webinar Presentation`, `# Funnel Copy`, `# Emails`.",
        fix_hint="Fix the asset headers, or extend the parser if this is a new format.",
    )]


def check_lc1_scope_confirmation(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if SCOPE_CONFIRMATION_RE.search(bundle.raw_text):
        return []
    return [Violation(
        rule_id="LC-1",
        rule_name="scope confirmation block",
        severity=YELLOW,
        section_id="metadata",
        line_no=1,
        line_content="(no scope confirmation found)",
        message=(
            "Bundle carries no scope confirmation. The archived doc has no record of which "
            "assets were in scope for the run, so scope creep can't be audited after the fact."
        ),
        fix_hint=(
            "Add the spec-v2 line near the top: `Generating: launch-copy bundle for [client]. "
            "Other assets: not in scope this run.`"
        ),
    )]


# ---------------------------------------------------------------------------
# LC-2 · 13H toggle declaration present
# ---------------------------------------------------------------------------


def check_lc2_toggle_declaration(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if _declared_toggles(bundle):
        return []
    return [Violation(
        rule_id="LC-2",
        rule_name="13H toggle declaration",
        severity=YELLOW,
        section_id="metadata",
        line_no=1,
        line_content="(no 13H toggle declaration found)",
        message=(
            "Bundle declares no 13H toggle states. LC-3 (never generate an asset whose toggle "
            "is OFF) can't be enforced without them, so toggle compliance is unverifiable here."
        ),
        fix_hint=(
            "Add the pre-flight toggle list: `13H.1 (Email sequence): ON · 13H.2 (Funnel page): "
            "ON · 13H.3 (Image brief): OFF · 13H.4 (Ad copy): ON`. TAB Section 13H is the source "
            "of truth — never override it."
        ),
    )]


# ---------------------------------------------------------------------------
# LC-3 · no asset present whose 13H toggle is OFF
# ---------------------------------------------------------------------------


def check_lc3_toggle_respected(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """spec-v2 HARD RULE · "Never generate an asset whose 13H toggle is OFF"."""
    violations = []
    toggles = _declared_toggles(bundle)
    if not toggles:
        return violations  # LC-2 already reported the missing declaration

    sections = _asset_sections(bundle)
    for toggle_key, asset in TOGGLE_TO_ASSET.items():
        if toggles.get(toggle_key, True):
            continue  # toggle ON, or not declared → the asset is allowed to run
        for section in sections:
            if section.key != asset:
                continue
            violations.append(Violation(
                rule_id="LC-3",
                rule_name="13H toggle respected",
                severity=HARD,
                section_id=section.section_id,
                line_no=section.start_line,
                line_content=section.heading,
                message=(
                    f"`{asset}` is in the bundle but {toggle_key} is declared OFF. The bundle is "
                    f"sized by the toggle list, not by a hardcoded 5-asset assumption."
                ),
                fix_hint=(
                    f"Strip the {asset} section, or correct {toggle_key} if the TAB actually has it "
                    f"ON. The agent never overrides the strategist's toggle."
                ),
            ))
    return violations


# ---------------------------------------------------------------------------
# LC-4 · archived section order matches the locked delivery order
# ---------------------------------------------------------------------------


def check_lc4_locked_order(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """config.py LOCKED_ASSET_ORDER · presentation → funnel → ads → video → email.

    YELLOW, not HARD. The locked order governs the generation pipeline (each asset is
    approved before the next begins), and a static file audit can't observe that. Section
    order in the archived doc is only a proxy for it, so a mismatch is a flag to check,
    not a ship blocker.
    """
    violations = []
    sections = _asset_sections(bundle)

    # First appearance of each asset, in document order.
    seen: List[tuple] = []
    seen_keys = set()
    for section in sections:
        if section.key not in seen_keys:
            seen.append((section.key, section))
            seen_keys.add(section.key)

    rank = {asset: i for i, asset in enumerate(LOCKED_ASSET_ORDER)}
    for i in range(1, len(seen)):
        prev_key, _ = seen[i - 1]
        this_key, this_section = seen[i]
        if prev_key not in rank or this_key not in rank:
            continue
        if rank[this_key] < rank[prev_key]:
            violations.append(Violation(
                rule_id="LC-4",
                rule_name="locked asset order",
                severity=YELLOW,
                section_id=this_section.section_id,
                line_no=this_section.start_line,
                line_content=this_section.heading,
                message=(
                    f"`{this_key}` appears after `{prev_key}`, but the locked order is "
                    f"{' → '.join(LOCKED_ASSET_ORDER)}."
                ),
                fix_hint=(
                    "Reorder the archived sections to the locked delivery order, or confirm the "
                    "pipeline itself ran in order — this check only sees the doc."
                ),
            ))
    return violations


# ---------------------------------------------------------------------------
# LC-5 · funnel deliverable carries all 4 pages
# ---------------------------------------------------------------------------


def check_lc5_funnel_complete(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """spec-v2 §A13 · "A 3-of-4 delivery is incomplete and must fail self-reflection"."""
    violations = []
    sections = _asset_sections(bundle)
    funnel_sections = [s for s in sections if s.key == "funnel_copy"]
    if not funnel_sections:
        return violations  # no funnel in this bundle at all → LC-3 governs

    found = {page: None for page in FUNNEL_PAGES}
    for section in funnel_sections:
        page = _funnel_page_of(section)
        if page and found[page] is None:
            found[page] = section.start_line

    missing = [page for page, line in found.items() if line is None]
    if not missing:
        return violations

    present = [FUNNEL_PAGE_LABELS[p] for p, line in found.items() if line is not None]
    anchor_line = funnel_sections[0].start_line
    for page in missing:
        violations.append(Violation(
            rule_id="LC-5",
            rule_name="4-page funnel deliverable",
            severity=HARD,
            section_id="Funnel Copy",
            line_no=anchor_line,
            line_content=f"(present: {', '.join(present) if present else 'none'})",
            message=(
                f"Funnel deliverable is missing the {FUNNEL_PAGE_LABELS[page]} page. A complete "
                f"funnel deliverable is all 4 pages — none can be skipped."
            ),
            fix_hint=(
                f"Write the {FUNNEL_PAGE_LABELS[page]} page, or ship with a BLOCKED header naming "
                f"the gap. Partial deliveries never ship silently."
            ),
        ))
    return violations


# ---------------------------------------------------------------------------
# LC-6 · no call-booking language on funnel pages 1-3
# ---------------------------------------------------------------------------


def _in_cta_block(section: AssetSection, hit_index: int) -> bool:
    """Is this line inside the page's CTA block (the bit above the typeform)?"""
    start = max(0, hit_index - CTA_CONTEXT_LOOKBACK)
    end = hit_index + CTA_CONTEXT_LOOKBACK + 1
    for _, content in section.lines[start:end]:
        if CTA_CONTEXT_RE.search(content):
            return True
    return False


def check_lc6_funnel_forbidden_phrases(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """config.py FUNNEL_FORBIDDEN_PHRASES.

    Registration: forbidden outright (HARD). Its only job is winning the registration.
    Replay: allowed in the CTA section above the typeform, flagged (YELLOW) anywhere else
    on the page. Both confirmation pages: allowed — the reader has to know the next step.
    """
    violations = []
    for section in _asset_sections(bundle):
        if section.key != "funnel_copy":
            continue
        page = _funnel_page_of(section)
        if page not in FUNNEL_FORBIDDEN_SCOPE and page not in FUNNEL_CTA_ONLY_SCOPE:
            continue

        for idx, (line_no, content) in enumerate(section.lines):
            for m in FUNNEL_FORBIDDEN_RE.finditer(content):
                if page in FUNNEL_CTA_ONLY_SCOPE:
                    if _in_cta_block(section, idx):
                        continue  # this is exactly where it belongs
                    violations.append(Violation(
                        rule_id="LC-6",
                        rule_name="no call-booking lang pre-conversion",
                        severity=YELLOW,
                        section_id=section.section_id,
                        line_no=line_no,
                        line_content=content.strip(),
                        message=(
                            f"`{m.group(0)}` on the {FUNNEL_PAGE_LABELS[page]} page, outside the CTA "
                            f"block. The strategy session is pitched in the CTA section above the "
                            f"typeform — loose in the page body it reads as a sales leak."
                        ),
                        fix_hint="Move the mention into the CTA section above the typeform, or cut it.",
                    ))
                    continue

                violations.append(Violation(
                    rule_id="LC-6",
                    rule_name="no call-booking lang pre-conversion",
                    severity=HARD,
                    section_id=section.section_id,
                    line_no=line_no,
                    line_content=content.strip(),
                    message=(
                        f"`{m.group(0)}` on the {FUNNEL_PAGE_LABELS[page]} page. This page's only job "
                        f"is winning the registration — a call offer here competes with it. Sales "
                        f"language does not belong on the registration page."
                    ),
                    fix_hint="Cut the phrase. The call gets pitched on the confirmation and replay pages.",
                ))
    return violations


# ---------------------------------------------------------------------------
# LC-7 · no out-of-scope asset bundled
# ---------------------------------------------------------------------------


OUT_OF_SCOPE_ASSETS = [
    ("VSL", re.compile(r"^#{1,4}\s+.*\bvsl\b", re.I)),
    ("sales page", re.compile(r"^#{1,4}\s+.*\bsales\s+page\b", re.I)),
    ("organic social", re.compile(r"^#{1,4}\s+.*\borganic\s+social\b", re.I)),
]


def check_lc7_out_of_scope_asset(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """spec-v2:83 · VSLs "live OUTSIDE that locked-order sequence".

    The 2026-06-03 incident in reverse: instead of a single-asset run growing siblings,
    the bundle quietly grows an asset that was never part of it.
    """
    violations = []
    for idx, line in enumerate(bundle.raw_lines):
        for label, pattern in OUT_OF_SCOPE_ASSETS:
            if pattern.match(line):
                violations.append(Violation(
                    rule_id="LC-7",
                    rule_name="no out-of-scope asset bundled",
                    severity=HARD,
                    section_id=line.strip(),
                    line_no=idx + 1,
                    line_content=line.strip(),
                    message=(
                        f"`{label}` is in the launch-copy bundle. It's a different conversion vehicle "
                        f"and lives outside the locked-order sequence."
                    ),
                    fix_hint=f"Strip the {label} section. Generate it with its own command.",
                ))
    return violations


RULES = [
    Rule(id="LC-0", name="document parses",                   severity=HARD,   layer=LAYER, check=check_lc0_parseable,               applies_to=APPLIES_TO),
    Rule(id="LC-1", name="scope confirmation block",          severity=YELLOW, layer=LAYER, check=check_lc1_scope_confirmation,       applies_to=APPLIES_TO),
    Rule(id="LC-2", name="13H toggle declaration",            severity=YELLOW, layer=LAYER, check=check_lc2_toggle_declaration,       applies_to=APPLIES_TO),
    Rule(id="LC-3", name="13H toggle respected",              severity=HARD,   layer=LAYER, check=check_lc3_toggle_respected,         applies_to=APPLIES_TO),
    Rule(id="LC-4", name="locked asset order",                severity=YELLOW, layer=LAYER, check=check_lc4_locked_order,             applies_to=APPLIES_TO),
    Rule(id="LC-5", name="4-page funnel deliverable",         severity=HARD,   layer=LAYER, check=check_lc5_funnel_complete,          applies_to=APPLIES_TO),
    Rule(id="LC-6", name="no call-booking lang pre-conversion", severity=HARD,   layer=LAYER, check=check_lc6_funnel_forbidden_phrases, applies_to=APPLIES_TO),
    Rule(id="LC-7", name="no out-of-scope asset bundled",     severity=HARD,   layer=LAYER, check=check_lc7_out_of_scope_asset,       applies_to=APPLIES_TO),
]
