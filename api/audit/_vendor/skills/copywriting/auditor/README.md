# Copywriting Output Auditor

**Status:** v1 (built 2026-06-24)
**Purpose:** Programmatic pre-ship audit gate for ALL copywriting output. Catches rule violations before they reach Drive.

## Why this exists

We have 47+ craft rules across Tom, Alec, Lauren, and formatting layers. Plus ops rules, per-client rules, and SOP contracts. When the rules list grows, the human + LLM Stage D attention gate fails — patterns flagged in one bundle reproduce in the next.

This auditor is the enforcement layer. The Stage D rules in workflow.md files are prompts. This is code.

**Worked example:** Tom flagged countdown openers on Trent W3 v2. The system fixed the lines Tom marked but reproduced the same pattern in unmarked lines on v5. Tom flagged it again. We rebuilt v6 to fix structure but missed UE-6 GHL variable compliance. Shipped v6.1 hours later. This auditor catches BOTH classes of failure on the next bundle.

## How to use

### From a Claude Project — the `audit()` MCP tool (added 2026-07-20)

Copy is written in claude.ai Projects, which reach this repo over the `growthmate-skills` MCP server and **cannot run a shell**. The CLI and auto-gate below therefore never ran on that surface — the sole QC was the model grading itself. The `audit()` MCP tool closes that gap: it runs this exact auditor server-side and returns the violations.

```
audit(asset_text=<full bundle markdown>, asset_type="email_sequence", client_slug="trent-harrison")
```

Returns `{passed, summary, blocking, warnings}`: `blocking` is the HARD list (do not deliver until empty), `warnings` the YELLOW list. This is the gate `skills/copywriting/SKILL.md` Step 6.5 requires before delivery. Semantic judge rules (e.g. TL-9) need `ANTHROPIC_API_KEY` on the server; without it they degrade to a YELLOW "unchecked" warning.

### CLI (local / operator shell)

```bash
python skills/copywriting/auditor/audit_bundle.py \
  clients/trent-harrison/outputs/email-sequences/drive-pushed/2026-06-24_trent-w3-bundle-v6.1-tom-clean.md \
  --asset-type email_sequence \
  --client trent-harrison
```

Output: pass/fail + line-numbered violations grouped by rule + summary.

Exit code 0 = pass, non-zero = fail (auto-gate compatible).

### Auto-gate (pre-Drive-upload)

```bash
scripts/ship-with-audit.sh <path-to-md> <asset-type> <client-slug>
```

Runs auditor, blocks the Drive upload if any HARD rule fails. Surfaces violations.

## Architecture

```
skills/copywriting/auditor/
├── audit_bundle.py          # main CLI entry point
├── README.md                # this file
├── lib/
│   ├── __init__.py
│   ├── parser.py            # markdown → structured emails/SMS/sections
│   ├── reporter.py          # formatted output (text + JSON)
│   ├── registry.py          # rule registry · loads all rule modules
│   ├── voice.py             # parses style-guide voice sections · literal / prose / retracted
│   ├── term_mappings.py     # normalizes the 9 live term-mappings.json key shapes
│   └── per_client.py        # loads client-specific style-guide + bans + locks
├── rules/
│   ├── __init__.py
│   ├── tom.py               # T-1 to T-20 mechanical checks
│   ├── alec.py              # E-1 to E-10 mechanical checks
│   ├── lauren.py            # UE-1 to UE-6 mechanical checks
│   ├── formatting.py        # F-1 to F-12 mechanical checks
│   ├── ops.py               # naming convention, sequence headers
│   ├── per_client.py        # PC-0..2  · voice parse guard, off-brand phrases, retired terms
│   ├── launch_copy.py       # LC-0..7  · bundle (13H toggles, 5-asset structure)
│   ├── funnel_pages.py      # FP-0..13 · 4-page deliverable, locked page blocks, sales language
│   ├── sales_page.py        # SP-0..8  · 9 locked sections (11 for VSL), one-CTA, proof stack
│   ├── video_ads.py         # VA-0..7  · hook proof-number, distinct hooks, length, hyphens, bullets
│   ├── image_ads.py         # IA-0..6  · headline/subhead length, proof-number, em dashes, presenter named, live-obvious (+ shared TL/TL9 HARD)
│   ├── webinar_deck.py      # WD-0..9  · slide format, word caps, case studies, founder images
│   ├── organic_social.py    # OS-1..4  · soft-CTA-only, one ask
│   └── semantic.py          # Claude-judge rules (T-19/T-20 nuance, TL8, AL, VR voice register)
└── tests/
    ├── test_launch_copy_rules.py   # LC rules, each tested firing AND clearing
    ├── test_skill_rules.py         # FP / SP / VA / OS / WD, same discipline
    ├── test_voice_rules.py         # the voice parser, run against all 22 LIVE style guides
    └── test_term_mappings.py       # the 9 term-mappings shapes, run against the live files
```

**Coverage: every copywriting asset type.** email (`email_sequence`, `email_launch`), `launch_copy`, `funnel_pages`, `sales_page`, `vsl`, `video_ads`, `image_ads`, `webinar_deck`, `organic_social`.

Configuration is in the rule modules themselves (e.g. `lauren.CANONICAL_CUSTOM_VALUES`, `launch_copy.LOCKED_ASSET_ORDER`), not in a config directory. Shared checks (em dashes, British spellings, asterisk bullets, markdown section splitting) live once in `lib/sections.py` so a fix lands everywhere at once.

## The `-0` parse guard, and why every module has one

