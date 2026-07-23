# Copywriting Output Auditor

**Status:** v1 (built 2026-06-24)
**Purpose:** Programmatic pre-ship audit gate for ALL copywriting output. Catches rule violations before they reach Drive.

## Why this exists

We have 47+ craft rules across Tom, Alec, Lauren, and formatting layers. Plus ops rules, per-client rules, and SOP contracts. When the rules list grows, the human + LLM Stage D attention gate fails — patterns flagged in one bundle reproduce in the next.

This auditor is the enforcement layer. The Stage D rules in workflow.md files are prompts. This is code.

**Worked example:** Tom flagged countdown openers on Trent W3 v2. The system fixed the lines Tom marked but reproduced the same pattern in unmarked lines on v5. Tom flagged it again. We rebuilt v6 to fix structure but missed UE-6 GHL variable compliance. Shipped v6.1 hours later. This auditor catches BOTH classes of failure on the next bundle.

## How to use

### CLI

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
│   ├── claude_judge.py      # Claude Haiku semantic checks
│   └── per_client.py        # loads client-specific style-guide + bans + locks
├── rules/
│   ├── __init__.py
│   ├── tom.py               # T-1 to T-20 mechanical checks
│   ├── alec.py              # E-1 to E-10 mechanical checks
│   ├── lauren.py            # UE-1 to UE-6 mechanical checks
│   ├── formatting.py        # F-1 to F-12 mechanical checks
│   ├── ops.py               # scope boundary, output destination, naming, mobile-first
│   ├── webinar_deck.py      # deck-specific (slide structure, T-1 to T-7)
│   ├── launch_copy.py       # bundle-specific (13H toggle, 5-doc structure)
│   ├── video_ads.py         # ad-specific (hook pattern, hook_category)
│   ├── sales_page.py        # sales-page-specific (sections, structure)
│   └── semantic.py          # Claude-judge rules (T-19 nuance, T-20 nuance, etc.)
└── config/
    ├── canonical_variables.yaml   # GHL allowlist + per-asset variants
    ├── banned_patterns.yaml       # legacy var names, banned openers, banned phrases
    ├── asset_type_registry.yaml   # which rule modules apply to which asset_type
    └── severity.yaml              # HARD (blocks ship) vs YELLOW (warns)
```

## Rule severity

- **HARD** rules block shipping. Bundle cannot upload to Drive until fixed.
- **YELLOW** rules warn but allow shipping. Reported in output, operator can override.

Severity is set per rule in `config/severity.yaml`.

## Adding a new rule

1. Decide layer (Tom, Alec, Lauren, formatting, ops, asset-specific, semantic)
2. Add function to the appropriate `rules/<layer>.py` module
3. Register in the module's `RULES` list with id, severity, and human-readable name
4. Update `config/severity.yaml` if not HARD by default
5. Add a test fixture in `tests/` (markdown that should FAIL the rule + markdown that should PASS)
6. Run `python -m pytest skills/copywriting/auditor/tests/` to verify

## Phases shipped

- **Phase 1** (2026-06-24): Framework + mechanical checks for Tom + Alec + Lauren + Formatting on email_sequence + email_launch
- **Phase 2** (2026-06-24): Ops rules + per-client loader + remaining asset types + CLI/auto-gate wiring
- **Phase 3** (2026-06-24): Semantic layer (Claude judge) for nuance rules

## Validation history

- v5 of Trent W3 bundle: FAIL (correctly flagged countdown openers, setup-statement openers, CDI reveal · matches Tom's 2026-06-22 review)
- v6.1 of Trent W3 bundle: PASS (all 50+ rules clear)

## Related

- `skills/copywriting/references/tom-craft-rules.md` — Tom rules source-of-truth
- `skills/copywriting/references/alec-qc-checklists.md` — Alec rules
- `skills/copywriting/references/craft/lauren-universal-email-gates.md` — Lauren rules
- `skills/copywriting/references/craft/email-sms-output-formatting.md` — formatting standard
- `skills/copywriting/references/craft/ghl-variable-conventions.md` — variable allowlist
- `skills/copywriting/asset-modules/*/workflow.md` — per-asset module specs
- `skills/n8n-automation/caretaker/` — sister system for n8n workflow QC (precedent for this auditor)
