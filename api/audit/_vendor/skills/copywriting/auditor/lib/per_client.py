"""per_client.py — load per-client style guide, info, term mappings.

Looks up clients/<slug>/info.json, style-guide.md, term-mappings.json and surfaces:
  - locked AHAs
  - banned phrases
  - mechanism source-of-truth
  - per-client custom_values (Instagram, podcast, etc.)
  - voice register notes
  - banned competitor mentions

Used by the per_client rules module and as context for semantic checks.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from skills.copywriting.auditor.lib.term_mappings import RetiredTerm, normalize_mappings
from skills.copywriting.auditor.lib.voice import VoiceRules, parse_voice_rules


@dataclass
class ClientData:
    slug: str
    info: dict = field(default_factory=dict)
    term_mappings: dict = field(default_factory=dict)
    style_guide_text: str = ""
    banned_phrases: List[str] = field(default_factory=list)
    locked_aha: Optional[str] = None
    mechanism_source_of_truth: Optional[str] = None
    # True only when a ratified `name_canonical` + an attributed `name_canonical_locked_by` exist.
    # False means the mechanism is still the onboarding DRAFT — usable as the operative name so copy
    # stops re-deriving it, but provisional until a human (Lauren) locks it.
    mechanism_locked: bool = False
    primary_desire: Optional[str] = None
    available: bool = False  # whether the client folder was actually found
    # The style guide's voice sections, sorted into what can be matched vs. judged.
    voice: Optional[VoiceRules] = None
    # Retired terminology, normalized out of the nine live term-mappings shapes.
    retired_terms: List[RetiredTerm] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.info.get("display_name", self.slug)


def find_clients_root(start_path: Optional[str] = None) -> Optional[Path]:
    """Walk up from start_path (or cwd) looking for a clients/ directory.

    Returns the path to clients/ or None if not found.
    """
    if start_path:
        path = Path(start_path).resolve()
    else:
        path = Path.cwd()
    while path != path.parent:
        clients = path / "clients"
        if clients.is_dir():
            return clients
        path = path.parent
    return None


def load_client(slug: str, clients_root: Optional[Path] = None) -> ClientData:
    """Load all per-client data for the given slug.

    Args:
        slug: client folder slug (e.g., "trent-harrison")
        clients_root: optional override for the clients root path

    Returns:
        ClientData populated with available files. .available=False if folder doesn't exist.
    """
    if clients_root is None:
        clients_root = find_clients_root()
    if not clients_root:
        return ClientData(slug=slug, available=False)

    client_dir = clients_root / slug
    if not client_dir.is_dir():
        return ClientData(slug=slug, available=False)

    data = ClientData(slug=slug, available=True)

    # info.json
    info_path = client_dir / "info.json"
    if info_path.is_file():
        try:
            with open(info_path, "r", encoding="utf-8") as f:
                data.info = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # term-mappings.json
    tm_path = client_dir / "term-mappings.json"
    if tm_path.is_file():
        try:
            with open(tm_path, "r", encoding="utf-8") as f:
                data.term_mappings = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # style-guide.md
    sg_path = client_dir / "style-guide.md"
    if sg_path.is_file():
        try:
            with open(sg_path, "r", encoding="utf-8") as f:
                data.style_guide_text = f.read()
        except IOError:
            pass

    # Extract structured fields from style-guide and info
    data.voice = parse_voice_rules(slug, data.style_guide_text)
    data.retired_terms = normalize_mappings(data.term_mappings)
    data.banned_phrases = _extract_banned_phrases(data.style_guide_text, data.info, data.voice)
    data.locked_aha = _extract_locked_aha(data.info, data.style_guide_text)
    data.mechanism_source_of_truth = _extract_mechanism(data.info, data.style_guide_text)
    data.mechanism_locked = _mechanism_is_locked(data.info)
    data.primary_desire = _extract_desire(data.info)

    return data


def _extract_banned_phrases(style_guide: str, info: dict, voice: VoiceRules) -> List[str]:
    """Literal banned phrases: the quoted terms the style guide enumerates, plus info.json.

    Rewritten 2026-07-16. The previous version grepped style-guide.md for `## Banned phrases`
    / `## Banned patterns` / `## Banned words` / `## Do NOT use` — **none of which appear in
    any of the 22 client style guides.** Every guide writes `## Off-brand phrases` and
    `## Don'ts`. So this returned info.json's list, which exists for one real client, and
    PC-1 — a HARD rule — loaded an empty list and passed silently for everyone else.

    Parsing now lives in lib/voice.py, which also keeps the two things that must NOT end up
    here: prose categories ("Passive voice") that only a judge can see, and rules the guide
    has retracted. See that module for why a naive heading fix would have been worse than
    the bug.
    """
    phrases = list(voice.banned_literals) if voice else []

    # info.json may carry an explicit banned_phrases list · it wins nothing, it just adds.
    if isinstance(info.get("banned_phrases"), list):
        phrases.extend(p for p in info["banned_phrases"] if isinstance(p, str))

    seen = set()
    out = []
    for p in phrases:
        if p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out


def _extract_locked_aha(info: dict, style_guide: str) -> Optional[str]:
    """Pull locked AHA Moment from info.json or style-guide.md."""
    raw = info.get("locked_aha") or info.get("aha_moment")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        # Common structures: {"verbatim": "...", ...} or {"text": "..."}
        return raw.get("verbatim") or raw.get("text") or raw.get("name")
    # Look for "AHA" reference in style guide
    if style_guide:
        match = re.search(r"AHA[\s:]*[\"\']([^\"\']+)[\"\']", style_guide, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_mechanism(info: dict, style_guide: str) -> Optional[str]:
    """Pull mechanism source-of-truth name from info.json or style-guide.md.

    Handles both simple string `mechanism: "Volume Eating"` and structured
    `mechanism: {"name_canonical": "Volume Eating", ...}` schemas.
    """
    raw = info.get("mechanism") or info.get("mechanism_name")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        # Ratified (locked) name first; then the onboarding DRAFT, so copy reads the researched
        # name instead of re-deriving it. `mechanism_locked` records which one this was.
        for key in ("name_canonical", "name", "canonical_name", "mechanism_name", "name_canonical_draft"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip() and "not found" not in value.lower():
                return value.strip()
    if style_guide:
        match = re.search(r"##\s+Mechanism[\s:]*\n+([^\n]+)", style_guide, re.IGNORECASE)
        if match:
            return match.group(1).strip().strip("`*").strip()
    return None


def _mechanism_is_locked(info: dict) -> bool:
    """True only when the mechanism is RATIFIED — a canonical name plus an attributed lock.

    A bare string mechanism (`"mechanism": "Volume Eating"`) is treated as settled. The structured
    schema is locked only when a `name_canonical` exists AND `name_canonical_locked_by` names who
    ratified it — a draft with `name_canonical_draft` and a null `locked_by` is NOT locked. (The
    2026-07-13 Holy Health revert: never treat an unattributed/inferred lock as real.)
    """
    raw = info.get("mechanism") or info.get("mechanism_name")
    if isinstance(raw, str):
        return bool(raw.strip())
    if isinstance(raw, dict):
        has_canonical = any(
            isinstance(raw.get(k), str) and raw.get(k, "").strip()
            for k in ("name_canonical", "name", "canonical_name", "mechanism_name")
        )
        locked_by = raw.get("name_canonical_locked_by")
        return bool(has_canonical and isinstance(locked_by, str) and locked_by.strip())
    return False


def _extract_desire(info: dict) -> Optional[str]:
    """The audience's PRIMARY DESIRE — the outcome they actually want.

    Lives in info.json under avatar_snapshot.primary_desire. Until 2026-07-13 no client
    declared it anywhere machine-readable: it sat in the TAB PDF and in people's heads, so
    every writer assumed it, and a title could name a desire the avatar solved years ago
    while passing every mechanical check.
    """
    avatar = info.get("avatar_snapshot") or info.get("avatar") or {}
    if isinstance(avatar, dict):
        for key in ("primary_desire", "core_desire", "desired_outcome"):
            value = avatar.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None
