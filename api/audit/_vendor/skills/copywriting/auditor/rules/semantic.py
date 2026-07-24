"""semantic.py — Claude-as-judge semantic checks for nuance rules.

These rules require LLM-level understanding of the copy. The checks call
Claude Haiku with strict JSON output schemas and a hard pass/fail verdict.

Skipped when --no-semantic flag is set (for dev cycles + cost control).

Rules implemented (Phase 3):
  SEM-T19 · setup-statement vs avatar-voice disambiguation (catches "fancy setup" disguised as scene)
  SEM-T20 · mechanism reveal nuance (catches mechanism leak that mechanical pattern missed)
  SEM-TL8 · title + mechanism are obvious to the target audience and point at their desire
  SEM-AL  · the body argument builds context-first, in order, and earns its close (AL-1..AL-5)
  SEM-VR  · voice register match against the client's style-guide (built 2026-07-16)

NOT implemented — do not assume these run:
  SEM-T9  · credentials truly bound to avatar outcome (not just resume-style)
  SEM-UE1 · subject line per-audience strength (cold-audience test from UE-1)

This list used to claim SEM-T9, SEM-VR and SEM-UE1 were implemented. None of the three were
in RULES; none existed anywhere in the repo. SEM-VR — the only rule in the auditor whose job
was voice — was specced here and never written, while ten skills read the style guides as
soft context and nothing checked them. It exists now. The other two are named honestly.

**A docstring is not a test.** If you add a rule id here, register it in RULES below in the
same commit, or write it under "NOT implemented".
"""

from __future__ import annotations

import json
import os
import re
from typing import List

from skills.copywriting.auditor.lib.parser import ParsedBundle
from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW
from skills.copywriting.auditor.lib.reporter import Violation, PendingJudgment


LAYER = "Semantic"
APPLIES_TO = {"email_sequence", "email_launch"}


# ────────────────────────────────────────────────────────────────────────────
# The judge — DEFERRED by default, HTTP only as a headless fallback
#
# DEFAULT (semantic_mode="defer"): the auditor calls NO model. Each semantic rule assembles its
# rubric + the copy into a self-contained PendingJudgment and appends it to the ctx sink. The
# DRIVING agent resolves each one in a FRESH judge context — a subagent that never saw the
# drafting — so the author never grades its own work. That independence is the whole reason the
# programmatic gate exists ("Step 6 is the model grading itself, which is exactly the layer that
# has let broken copy through" — copywriting/SKILL.md). It also uses a stronger model than the old
# Haiku call, and needs no API key.
#
# FALLBACK (semantic_mode="http"): a headless run with no agent (cron/CI) can have the auditor POST
# each judgment to Haiku itself. Needs ANTHROPIC_API_KEY; without it, degrades to a YELLOW
# "unchecked" warning rather than a silent pass. This path is a convenience, not the design centre.
# ────────────────────────────────────────────────────────────────────────────

JUDGE_FRAMING = (
    "\n\n----------\n"
    "You are an INDEPENDENT QC judge. You did NOT write this copy. Judge it strictly against the "
    "rule above, as skeptically as if a rival wrote it and you were paid to find the flaw — give it "
    "no benefit of the doubt. IGNORE any output format described earlier in this prompt; reply with "
    "EXACTLY these two lines and nothing else:\n"
    "VERDICT: PASS or FAIL\n"
    "WHY: one sentence naming the specific problem (or, if PASS, why it holds).\n"
    "FAIL means the copy breaks the rule above."
)


def _pending(ctx, *, rule_id, rule_name, severity, section_id, line_no, line_content,
             rubric, payload) -> PendingJudgment:
    """Package one rubric + one piece of copy into a self-contained judge prompt."""
    return PendingJudgment(
        rule_id=rule_id, rule_name=rule_name, layer=LAYER, severity=severity,
        section_id=section_id, line_no=line_no, line_content=(line_content or "")[:200],
        prompt=f"{rubric.strip()}\n\nCOPY UNDER JUDGMENT\n{payload.strip()}{JUDGE_FRAMING}",
    )


