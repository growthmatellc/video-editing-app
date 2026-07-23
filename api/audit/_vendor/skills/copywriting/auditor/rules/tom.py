"""tom.py — Tom Render T-1 to T-20 mechanical checks.

Source-of-truth: skills/copywriting/references/tom-craft-rules.md

Mechanical layer implements the rules that can be checked deterministically
via regex/parsing. Semantic nuance (T-9 credential binding, T-11 promise lines,
T-19 setup-vs-avatar-voice disambiguation, T-20 mechanism reveal nuance)
goes in rules/semantic.py.

Rules implemented here (HARD severity unless noted):
  T-7  · no em dashes (— or –)
  T-8  · inline action links at moments of action (live-event reminder emails)
  T-12 · no defensive framing patterns (banned phrases like "Even if you don't")
  T-15 · unit clarity on numbers (catches unitless per-100g style)
  T-16 · bridge connectors present (YELLOW · presence count, not error)
  T-17 · secondary CTAs stacked in confirmation emails (YELLOW)
  T-18 · NO countdown openings (the big one · catches "X days from..." openers)
  T-19 · NO setup-statement openings (catches "I want to tell you about X" pattern)
  T-20 · NO mechanism reveal in pre-webinar emails (mechanical pass · detects known
         mechanism names + specific threshold patterns; semantic nuance in semantic.py)
"""

from __future__ import annotations

import re
from typing import List

from skills.copywriting.auditor.lib.parser import BundleSection, ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation


LAYER = "Tom"
APPLIES_TO = {"email_sequence", "email_launch"}


# ────────────────────────────────────────────────────────────────────────────
# T-7 · No em dashes
# ────────────────────────────────────────────────────────────────────────────

EM_DASH_RE = re.compile(r"[—–]")  # em dash + en dash
# Sign-off pattern · `— Coach Trent` or `— Coach Trent` at start of line or
# inline as "See you there. — Coach Trent" · these are conventional sign-offs
# and were NEVER flagged by Tom in v2 or v5 reviews. Exempt from T-7.
SIGNOFF_EXEMPT_RE = re.compile(
    # Matches: "— Coach Trent" · "— Dr. Dex" · "— Coach Trent (no reply)" · "See you there. — Coach Trent"
    r"(?:^|\.\s+)[—–]\s*(?:(?:Coach|Dr\.?)\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s*(?:\([^)]+\))?\s*$",
    re.MULTILINE,
)

def check_t7_no_em_dashes(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for section in bundle.all_communication_sections:
        for line_no, content in section.body_lines:
            # Skip if this line is purely a sign-off (e.g., "— Coach Trent"
            # or "See you there. — Coach Trent" pattern)
            stripped = content.strip()
            if SIGNOFF_EXEMPT_RE.search(stripped):
                continue
            if EM_DASH_RE.search(content):
                violations.append(Violation(
                    rule_id="T-7",
                    rule_name="no em dashes",
                    severity=HARD,
                    section_id=section.section_id,
                    line_no=line_no,
                    line_content=content.strip(),
                    message="Em dash detected (— or –). Tom flags this as an AI tell.",
                    fix_hint="Replace with `·` middle-dot, comma, or period.",
                ))
    return violations


# ────────────────────────────────────────────────────────────────────────────
# T-8 · Inline action links at moments of action
# ────────────────────────────────────────────────────────────────────────────

# Emails whose description / timing indicates "moment of action"
MOMENT_OF_ACTION_KEYWORDS = (
    "live in",
    "hour out",
    "1 hour",
    "one hour",
    "minutes before",
    "minutes out",
    "in 5",
    "five minutes",
    "5 minutes",
    "join your",
    "going live",
)

LIVE_ZOOM_LINK_RE = re.compile(
    r"(\{\{contact\.live_webinar_zoom_join_link\}\}"  # contact field
    r"|\{\{contact\.strategy_session_zoom_link\}\}"   # post-booking
    r"|\(button URL:\s*\{\{contact\.[^}]+_zoom[^}]*\}\})"
    r"|https?://(?:[\w-]+\.)?zoom\.us/"  # rare but possible
    , re.IGNORECASE,
)

def check_t8_inline_action_links(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    # Build word-boundary regex from keywords so e.g., "in 5" doesn't match "origIN 5"
    moa_pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(k) for k in MOMENT_OF_ACTION_KEYWORDS) + r")\b",
        re.IGNORECASE,
    )
    for section in bundle.emails:
        # Determine if this is a "moment of action" email
        desc = (section.description or "").lower()
        timing = (section.timing_label or "").lower()
        combined = f"{desc} {timing}"
        # Filter out post-event timings · "1 hour after webinar ends" is NOT
        # a moment-of-action email even though it contains "1 hour"
        if "after" in timing:
            continue
        is_moment_of_action = bool(moa_pattern.search(combined))
        if not is_moment_of_action:
            continue

        # Check whether the body contains an inline zoom join link
        has_link = LIVE_ZOOM_LINK_RE.search(section.body or "")
        # Also accept [BUTTON] + (button URL:) declaration as an inline link
        has_button_with_url = (
            re.search(r"\[(JOIN[^\]]*)\]\s*\n\(button URL:", section.body or "", re.IGNORECASE)
            or re.search(r"\[(JOIN[^\]]*)\]\s*\(button URL:", section.body or "", re.IGNORECASE)
        )
        if not has_link and not has_button_with_url:
            violations.append(Violation(
                rule_id="T-8",
                rule_name="inline action links at moments of action",
                severity=HARD,
                section_id=section.section_id,
                line_no=section.start_line,
                line_content=(section.description or "")[:100],
                message=(
                    "Moment-of-action email but no inline Zoom join link found. "
                    "Tom: never make the reader app-switch to find the link."
                ),
                fix_hint=(
                    "Add `{{contact.live_webinar_zoom_join_link}}` inline in the body, or "
                    "include a `[JOIN ...]` button with `(button URL: {{contact.live_webinar_zoom_join_link}})`."
                ),
            ))
    return violations