Each asset module's first rule is `XX-0 · document parses`, a HARD rule that fires when the parser recognises zero units (pages, slides, ads, sections) in the file.

This is not defensive padding. On 2026-07-13 the deck parser knew only the scripted slide format. Trent's deck used the compressed format, parsed to **zero slides**, every one of the nine deck rules passed on an empty list, and the auditor printed **"PASS · ship clear"** for a deck it had never read.

A gate that blesses what it cannot parse is worse than no gate: it manufactures false confidence. The `-0` rules make an unreadable file a hard failure, always.

**It happened again, in the other direction — and `PC-0` is the answer.** *(2026-07-16.)* The deck case was a rule that couldn't parse the **asset**. `PC-1 · per-client banned phrases`, also HARD, couldn't parse the **client**: it grepped `style-guide.md` for `## Banned phrases`, a heading that appears in **zero** of the 22 live guides — every one writes `## Off-brand phrases`. So it loaded an empty ban list and passed cleanly for every client, for six weeks. Same failure, same silence, and this time nothing in the file was even malformed.

`PC-0 · voice rules parse` closes it: a `style-guide.md` that exists but yields no readable voice section is now a HARD failure instead of a green check. The lesson generalises past parsing an asset — **any rule whose input is loaded rather than passed in needs a guard proving the load worked.** An empty list is not a clean bill of health.

The tests changed too: `test_voice_rules.py` and `test_term_mappings.py` run against `clients/*/` rather than fixtures, because a fixture carries whatever heading its author imagined — which is precisely how this stayed invisible.

## What is deliberately NOT encoded

Rules that need human or LLM judgment are not in the auditor, and that is on purpose:

- video-ad hook criteria 1 and 2 ("specific WHO", "hot take / value statement / shocking truth")
- "bullets anchored in lived experience", "headline self-explanatory on first read"
- "reader-first framing", "genuine vs manufactured urgency"
- "pattern-match the approved anchors"

A regex could check for the word "women" and call it a specific WHO. That green tick would be a lie, and a lie from a QC gate is more dangerous than a gap. These stay in the workflow checklists and the semantic layer.

**So a VA-1 pass does not mean the hook passed Lauren's hook rule** — only that the proof number is there. The other two criteria remain a human gate at Stage E.

## Rule severity

- **HARD** rules block shipping. Bundle cannot upload to Drive until fixed.
- **YELLOW** rules warn but allow shipping. Reported in output, operator can override.

Severity is set per rule in the `RULES` list of each module.

Use YELLOW when the rule is real but a *static file audit can't fully observe it* — e.g. LC-1/LC-2, where the scope confirmation is specified as chat output. The audit then reports that the check is unverifiable and names what the doc must carry to make it enforceable. Don't invent a HARD gate the written rules don't support.

## Adding a new rule

1. Decide layer (Tom, Alec, Lauren, formatting, ops, asset-specific, semantic)
2. Add a check function to the appropriate `rules/<layer>.py` module
3. Register it in the module's `RULES` list with id, severity, and human-readable name
4. Cite the source of the rule in the module docstring — a rule with no written source is an invented rule
5. Add tests in `tests/` proving it BOTH fires on a violation and clears on clean copy
6. Run the suite:

```bash
python3 -m unittest discover -s skills/copywriting/auditor/tests -t . -v
```

(stdlib `unittest` — no pytest dependency)

## Phases shipped

- **Phase 1** (2026-06-24): Framework + mechanical checks for Tom + Alec + Lauren + Formatting on email_sequence + email_launch
- **Phase 2** (2026-06-24): Ops rules + per-client loader + CLI/auto-gate wiring
- **Phase 3** (2026-06-24): Semantic layer (Claude judge) for nuance rules
- **Phase 2c** (2026-07-13): `launch_copy` module filled — LC-1 to LC-7 + first test suite

## Validation history

- v5 of Trent W3 bundle: FAIL (correctly flagged countdown openers, setup-statement openers, CDI reveal · matches Tom's 2026-06-22 review)
- v6.1 of Trent W3 bundle: PASS (all 50+ rules clear)
- Trent Metabolic Fuel launch bundle v1 (2026-07-13, first `launch_copy` run): FAIL · 3 HARD. Caught a 3-of-4 funnel deliverable (no Replay page) and "strategy session" call-booking language on both the registration and webinar-confirmation pages. Both are real defects in a Stage C draft that had already been written.

## Related

- `skills/copywriting/references/tom-craft-rules.md` — Tom rules source-of-truth
- `skills/copywriting/references/alec-qc-checklists.md` — Alec rules
- `skills/copywriting/references/craft/argument-logic-rules.md` — AL-1 to AL-5 source-of-truth (SEM-AL judge)
- `skills/email-sms-building/email-sequence/workflow.md` § Universal email copy QC gates — Lauren's UE-1 to UE-6 source-of-truth
- `references/craft/email-sms-output-formatting.md` — formatting standard
- `references/craft/ghl-variable-conventions.md` — variable allowlist
- `references/craft/funnel-and-email-rules-lauren.md` — Lauren's funnel + email ruleset
- `skills/copywriting/asset-modules/launch-copy/spec-v2.md` — launch_copy source-of-truth (LC rules) + the Stage D gate
- `skills/copywriting/asset-modules/launch-copy/incidents/2026-06-03_scope-creep-emails-generated-webinar.md` — why the LC rules exist
- `skills/n8n-automation/caretaker/` — sister system for n8n workflow QC (precedent for this auditor)
