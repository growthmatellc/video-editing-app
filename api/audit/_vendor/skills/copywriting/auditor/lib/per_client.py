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


@dataclass
class ClientData:
    slug: str
    info: dict = field(default_factory=dict)
    term_mappings: dict = field(default_factory=dict)
    style_guide_text: str = ""
    banned_phrases: List[str] = field(default_factory=list)
    locked_aha: Optional[str] = None
    mechanism_source_of_truth: Optional[str] = None
    available: bool = False  # whether the client folder was actually found

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
    data.banned_phrases = _extract_banned_phrases(data.style_guide_text, data.info)
    data.locked_aha = _extract_locked_aha(data.info, data.style_guide_text)
    data.mechanism_source_of_truth = _extract_mechanism(data.info, data.style_guide_text)

    return data


def _extract_banned_phrases(style_guide: str, info: dict) -> List[str]:
    """Pull banned phrases from style-guide.md banned-phrases section + info.json."""
    phrases = []

    # info.json may have a "banned_phrases" list
    if isinstance(info.get("banned_phrases"), list):
        phrases.extend(info["banned_phrases"])

    # Parse style-guide.md for a "## Banned phrases" or "## Banned patterns" section
    if style_guide:
        # Match section headers and content until next H2 or end
        patterns = [
            r"##\s+Banned\s+phrases\s*\n(.*?)(?=\n##\s|\Z)",
            r"##\s+Banned\s+patterns\s*\n(.*?)(?=\n##\s|\Z)",
            r"##\s+Banned\s+words\s*\n(.*?)(?=\n##\s|\Z)",
            r"##\s+Do\s+NOT\s+use\s*\n(.*?)(?=\n##\s|\Z)",
        ]
        for pat in patterns:
            match = re.search(pat, style_guide, re.IGNORECASE | re.DOTALL)
            if match:
                section = match.group(1)
                # Extract bullet items (- foo) and quoted strings
                for line in section.splitlines():
                    line = line.strip()
                    if line.startswith("-") or line.startswith("*"):
                        item = line.lstrip("-* ").strip()
                        # Strip quotes
                        item = item.strip('"\'').strip("`")
                        if item:
                            phrases.append(item)

    # Dedupe, case-preserve
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
        # Try canonical name fields in order
        for key in ("name_canonical", "name", "canonical_name", "mechanism_name"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if style_guide:
        match = re.search(r"##\s+Mechanism[\s:]*\n+([^\n]+)", style_guide, re.IGNORECASE)
        if match:
            return match.group(1).strip().strip("`*").strip()
    return None