# ────────────────────────────────────────────────────────────────────────────
# T-12 · No defensive framing patterns
# ────────────────────────────────────────────────────────────────────────────

DEFENSIVE_FRAMING_PATTERNS = [
    (r"\bEven if you don'?t\b", "'Even if you don't...' pattern · defensive framing"),
    (r"\bWhether or not you decide\b", "'Whether or not you decide...' pattern · defensive framing"),
    (r"\bJust in case [^,]+ isn'?t for you\b", "'Just in case X isn't for you...' pattern · defensive framing"),
    (r"\bEven if today isn'?t the right\b", "'Even if today isn't the right time' pattern · defensive framing"),
    (r"\bno pressure\b", "'No pressure' framing · signals lack of confidence (Tom-flagged)"),
]

def check_t12_no_defensive_framing(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for section in bundle.all_communication_sections:
        for line_no, content in section.body_lines:
            for pat, msg in DEFENSIVE_FRAMING_PATTERNS:
                if re.search(pat, content, re.IGNORECASE):
                    violations.append(Violation(
                        rule_id="T-12",
                        rule_name="promise framing over defensive framing",
                        severity=HARD,
                        section_id=section.section_id,
                        line_no=line_no,
                        line_content=content.strip(),
                        message=msg,
                        fix_hint=(
                            "Replace with promise framing: 'By the end you're going to leave with [benefit]'. "
                            "Promise > defensive, every time."
                        ),
                    ))
    return violations


# ────────────────────────────────────────────────────────────────────────────
# T-15 · Unit clarity on numbers
# ────────────────────────────────────────────────────────────────────────────

# Catches "588 per 100g" without "cal" or "calorie" unit
UNITLESS_PER_100G_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s+per\s+100\s?g\b",
    re.IGNORECASE,
)