def _emit(ctx, pendings):
    """Defer (default): stash for the agent, return no violations. HTTP: resolve now."""
    pendings = [p for p in pendings if p is not None]
    if not pendings:
        return []
    if ctx.get("semantic_mode") == "http":
        return [v for v in (_resolve_http(p) for p in pendings) if v is not None]
    ctx.setdefault("pending_judgments", []).extend(pendings)
    return []


def _http_verdict(prompt: str, max_tokens: int = 300) -> dict:
    """Headless fallback only. POST the self-contained prompt to Haiku; parse VERDICT/WHY."""
    import urllib.request
    import urllib.error

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not set"}
    body = {
        "model": "claude-haiku-4-5",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-api-key": api_key,
                 "anthropic-version": "2023-06-01"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return {"error": f"API error: {e}"}
    text = "".join(b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text")
    if re.search(r"verdict\s*:\s*fail", text, re.I):
        verdict = "FAIL"
    elif re.search(r"verdict\s*:\s*pass", text, re.I):
        verdict = "PASS"
    else:
        verdict = "UNPARSED"
    m = re.search(r"why\s*:\s*(.+)", text, re.I)
    return {"verdict": verdict, "why": m.group(1).strip() if m else ""}


def _resolve_http(p: PendingJudgment):
    result = _http_verdict(p.prompt)
    if result.get("error") or result.get("verdict") == "UNPARSED":
        return Violation(
            rule_id=p.rule_id, rule_name=p.rule_name, severity=YELLOW,
            section_id=p.section_id, line_no=p.line_no,
            line_content="(semantic judge unavailable)",
            message=f"Semantic check not run: {result.get('error', 'unparsed verdict')}. "
                    f"Unchecked, not passed.",
            fix_hint="Set ANTHROPIC_API_KEY for the headless judge, or run under an agent (default).",
        )
    if result.get("verdict") == "FAIL":
        return Violation(
            rule_id=p.rule_id, rule_name=p.rule_name, severity=p.severity,
            section_id=p.section_id, line_no=p.line_no, line_content=p.line_content,
            message=f"Judge: {result.get('why', 'fails the rule')}",
            fix_hint="See the rule's craft doc for the fix.",
        )
    return None


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
    pendings = []
    for section in bundle.emails:
        opener = section.opening_line
        if not opener:
            continue
        payload = (f"Email section: {section.section_id}\nDescription: {section.description}\n"
                   f"Timing: {section.timing_label or 'N/A'}\nOpening line: {opener}")
        pendings.append(_pending(
            ctx, rule_id="SEM-T19", rule_name="setup-statement nuance (agent judge)",
            severity=YELLOW, section_id=section.section_id,
            line_no=section.body_lines[0][0] if section.body_lines else section.start_line,
            line_content=opener, rubric=SEM_T19_SYSTEM, payload=payload,
        ))
    return _emit(ctx, pendings)


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
    pendings = []
    for section in bundle.emails:
        if section.sequence != 1:  # only pre-webinar emails
            continue
        body = section.body or ""
        if not body.strip():
            continue
        payload = (f"Email section: {section.section_id}\nDescription: {section.description}\n\n"
                   f"Body:\n{body[:3000]}")
        pendings.append(_pending(
            ctx, rule_id="SEM-T20", rule_name="mechanism reveal nuance (agent judge)",
            severity=YELLOW, section_id=section.section_id, line_no=section.start_line,
            line_content=section.description or section.section_id,
            rubric=SEM_T20_SYSTEM, payload=payload,
        ))
    return _emit(ctx, pendings)


# ────────────────────────────────────────────────────────────────────────────
# SEM-TL8 · the title and the mechanism are obvious to the people in the room
#
# TL-1/TL-2 check that a title is specific and carries a verb. TL-7 checks that it shares
# vocabulary with the declared desire. None of them can tell whether the words mean anything
# to the woman reading them — and the mechanism name is checked by nobody at all: TL-6 only
# asks that it be spelled the same way everywhere, PC-2 that it be the locked one.
#
# So `The 5M Method Workshop` clears the whole title layer while naming a thing the audience
# cannot decode and a benefit it never states. A mechanism name is a promise or it is a
# product code. (Lauren, 2026-07-14.)
#
# This is comprehension, not vocabulary, so it lives with the judges and not the regexes —
# a lexical proxy here would emit a green tick that lies. Two tests, both from the avatar's
# chair: can they decode it on sight, and does it point at what they actually came for?
#
# The desire-bound test also carries TL-9 (Lauren, 2026-07-17): the title has to name a
# TANGIBLE result — a concrete thing they can picture — AND a nameable audience, not one or the
# other. A HARD regex for "tangible" would false-fail our own anchor "How Women Over 40 Lose the
# Weight by Eating More, Not Less" (no number, no timeframe, and right), so tangibility rides the
# judge here, not a pattern. references/craft/headline-and-subject-rules.md TL-9.
# ────────────────────────────────────────────────────────────────────────────

TL8_APPLIES_TO = {"webinar_deck", "funnel_pages", "image_ads"}

SEM_TL8_SYSTEM = """You audit headline copy — webinar/workshop titles, funnel-page hero headlines,
and image-ad headlines — plus the method/mechanism name, against craft rule TL-8.

THE TEST (ask it from THIS audience's chair, not a marketer's). Reading only this copy, is it
obvious to the audience:
  (1) WHAT IT SOLVES — the problem, pain, or need the method speaks to? AND
  (2) WHAT SOLUTION IT BRINGS — the concrete outcome / transformation they walk away with, the one
      they actually want?
BOTH must be obvious from the copy itself. If the reader cannot tell what it's for, OR cannot tell
what they'd get, it FAILS. This is the same test whatever the surface — a title, a page hero, or an
ad headline.

How each half fails:
  (1) NOT OBVIOUS WHAT IT SOLVES — insider jargon, an invented abstraction, an initialism or
      letter-count construct ("The 5M Method", "The 3P Framework"), a coined term the audience can't
      decode on sight ("Operational Debt" to someone who has never heard it), or a curiosity hook
      that names no problem at all. If they can't tell what pain it speaks to, it fails.
  (2) NOT OBVIOUS WHAT SOLUTION IT BRINGS — names a topic rather than an outcome, an outcome they
      solved years ago, a benefit so vague they can't picture it ("transform your health", "unlock
      your potential"), or the concrete result is only implied / offloaded to a subtitle. The result
      they want has to be on the copy line itself.

Judge from the audience's words, not the industry's. A term is obvious if THEY use it. A method
name may be metaphorical and still pass if the metaphor lands instantly for them AND points at
their outcome ("Metabolic Fuel" for women told to eat less: obvious problem, obvious solution —
eat more, not less).

The HEADLINE stands on its own: it must make BOTH the problem and the solution obvious by itself.
A curiosity / myth-buster / identity headline that offloads the problem or the solution to the
SUBTITLE fails — the subtitle is supporting context only, it never rescues a headline that leaves
the reader unsure what it solves or what they get. (This is craft rule TL-9: audience + tangible
result on the line.)

You will receive the client's avatar, their declared primary desire, the headline, its supporting
subtitle, and the method/mechanism name."""

AVATAR_FIELDS = (
    "age_range", "gender_split", "professions", "life_stage_majority",
    "sophistication", "awareness_stage", "primary_desire", "primary_desire_negation",
    "not_the_desire",
)


def _avatar_brief(client) -> str:
    """The avatar as the judge needs to see it — who they are, and what they came for."""
    info = getattr(client, "info", None) or {}
    avatar = info.get("avatar_snapshot") or info.get("avatar") or {}
    lines = []
    for key in AVATAR_FIELDS:
        value = avatar.get(key) if isinstance(avatar, dict) else None
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        if isinstance(value, str) and value.strip():
            lines.append(f"{key}: {value.strip()}")
    return "\n".join(lines)


# TL-6's extractor requires the name to start with a capital LETTER, so it reads "5M Method
# Workshop" as "Method Workshop" — blind to the digit-led product codes this rule exists to
# catch. SEM-TL8 captures its own so TL-6's blast radius (what it BLOCKS) stays unchanged.
MECH_NAME_RE = re.compile(
    r"\b([A-Z0-9][\w'’-]*(?:\s+[A-Z][\w'’-]*){0,3})\s+(Workshop|Masterclass)\b"
)


def _mechanism_names(bundle: ParsedBundle, client) -> List[tuple]:
    """The mechanism as this document names it, falling back to the client's locked name.

    -> [(line_no, name)]
    """
    from skills.copywriting.auditor.rules.headlines import NAME_STOPWORDS

    named = []
    seen = set()
    for idx, line in enumerate(bundle.raw_lines):
        for m in MECH_NAME_RE.finditer(line):
            words = [w for w in m.group(1).split() if w.lower() not in NAME_STOPWORDS]
            if not words:
                continue
            name = " ".join(words)
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            named.append((idx + 1, name))

    canonical = getattr(client, "mechanism_source_of_truth", None) if client else None
    if canonical and not any(canonical.lower() in name.lower() for _, name in named):
        named.append((1, canonical))
    return named


def check_sem_tl8_obvious_to_the_audience(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if ctx.get("skip_semantic"):
        return []
    from skills.copywriting.auditor.rules import headlines as hl

    units = hl._title_units(bundle, ctx)
    if not units:
        return []

    client = ctx.get("client_data")
    desire = getattr(client, "primary_desire", None) if client else None
    brief = _avatar_brief(client) if client else ""
    if not desire or not brief:
        # Same stance as TL-7: silence about who the audience is, or what they want, is not a
        # pass. A judge with no avatar would be grading the title against its own assumptions.
        line_no, label, title, _subtitle = units[0]
        return [Violation(
            rule_id="SEM-TL8",
            rule_name="obvious to the audience (semantic)",
            severity=YELLOW,
            section_id=label,
            line_no=line_no,
            line_content=title[:200],
            message="This client declares no avatar snapshot or no primary desire, so the judge "
                    "cannot ask whether the title and mechanism mean anything to the people in "
                    "the room. Unchecked, not passed.",
            fix_hint="Add `avatar_snapshot` (with `primary_desire`) to clients/<slug>/info.json, "
                     "sourced from the Target Audience Brief.",
        )]

    # One title UNIT per judgment: a webinar deck / funnel page has one, an image-ad batch has one
    # per variant. The mechanism name is one per deliverable, judged once.
    mechanisms = _mechanism_names(bundle, client)
    mech_line, mech_name = mechanisms[0] if mechanisms else (units[0][0], "")

    # For an image ad the headline IS the ad, so a "no reason to care" headline should block, not
    # warn — TL-9 fails HARD there. Webinar/funnel titles keep the semantic-layer YELLOW default
    # (a title has a subtitle and body behind it; an ad headline stands alone). The judge's
    # desire_bound test still passes a pain-reframe that points at the outcome, so a legitimate
    # angle is not blanket-blocked — only a headline that gives the reader nothing.
    title_sev = HARD if ctx.get("asset_type") == "image_ads" else YELLOW

    pendings = []
    for (line_no, label, title, subtitle) in units:
        # TL-9: the headline must carry audience + tangible result on its own. The subtitle is
        # passed as context so the judge can tell a genuinely tangible headline from a vague one —
        # it does NOT rescue a curiosity headline that offloads the promise.
        subtitle_block = subtitle.strip() or "(no subtitle on this title)"
        payload = (
            f"AVATAR\n{brief}\n\n"
            f"DECLARED PRIMARY DESIRE\n{desire}\n\n"
            f"HEADLINE — judge THIS: reading it alone, is it obvious to this audience what it SOLVES "
            f"and the SOLUTION it brings?\n{title}\n\n"
            f"SUPPORTING SUBTITLE (context only — it cannot rescue a headline that leaves the problem "
            f"or the solution unclear)\n{subtitle_block}"
        )
        pendings.append(_pending(
            ctx, rule_id="SEM-TL8", rule_name="title obvious + desire-bound (agent judge)",
            severity=title_sev, section_id=label, line_no=line_no, line_content=title,
            rubric=SEM_TL8_SYSTEM, payload=payload,
        ))
    if mech_name:
        payload = (
            f"AVATAR\n{brief}\n\n"
            f"DECLARED PRIMARY DESIRE\n{desire}\n\n"
            f"METHOD / MECHANISM NAME — judge THIS: is it obvious to this audience what it solves and "
            f"the solution it brings?\n{mech_name}"
        )
        pendings.append(_pending(
            ctx, rule_id="SEM-TL8", rule_name="mechanism obvious + desire-bound (agent judge)",
            severity=YELLOW, section_id="Mechanism name", line_no=mech_line, line_content=mech_name,
            rubric=SEM_TL8_SYSTEM, payload=payload,
        ))
    return _emit(ctx, pendings)


# ────────────────────────────────────────────────────────────────────────────
# SEM-AL · the body argument builds context-first, in order, and earns its close
#
# The auditor already checks that the right SECTIONS are present in the right ORDER
# (funnel_pages FP, sales_page SP, launch_copy LC) and that individual LINES open with
# relevance (T-19) and tease before a demo (T-11). Nothing between those altitudes checked
# whether the body ARGUMENT flows: whether each point is set up before it's asserted, whether
# the order skips a rung, and whether the points sum to the offer by the CTA.
#
# That is the oldest principle in direct response, under three names — Schwartz's gradualization
# ("a claim succeeds only on the preparation made for it"), Sugarman's slippery slide (one idea
# per unit, each greased into the next), and Todd Brown's belief chain (deliver the beliefs in
# the proper sequence so the close is earned). Full rule + sources + worked examples:
# references/craft/argument-logic-rules.md. (Lauren, 2026-07-15.)
#
# Comprehension, not vocabulary — so it lives with the judge, YELLOW, not with the regexes. One
# judge call grades all five facets of one holistic judgment; a violation is emitted per facet
# that fails, each naming the AL principle. Unlike SEM-TL8, the argument lives inside the copy,
# so client_data only SHARPENS the judgment (AL-5 gets the offer's required beliefs) — it is not
# required. A short or empty document has no argument to grade; those are owned by each module's
# XX-0 parse guard, so SEM-AL stays silent rather than manufacture a pass.
# ────────────────────────────────────────────────────────────────────────────

AL_APPLIES_TO = {
    "funnel_pages", "sales_page", "webinar_deck", "vsl", "video_ads",
    "email_sequence", "email_launch",
}

# Below this the file has no argument to grade — the parse guards own emptiness, not us.
AL_MIN_WORDS = 120
# The judge reads the whole argument; cap the payload so cost stays bounded on long sales pages.
AL_MAX_CHARS = 12000

# (facet key returned by the judge, AL id, human label)
AL_FACETS = (
    ("context_before_claim", "AL-1", "context before the claim"),
    ("logical_order",        "AL-2", "logical order · the chain does not skip"),
    ("one_idea_per_unit",    "AL-3", "one idea per unit"),
    ("claim_support",        "AL-4", "no naked claim"),
    ("earned_close",         "AL-5", "the close is earned"),
)

SEM_AL_SYSTEM = """You audit the BODY ARGUMENT of a piece of direct-response copy against the
Argument Logic rules (AL-1 to AL-5). You grade the LOGIC of the argument, never its truth — you
cannot fact-check, only judge whether the case is built in an order a reader can follow.

Grounding: Schwartz (gradualization — a claim succeeds only on the preparation made for it),
Sugarman (slippery slide — one idea per unit, each set up before the next), Todd Brown (belief
chain — every belief the offer needs is established, in sequence, before the ask).

Grade each of the five, from the reader's chair:

  AL-1 context_before_claim · Is every point that asks the reader to believe/want/do something
       set up FIRST — the problem, the why-it-matters, or the reason — rather than asserted cold?
  AL-2 logical_order · Does the copy introduce each concept before anything refers back to it?
       FAIL if a mechanism/framework name, or an "as we saw" callback, or an assumed belief
       appears before the copy has introduced/built it. The chain must not skip a rung.
  AL-3 one_idea_per_unit · Does each paragraph or slide advance exactly one idea, with no
       filler line that advances none?
  AL-4 claim_support · Does every point that asks for belief carry its support nearby — a
       reason, proof, mechanism, or example — rather than standing as a naked assertion?
  AL-5 earned_close · By the CTA, has the copy built EVERY belief the reader must hold to say
       yes to THIS offer (mechanism works · works for them · founder can deliver · now is the
       time)? FAIL if the close leans on a belief the argument never built.

You will receive the audience (if known), the offer's declared desire (if known), and the copy.
If the audience/desire are absent, still grade AL-1..AL-5 from the copy itself; AL-5 then judges
against the offer as the copy's own CTA states it.

Return STRICTLY this JSON, no prose outside it, no code fences:
{
  "context_before_claim": {"pass": true|false, "reasoning": "1-2 sentences", "evidence": "the line/point that arrives without setup, or ''"},
  "logical_order":        {"pass": true|false, "reasoning": "...", "evidence": "the forward reference or skipped rung, or ''"},
  "one_idea_per_unit":    {"pass": true|false, "reasoning": "...", "evidence": "the overloaded unit, or ''"},
  "claim_support":        {"pass": true|false, "reasoning": "...", "evidence": "the naked claim, or ''"},
  "earned_close":         {"pass": true|false, "reasoning": "...", "evidence": "the belief the close needs but never built, or ''"}
}"""


def _argument_text(bundle: ParsedBundle) -> str:
    """The published argument, capped. Whole-doc raw text — for a page/deck/script it is the
    argument; for an email sequence it is the belief chain across the emails."""
    text = bundle.raw_text or ""
    return text[:AL_MAX_CHARS]


def check_sem_al_argument_logic(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    if ctx.get("skip_semantic"):
        return []
    # A capture records copy that already ran — evidence, not a deliverable. Do not re-grade it,
    # same stance as SEM-TL8's title check and the shared craft checks.
    from skills.copywriting.auditor.lib import sections as S
    if S.is_capture(bundle.raw_lines):
        return []

    argument = _argument_text(bundle)
    # No argument to grade. Emptiness/unparseable is the job of each module's XX-0 guard; SEM-AL
    # staying silent here is correct, NOT a vacuous pass — it is not the parse gate.
    if len(argument.split()) < AL_MIN_WORDS:
        return []

    client = ctx.get("client_data")
    desire = getattr(client, "primary_desire", None) if client else None
    brief = _avatar_brief(client) if client else ""

    audience_block = brief or "(not declared — grade from the copy itself)"
    desire_block = desire or "(not declared — judge the close against the copy's own CTA)"
    payload = (
        f"AUDIENCE\n{audience_block}\n\n"
        f"OFFER'S DECLARED DESIRE\n{desire_block}\n\n"
        f"COPY\n{argument}"
    )
    p = _pending(
        ctx, rule_id="SEM-AL",
        rule_name="argument builds context-first, earns its close (agent judge)",
        severity=YELLOW, section_id="document", line_no=1,
        line_content="(whole-argument judgment · AL-1..AL-5)",
        rubric=SEM_AL_SYSTEM, payload=payload,
    )
    return _emit(ctx, [p])


# ────────────────────────────────────────────────────────────────────────────
# SEM-VR · voice register match against the client's style-guide
# ────────────────────────────────────────────────────────────────────────────

# SEM-VR reads `bundle.all_communication_sections`, which the SHARED parser populates only
# for emails + SMS. Webinar decks, funnel pages and sales pages parse to zero sections here —
# they carry their own parsers inside their asset modules (which is why SEM-TL8 scopes to
# {webinar_deck, funnel_pages} and reads titles through `headlines._titles` instead).
#
# So `{"*"}` would be a lie in the U10 shape: the rule would be listed as evaluated on a deck,
# read nothing, flag nothing, and print green. Scope to what it can actually read. Extending
# voice checking to decks/funnel pages needs a per-asset body accessor — see
# skills/tone-of-voice/SKILL.md § Known limits.
VR_APPLIES_TO = {"email_sequence", "email_launch"}

SEM_VR_SYSTEM = """You audit marketing copy against ONE client's documented brand voice.

You will receive that client's own voice rules, taken verbatim from their style guide, and a
passage of copy written for them. Judge ONLY against the rules you are given. You have no
outside knowledge of this brand, and "this sounds like decent marketing copy" is not the test —
the test is whether it sounds like THEM.

Most of these rules are categories, not phrases: "Passive voice", "Fear-only language without
empowerment", "Formal/academic language", "Emoji-heavy enthusiasm", "Deep technical register".
A literal string search cannot see any of them. That is why you exist.

Judge conservatively. Flag a passage ONLY when a specific, quotable line violates a specific
rule you were given. Do not flag:
  - vibes, or copy you would have written differently
  - a rule you are inferring rather than reading
  - a single borderline word in an otherwise on-voice passage

If the copy is on-voice, say so. A false flag costs a writer their trust in this gate, and a
gate nobody trusts gets switched off.

ONE EXCEPTION — register mismatch. Separately from the prohibition list, ask: could this copy
plausibly have been written for THIS brand at all? Wrong industry, wrong audience, wrong subject
matter, or a register sharing nothing with the on-brand library above. If it could not, return
FAIL with rule "register mismatch" — even though no specific prohibition was tripped.

This exception exists because an off-brand list is a list of the ways THIS brand goes wrong, so
copy from a different brand entirely can trip none of it and still be completely wrong. Without
this clause the judge passes a fitness origin story against an AI-operations voice guide, which
is exactly what it did on 2026-07-16.

It is rare and it is obvious. It is NOT for copy that is merely imperfect, and "this passage is
weaker than I'd like" is never a register mismatch. If you find yourself reasoning hard about
whether it applies, it does not.

Return STRICTLY this JSON:
{
  "verdict": "PASS" | "FAIL",
  "violations": [
    {"line": "<the offending line, verbatim from the copy>",
     "rule": "<the voice rule it breaks, verbatim from the rules given>",
     "why": "<one sentence>"}
  ],
  "reasoning": "1-2 sentence summary"
}

`violations` is empty when the verdict is PASS. No prose outside the JSON. No markdown fences."""


def _vr_rules_block(client_data) -> str:
    """The client's voice rules, as the judge sees them."""
    voice = client_data.voice
    parts = []
    if voice.voice_prohibitions:
        parts.append("OFF-BRAND — the client's own list of what they never sound like:")
        parts.extend(f"  - {p}" for p in voice.voice_prohibitions[:40])
    if voice.on_brand_phrases:
        parts.append("\nON-BRAND — phrases from their must-use library, for register reference:")
        parts.extend(f'  - "{p}"' for p in voice.on_brand_phrases[:25])
    if voice.retracted:
        # The judge must know these were TAKEN BACK, or it re-derives the false rule from
        # the guide's own struck-through text. rachel-woods retracted "leverage" after a
        # video sweep proved she says it herself.
        parts.append("\nRETRACTED — the guide explicitly took these back. They are NOT rules. "
                     "Do not flag copy for them:")
        parts.extend(f"  - {r}" for r in voice.retracted[:10])
    return "\n".join(parts)


def check_sem_vr_voice_register(bundle: ParsedBundle, ctx: dict) -> List[Violation]:
    """Does this copy sound like the client, per the client's own documented voice?

    Built 2026-07-16. This rule was listed as implemented in this module's docstring from the
    beginning and did not exist. Meanwhile the repo accumulated ~7,800 lines of carefully
    sourced voice across 22 style guides — tone sliders with verbatim evidence, must-use
    libraries, off-brand lists — which ten skills read as soft context and zero rules checked.

    PC-1 handles the quotable literals. Everything else in an off-brand list is a category
    only a judge can see, and that is most of what those lists actually contain.
    """
    if ctx.get("skip_semantic"):
        return []
    client_data = ctx.get("client_data")
    if not client_data or not client_data.available or not client_data.voice:
        return []
    voice = client_data.voice
    # Nothing to judge against. PC-0 is what complains about an unreadable guide; SEM-VR
    # staying quiet here is correct, not a pass.
    if not voice.voice_prohibitions and not voice.on_brand_phrases:
        return []

    rules_block = _vr_rules_block(client_data)
    pendings = []
    for section in bundle.all_communication_sections:
        body = (section.body or "").strip()
        if len(body) < 120:  # too short to have a register
            continue
        payload = (
            f"CLIENT: {client_data.display_name}\n\n"
            f"THEIR VOICE RULES:\n{rules_block}\n\n"
            f"COPY TO JUDGE (section {section.section_id}):\n{body[:3000]}"
        )
        pendings.append(_pending(
            ctx, rule_id="SEM-VR", rule_name=f"voice register · {client_data.slug} (agent judge)",
            severity=YELLOW, section_id=section.section_id, line_no=section.start_line,
            line_content=body[:120], rubric=SEM_VR_SYSTEM, payload=payload,
        ))
    return _emit(ctx, pendings)


def _find_line_no(section, quoted: str) -> int:
    """Best-effort map the judge's quoted line back to a real line number."""
    if quoted:
        needle = quoted.strip()[:60].lower()
        for line_no, content in section.body_lines:
            if needle and needle in content.lower():
                return line_no
    return section.body_lines[0][0] if section.body_lines else section.start_line


# ────────────────────────────────────────────────────────────────────────────
# RULES registry
# ────────────────────────────────────────────────────────────────────────────

RULES = [
    Rule(id="SEM-T19", name="setup-statement nuance (Claude judge)",  severity=YELLOW, layer=LAYER, check=check_sem_t19_setup_statement_nuance, applies_to=APPLIES_TO),
    Rule(id="SEM-T20", name="mechanism reveal nuance (Claude judge)", severity=YELLOW, layer=LAYER, check=check_sem_t20_mechanism_reveal_nuance, applies_to=APPLIES_TO),
    Rule(id="SEM-TL8", name="title + mechanism obvious to the audience (Claude judge)", severity=YELLOW, layer=LAYER, check=check_sem_tl8_obvious_to_the_audience, applies_to=TL8_APPLIES_TO),
    Rule(id="SEM-AL", name="argument builds context-first and earns its close (Claude judge)", severity=YELLOW, layer=LAYER, check=check_sem_al_argument_logic, applies_to=AL_APPLIES_TO),
    Rule(id="SEM-VR", name="voice register match vs client style-guide (Claude judge)", severity=YELLOW, layer=LAYER, check=check_sem_vr_voice_register, applies_to=VR_APPLIES_TO),
]
