"""term_mappings.py — normalize clients/<slug>/term-mappings.json into one shape.

`mappings[]` is where a client's retired terminology lives: Jane's "MAP system" → "metabolic
alignment system", Trent's "Big Plates Skinny Waists" → "Metabolic Fuel". PC-2 is supposed to
catch copy that still uses the retired name. Until 2026-07-16 it didn't read this file at all —
it carried a hardcoded `DEPRECATED_MECHANISMS = {"trent-harrison": [...]}` and returned clean
for the other 21 clients.

Reading the file is harder than it should be. Every guide declares `"schema_version": 1` and
then uses its own key names — eight variants across twelve populated files:

    retire / use_instead ......... bti-8ss
    retired_term / current_term .. erinne, jake, jane, janela, kute
    preferred_term / avoid_terms[] hea
    from / to .................... legion
    old_term / new_term .......... mindstrong
    placeholder / canonical_value  mpwr
    term / use / retire[] ........ ownit
    term / do_not_resurrect[] .... trent
    term / canonical ............. vfactor  (no retirement — a spelling lock)

So `schema_version: 1` is decoration. This module reads all of them and emits one
`RetiredTerm` shape; the alternative is PC-2 staying blind on 21 clients, which is where
it has been since it was written.

Severity is data-driven, not assumed: a retirement the client has actually confirmed blocks
(HARD); one still marked pending a Lauren call warns (YELLOW). Firing HARD on a rule nobody
has agreed to yet is how a gate loses its credibility.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

# (retired_key, replacement_key, blocking) — scalar retired term.
#
# `blocking` is not a style choice, it is what the client's own key NAME claims:
#   `retired_term` / `old_term` / `retire` say a term is DEAD → HARD.
# `from`/`to` is deliberately absent. legion is the only client using it and both of its
# entries are research notes, not retirements — `from: "founder (TBD)"` and
# `from: "Legion Athletics (separate brand)"`. Normalizing those would HARD-fail the word
# "founder" and the brand's own name in every Legion asset. A note is not a rule.
_SCALAR_PAIRS = [
    ("retired_term", "current_term", True),
    ("old_term", "new_term", True),
    ("retire", "use_instead", True),
]

# Keys whose value is a LIST of retired terms, paired with a scalar replacement key.
#
# `avoid_terms` (hea) is a PREFERENCE vocabulary, not a retirement — its own key says
# "avoid", and its entries are things like "results" → "clinical outcomes" and "learn" →
# "Install [the Method]". Blocking a draft for the word "results" would make PC-2 the most
# hated rule in the auditor within a day. Preference → YELLOW; the writer decides.
_LIST_PAIRS = [
    ("avoid_terms", "preferred_term", False),  # hea · preference vocabulary
    ("do_not_resurrect", "term", True),        # trent · explicit "never again"
    ("retire", "use", True),                   # ownit · list here, scalar in bti
]

# Markers meaning "this retirement is not agreed yet" → YELLOW rather than HARD.
_PENDING = re.compile(
    r"pending|PENDING|ORANGE|proposed|candidate|not\s+yet\s+confirmed|unconfirmed",
    re.IGNORECASE,
)


@dataclass
class RetiredTerm:
    retired: str
    replacement: Optional[str]
    reason: str
    confirmed: bool   # False → the retirement awaits a human call
    blocking: bool    # False → a preference, not a retirement

    @property
    def hard(self) -> bool:
        """HARD only when the client retired the term AND agreed to it.

        Everything else warns. A gate that blocks on a rule nobody ratified gets
        worked around, and then it is not a gate.
        """
        return self.blocking and self.confirmed


def _pending_entry(entry: dict) -> bool:
    if entry.get("pending_lauren_confirm") is True:
        return True
    if entry.get("lauren_gate"):
        return True
    for key in ("status", "confidence"):
        val = entry.get(key)
        if isinstance(val, str) and _PENDING.search(val):
            return True
    # An entry parked in an explicit gate field is not settled.
    for key in ("question_for_lauren", "candidate_alternates"):
        if entry.get(key):
            return True
    return False


def _clean(term: str) -> str:
    """Strip a trailing gloss so the literal can actually match real copy.

    The corpus writes `Maintenance Inversion (v4.1)` and
    `Ransomed 5M Method (as canonical · keep as legacy brand only)`. The parenthetical is a
    note to a human; matching it verbatim means matching nothing.
    """
    term = re.sub(r"\s*\([^)]*\)\s*$", "", term or "").strip()
    return term.strip(" .,;:·—-").strip()


def _reason_of(entry: dict) -> str:
    for key in ("reason", "context", "notes"):
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def normalize_mappings(term_mappings: dict) -> List[RetiredTerm]:
    """Read any of the live `mappings[]` shapes into one list of retired terms."""
    out: List[RetiredTerm] = []
    entries = (term_mappings or {}).get("mappings") or []
    if not isinstance(entries, list):
        return out

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        pending = _pending_entry(entry)
        reason = _reason_of(entry)

        # Shape 9: `do_not_resurrect: true` as a BOOLEAN — the entry's own `term` is the
        # retired one, and `maps_to` is its replacement. trent's "Volume Eating" uses this
        # (retired 2026-07-13, "171 occurrences" per its own context note). The list-shaped
        # `do_not_resurrect: [...]` below would skip it silently, which is how the single
        # most-used retired term in the repo stayed invisible.
        if entry.get("do_not_resurrect") is True:
            term = _clean(entry.get("term") or "")
            repl = _clean(entry.get("maps_to") or "") or None
            if term:
                out.append(RetiredTerm(term, repl, reason, not pending, True))

        for retired_key, repl_key, blocking in _LIST_PAIRS:
            raw = entry.get(retired_key)
            if not isinstance(raw, list):
                continue
            replacement = entry.get(repl_key)
            repl = _clean(replacement) if isinstance(replacement, str) else None
            for item in raw:
                if not isinstance(item, str):
                    continue
                term = _clean(item)
                if term:
                    out.append(RetiredTerm(term, repl, reason, not pending, blocking))

        for retired_key, repl_key, blocking in _SCALAR_PAIRS:
            raw = entry.get(retired_key)
            if not isinstance(raw, str):
                continue
            replacement = entry.get(repl_key)
            term = _clean(raw)
            repl = _clean(replacement) if isinstance(replacement, str) else None
            # mpwr and vfactor write `X → X` to lock a spelling. Nothing to flag.
            if not term or (repl and term.lower() == repl.lower()):
                continue
            out.append(RetiredTerm(term, repl, reason, not pending, blocking))

    # Dedupe on the retired term; prefer the entry that would fire hardest.
    best = {}
    for rt in out:
        key = rt.retired.lower()
        if key not in best or (rt.hard and not best[key].hard):
            best[key] = rt
    return list(best.values())