def check_t15_unit_clarity(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for section in bundle.all_communication_sections:
        for line_no, content in section.body_lines:
            # Check if "per 100g" appears without a unit (cal/calorie/cals)
            for match in UNITLESS_PER_100G_RE.finditer(content):
                # Look 20 chars before to check for cal/cals/calorie
                start = max(0, match.start() - 20)
                preceding = content[start:match.start()]
                if not re.search(r"\b(cal|cals|calorie|calories)\b", preceding, re.IGNORECASE):
                    violations.append(Violation(
                        rule_id="T-15",
                        rule_name="unit clarity on numbers",
                        severity=HARD,
                        section_id=section.section_id,
                        line_no=line_no,
                        line_content=content.strip(),
                        message=f"Unitless 'per 100g' detected near '{match.group(0)}'.",
                        fix_hint=f"Use '{match.group(1)} cals per 100g' instead.",
                    ))
    return violations


# ────────────────────────────────────────────────────────────────────────────
# T-18 · NO countdown openings
# ────────────────────────────────────────────────────────────────────────────

# Patterns that indicate a countdown opener (banned · except for 1-day, 1-hour, 5-min reminders)
COUNTDOWN_OPENER_PATTERNS = [
    re.compile(r"^[^.]*\b(?:two|three|four|five|six|seven|eight|nine|ten|\d+)\s+days?\b[^.]*\.", re.IGNORECASE),
    re.compile(r"^[^.]*\b\d+\s+days?\s+from\b", re.IGNORECASE),
    re.compile(r"^[^.]*\b\d+\s+days?\s+until\b", re.IGNORECASE),
    re.compile(r"^(?:two|three|four|five|six|seven|eight|nine|ten)\s+days?\.\s*$", re.IGNORECASE),
]

# Whitelist · countdowns allowed as openers when the countdown IS the news
ALLOWED_COUNTDOWN_TIMING_KEYWORDS = (
    "1 hour", "one hour", "hour out", "hour before",
    "tomorrow", "1 day", "one day", "day before",
    "5 minutes", "five minutes", "minutes before", "minutes out", "live in",
    "in 5",
)

def _is_allowed_countdown_email(section: BundleSection) -> bool:
    """Return True if this is a 1-day, 1-hour, or 5-min reminder where countdown IS news."""
    desc = (section.description or "").lower()
    timing = (section.timing_label or "").lower()
    combined = f"{desc} {timing}"
    return any(kw in combined for kw in ALLOWED_COUNTDOWN_TIMING_KEYWORDS)


def check_t18_no_countdown_openings(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for section in bundle.emails:
        # Skip if allowed-countdown email
        if _is_allowed_countdown_email(section):
            continue
        opener = section.opening_line
        if not opener:
            continue
        # Strip the {{contact.first_name}}, prefix if present, leaving just the substantive opener
        stripped = re.sub(r"^\{\{contact\.first_name\}\}\s*,\s*", "", opener).strip()
        # Test against all countdown patterns
        for pat in COUNTDOWN_OPENER_PATTERNS:
            if pat.match(stripped):
                violations.append(Violation(
                    rule_id="T-18",
                    rule_name="no countdown openings",
                    severity=HARD,
                    section_id=section.section_id,
                    line_no=section.body_lines[0][0] if section.body_lines else section.start_line,
                    line_content=opener[:200],
                    message=(
                        f"Email opens with a countdown ('{stripped[:60]}...'). Tom-flagged pattern. "
                        "Countdown can come later in body if it earns its place, but not as the opener."
                    ),
                    fix_hint=(
                        "Open with the reader-interest hook: avatar voice quote, recognizable scene, "
                        "or credential-bound-to-outcome line (T-9 pattern). "
                        "Allowed exceptions: 1-day-before, 1-hour-before, 5-min-before reminders."
                    ),
                ))
                break  # one match is enough · move to next section
    return violations


# ────────────────────────────────────────────────────────────────────────────
# T-19 · NO setup-statement openings
# ────────────────────────────────────────────────────────────────────────────

# Banned setup-statement opener patterns
SETUP_STATEMENT_OPENERS = [
    re.compile(r"^I\s+want\s+to\s+tell\s+you\s+about\b", re.IGNORECASE),
    re.compile(r"^Let\s+me\s+tell\s+you\s+about\b", re.IGNORECASE),
    re.compile(r"^Let\s+me\s+show\s+you\b", re.IGNORECASE),
    re.compile(r"^I\s+want\s+to\s+show\s+you\b", re.IGNORECASE),
    re.compile(r"^Before\s+we\s+get\s+(?:there|started|into)\b", re.IGNORECASE),
    re.compile(r"^I\s+want\s+to\s+take\s+one\s+(?:thought|thing)\s+off\s+the\s+table\b", re.IGNORECASE),
    re.compile(r"^I\s+want\s+to\s+be\s+(?:straight|honest|real)\s+with\s+you\b", re.IGNORECASE),
    re.compile(r"^Here'?s\s+a\s+story\s+about\b", re.IGNORECASE),
    re.compile(r"^I'?m\s+going\s+to\s+share\s+(?:something|a\s+story)\b", re.IGNORECASE),
    re.compile(r"^Today\s+I\s+want\s+to\s+talk\s+about\b", re.IGNORECASE),
    re.compile(r"^I\s+want\s+to\s+share\s+something\s+with\s+you\b", re.IGNORECASE),
]

def check_t19_no_setup_openings(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    violations = []
    for section in bundle.emails:
        opener = section.opening_line
        if not opener:
            continue
        stripped = re.sub(r"^\{\{contact\.first_name\}\}\s*,\s*", "", opener).strip()
        # Remove leading bold markers
        stripped = re.sub(r"^\*+", "", stripped).strip()
        for pat in SETUP_STATEMENT_OPENERS:
            if pat.match(stripped):
                violations.append(Violation(
                    rule_id="T-19",
                    rule_name="no setup-statement openings",
                    severity=HARD,
                    section_id=section.section_id,
                    line_no=section.body_lines[0][0] if section.body_lines else section.start_line,
                    line_content=opener[:200],
                    message=(
                        f"Email opens with a setup statement ('{stripped[:60]}...'). Tom-flagged: "
                        "setup openers fail the 5-second rule (reader works for the relevance)."
                    ),
                    fix_hint=(
                        "Tom-approved openers: (a) avatar-voice quote first · `[Name] said to me \"[verbatim]\"`, "
                        "(b) direct scene the avatar recognizes · `Imagine two plates. Same calories.`, "
                        "(c) credential-bound-to-outcome line for origin emails · `I quit X to help you Y.`"
                    ),
                ))
                break
    return violations


# ────────────────────────────────────────────────────────────────────────────
# T-20 · NO mechanism reveal in pre-webinar emails (mechanical pass)
# ────────────────────────────────────────────────────────────────────────────

# Mechanism names that are CLIENT-SPECIFIC · check semantic.py for the more nuanced version.
# This mechanical check looks for known reveal patterns: explicit name-drop + thresholds + "that's the whole game"
KNOWN_MECHANISM_NAMES_TRENT = [
    r"\bCaloric\s+Density\s+Index\b",
]
MECHANISM_THRESHOLD_PATTERNS = [
    re.compile(r"\bUnder\s+\d+\s*:\s*", re.IGNORECASE),
    re.compile(r"\b\d+\s*to\s*\d+\s*:\s*", re.IGNORECASE),
    re.compile(r"\bOver\s+\d+\s*:\s*", re.IGNORECASE),
    re.compile(r"\bthat'?s\s+the\s+whole\s+(?:game|test)\b", re.IGNORECASE),
]

# Pre-webinar emails are those in sequence 1
def _is_pre_webinar_email(section: BundleSection, bundle: ParsedBundle) -> bool:
    if section.section_type != "email":
        return False
    # Sequence 1 = pre-webinar by convention
    if section.sequence == 1:
        return True
    # Also pre-webinar: emails whose timing label contains "before"
    timing = (section.timing_label or "").lower()
    if "before" in timing and "session" not in timing and "call" not in timing:
        return True
    return False


def check_t20_no_mechanism_reveal_pre_webinar(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """
    Mechanical pass: only flags the DEEP-mechanic name (e.g., 'Caloric Density Index')
    + threshold reveal patterns. Does NOT flag the public canonical mechanism name
    (e.g., 'Volume Eating') because that's the offer/workshop name and is allowed.

    Semantic nuance (does the email actually reveal the framework structure even
    without the name?) is delegated to rules/semantic.py · SEM-T20.
    """
    violations = []
    client_data = ctx.get("client_data")
    # Per-client deep-mechanic name patterns · only the names Tom said NEVER tease
    # NOT the public canonical name (e.g., Trent's "Volume Eating" · the offer name)
    mechanism_patterns = []
    if client_data and client_data.slug == "trent-harrison":
        mechanism_patterns.extend(KNOWN_MECHANISM_NAMES_TRENT)
    # NOTE: deliberately NOT adding client_data.mechanism_source_of_truth (canonical
    # name) because it's the workshop/offer name and shows up in subject lines, etc.

    for section in bundle.emails:
        if not _is_pre_webinar_email(section, bundle):
            continue
        # Check for mechanism name reveal
        for line_no, content in section.body_lines:
            # Mechanism name detection (configured per-client)
            for pat_str in mechanism_patterns:
                if re.search(pat_str, content, re.IGNORECASE):
                    violations.append(Violation(
                        rule_id="T-20",
                        rule_name="no mechanism reveal in pre-webinar emails",
                        severity=HARD,
                        section_id=section.section_id,
                        line_no=line_no,
                        line_content=content.strip()[:200],
                        message=(
                            f"Pre-webinar email contains mechanism name reveal. "
                            "Tom: 'DO NOT GIVE IT AWAY. Tease it.'"
                        ),
                        fix_hint=(
                            "Tease the mechanism's existence + outcome only. Don't name it, don't reveal "
                            "the framework, don't reveal thresholds. The workshop is the payoff."
                        ),
                    ))
            # Threshold reveal detection
            for pat in MECHANISM_THRESHOLD_PATTERNS:
                if pat.search(content):
                    violations.append(Violation(
                        rule_id="T-20",
                        rule_name="no mechanism reveal in pre-webinar emails",
                        severity=HARD,
                        section_id=section.section_id,
                        line_no=line_no,
                        line_content=content.strip()[:200],
                        message=(
                            "Pre-webinar email contains framework threshold / 'whole game' reveal. "
                            "Tom: tease only."
                        ),
                        fix_hint=(
                            "Strip the thresholds / framework structure. End on a tease like "
                            "'I'll show you what it is on the {{custom_values.live_webinar_date}}.'"
                        ),
                    ))
    return violations


# ────────────────────────────────────────────────────────────────────────────
# T-16 · Bridge connectors (YELLOW · presence check, not error)
# ────────────────────────────────────────────────────────────────────────────

BRIDGE_CONNECTORS = ["Remember,", "See,", "But", "Here's the thing"]

def check_t16_bridge_connectors(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Warn (YELLOW) if a LONG-FORM email has zero bridge connectors · suggests poor rhythm.

    Skip operational + reminder emails where short, direct, operational tone is
    correct: booking confirmations, hour-before reminders, agenda previews, etc.
    These don't need bridges · they're action emails not narrative emails.
    """
    violations = []
    # Operational emails (skip · they don't need narrative bridges)
    OPERATIONAL_KEYWORDS = (
        "confirmation", "booking", "agenda", "live in", "hour out",
        "hour before", "hours before", "minutes before", "in 5",
        "five minutes", "5 minutes", "spots left", "qualification",
        "live in 5", "going live", "live now", "tomorrow at",
        "reminders", "session reminder",
    )
    for section in bundle.emails:
        body = section.body or ""
        if len(body) < 800:  # short emails (confirmation, 5-min, reminders) don't need bridges
            continue
        # Skip operational emails by description / timing
        desc = (section.description or "").lower()
        timing = (section.timing_label or "").lower()
        combined = f"{desc} {timing}"
        if any(kw in combined for kw in OPERATIONAL_KEYWORDS):
            continue
        connector_count = 0
        for connector in BRIDGE_CONNECTORS:
            connector_count += len(re.findall(re.escape(connector), body))
        if connector_count == 0:
            violations.append(Violation(
                rule_id="T-16",
                rule_name="bridge connectors keep reader moving",
                severity=YELLOW,
                section_id=section.section_id,
                line_no=section.start_line,
                line_content=(section.description or "")[:100],
                message=(
                    "No bridge connectors detected (`Remember,`, `See,`, `But`, `Here's the thing`). "
                    "Tom: these are momentum · the reader who reads 'See,' reads the next sentence."
                ),
                fix_hint=(
                    "Add a bridge connector at major beats · after setup paragraphs, before pivots, "
                    "between sections that risk losing the reader."
                ),
            ))
    return violations


# ────────────────────────────────────────────────────────────────────────────
# T-17 · Secondary CTAs in confirmation emails (YELLOW)
# ────────────────────────────────────────────────────────────────────────────

def check_t17_secondary_ctas_in_confirmation(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Warn if the first/confirmation email doesn't stack a low-friction secondary CTA."""
    violations = []
    # Find the confirmation email (sequence 1, "confirmation" in description)
    for section in bundle.emails:
        desc = (section.description or "").lower()
        if section.sequence != 1 or "confirmation" not in desc:
            continue
        body = section.body or ""
        # Check for Instagram / podcast / social CTA
        has_secondary_cta = any([
            "instagram" in body.lower(),
            "podcast" in body.lower(),
            "follow me" in body.lower(),
            "follow us" in body.lower(),
            "subscribe" in body.lower(),
        ])
        if not has_secondary_cta:
            violations.append(Violation(
                rule_id="T-17",
                rule_name="stack secondary CTA in confirmation emails",
                severity=YELLOW,
                section_id=section.section_id,
                line_no=section.start_line,
                line_content="(confirmation email)",
                message=(
                    "Confirmation email has no secondary low-friction CTA. "
                    "Tom: stack Instagram follow with social proof in the P.S. to capture non-immediate-buyers."
                ),
                fix_hint=(
                    "Add a P.S. with Instagram follow CTA + social proof: "
                    "`P.S. Follow me on Instagram, where I share strategies with over X people just like you: ...`"
                ),
            ))
    return violations


# ────────────────────────────────────────────────────────────────────────────
# RULES registry
# ────────────────────────────────────────────────────────────────────────────

# ────────────────────────────────────────────────────────────────────────────
# T-21 · No "join from your phone" recommendations (Tom 2026-06-25)
# ────────────────────────────────────────────────────────────────────────────

PHONE_JOIN_PATTERNS = [
    re.compile(r"\bjoin\s+(?:with\s+)?(?:one\s+tap\s+)?from\s+your\s+phone\b", re.IGNORECASE),
    re.compile(r"\beasiest\s+way\s+to\s+join\s+from\s+your\s+phone\b", re.IGNORECASE),
    re.compile(r"\bfrom\s+your\s+phone\.\s*$", re.IGNORECASE | re.MULTILINE),
]

def check_t21_no_phone_join_push(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Tom 2026-06-25: don't push attendees to join from phone · we want them on desktop."""
    violations = []
    for section in bundle.emails:
        for line_no, content in section.body_lines:
            for pat in PHONE_JOIN_PATTERNS:
                if pat.search(content):
                    violations.append(Violation(
                        rule_id="T-21",
                        rule_name="no 'join from phone' push",
                        severity=HARD,
                        section_id=section.section_id,
                        line_no=line_no,
                        line_content=content.strip(),
                        message="Tom: 'We want them on desktop. Phone is better than not attending, but we don't push it.'",
                        fix_hint="End at 'one tap' or 'one click' · drop the 'from your phone' part.",
                    ))
                    break
    return violations


# ────────────────────────────────────────────────────────────────────────────
# T-22 · Confirmation SMS must request reply callback (Tom 2026-06-25)
# ────────────────────────────────────────────────────────────────────────────

REPLY_CALLBACK_PATTERNS = [
    re.compile(r"\b(?:respond|reply|text)\b[^.]*\b(?:to\s+this|with|back)\b", re.IGNORECASE),
    re.compile(r"\breply\s+(?:with\s+)?[\"']?(?:READY|YES|CONFIRM)[\"']?", re.IGNORECASE),
]

def check_t22_confirmation_sms_reply_callback(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Tom 2026-06-25: confirmation SMS must ask for reply (READY) for accurate headcount."""
    violations = []
    for section in bundle.sms_messages:
        # Only check the FIRST/confirmation SMS · post-opt-in
        if section.number not in ("1", "#1"):
            continue
        timing = (section.timing_label or "").lower()
        if "immediate" not in timing:
            continue
        body = section.body or ""
        has_callback = any(pat.search(body) for pat in REPLY_CALLBACK_PATTERNS)
        if not has_callback:
            violations.append(Violation(
                rule_id="T-22",
                rule_name="confirmation SMS must request reply callback",
                severity=HARD,
                section_id=section.section_id,
                line_no=section.start_line,
                line_content=body[:200],
                message=(
                    "Tom: 'We want them to reply with READY so we have an accurate headcount.' "
                    "The confirmation SMS is the right moment to ask for that callback."
                ),
                fix_hint=(
                    "Add 'Please respond to this text with \"READY\" so we know you got it' "
                    "(or equivalent). Combines confirmation + engagement."
                ),
            ))
    return violations


# ────────────────────────────────────────────────────────────────────────────
# T-27 · No cross-message link references (Tom 2026-06-25 · strengthens T-8)
# ────────────────────────────────────────────────────────────────────────────

CROSS_MESSAGE_LINK_REF_PATTERNS = [
    re.compile(r"\bin\s+the\s+(?:last|previous|earlier)\s+(?:text|sms|email|message)\b", re.IGNORECASE),
    re.compile(r"\bfrom\s+the\s+(?:last|previous|earlier)\s+(?:text|sms|email|message)\b", re.IGNORECASE),
    re.compile(r"\bI\s+sent\s+you\s+(?:earlier|before)\b", re.IGNORECASE),
    re.compile(r"\btap\s+the\s+(?:zoom\s+)?link\s+(?:in|from)\s+(?:the\s+)?(?:last|previous|earlier)\s+text\b", re.IGNORECASE),
    re.compile(r"\bcheck\s+(?:the\s+)?(?:last|previous|earlier)\s+(?:text|email|message)\s+for\s+(?:the\s+)?link\b", re.IGNORECASE),
]

def check_t27_no_cross_message_link_references(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Tom 2026-06-25: 'NEVER ask them to take action in a different place. Any links MUST be contained in the email/SMS they're reading right now.'"""
    violations = []
    for section in bundle.all_communication_sections:
        for line_no, content in section.body_lines:
            for pat in CROSS_MESSAGE_LINK_REF_PATTERNS:
                if pat.search(content):
                    violations.append(Violation(
                        rule_id="T-27",
                        rule_name="no cross-message link references",
                        severity=HARD,
                        section_id=section.section_id,
                        line_no=line_no,
                        line_content=content.strip(),
                        message=(
                            "Tom: 'NEVER ask them to take an action in a different place to where they are right now. "
                            "Any links to click MUST be contained in the email/ad/sales page they're reading.'"
                        ),
                        fix_hint=(
                            "Include the link directly in THIS message: `{{contact.live_webinar_zoom_join_link}}` "
                            "or `[BUTTON] (button URL: {{...}})`. Don't reference other messages."
                        ),
                    ))
                    break
    return violations


RULES = [
    Rule(id="T-7",  name="no em dashes",                       severity=HARD,   layer=LAYER, check=check_t7_no_em_dashes,                       applies_to=APPLIES_TO),
    Rule(id="T-8",  name="inline action links",                severity=HARD,   layer=LAYER, check=check_t8_inline_action_links,                applies_to=APPLIES_TO),
    Rule(id="T-12", name="promise over defensive framing",     severity=HARD,   layer=LAYER, check=check_t12_no_defensive_framing,              applies_to=APPLIES_TO),
    Rule(id="T-15", name="unit clarity on numbers",            severity=HARD,   layer=LAYER, check=check_t15_unit_clarity,                      applies_to=APPLIES_TO),
    Rule(id="T-16", name="bridge connectors",                  severity=YELLOW, layer=LAYER, check=check_t16_bridge_connectors,                 applies_to=APPLIES_TO),
    Rule(id="T-17", name="secondary CTAs in confirmation",     severity=YELLOW, layer=LAYER, check=check_t17_secondary_ctas_in_confirmation,    applies_to=APPLIES_TO),
    Rule(id="T-18", name="no countdown openings",              severity=HARD,   layer=LAYER, check=check_t18_no_countdown_openings,             applies_to=APPLIES_TO),
    Rule(id="T-19", name="no setup-statement openings",        severity=HARD,   layer=LAYER, check=check_t19_no_setup_openings,                 applies_to=APPLIES_TO),
    Rule(id="T-20", name="no mechanism reveal pre-webinar",    severity=HARD,   layer=LAYER, check=check_t20_no_mechanism_reveal_pre_webinar,   applies_to=APPLIES_TO),
    Rule(id="T-21", name="no 'join from phone' push",          severity=HARD,   layer=LAYER, check=check_t21_no_phone_join_push,                applies_to=APPLIES_TO),
    Rule(id="T-22", name="confirmation SMS reply callback",    severity=HARD,   layer=LAYER, check=check_t22_confirmation_sms_reply_callback,   applies_to=APPLIES_TO),
    Rule(id="T-27", name="no cross-message link references",   severity=HARD,   layer=LAYER, check=check_t27_no_cross_message_link_references,  applies_to=APPLIES_TO),
]
