"""registry.py — discover + load rule modules.

Each rule module under rules/ exports:
  RULES: list of Rule dataclass instances
  LAYER: human-readable layer name (e.g., "Tom", "Lauren")
  APPLIES_TO: set of asset_type strings this layer applies to, or {"*"} for all

A Rule has:
  id: short identifier (e.g., "T-18")
  name: human-readable name (e.g., "no countdown openings")
  severity: "HARD" | "YELLOW"
  check: callable(ParsedBundle, dict) -> list of Violation

The check function receives the parsed bundle + a context dict containing
client_slug, client_data (loaded from clients/[slug]/), asset_type, etc.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Set, Dict, Any


@dataclass
class Rule:
    id: str
    name: str
    severity: str
    layer: str
    check: Callable
    applies_to: Set[str] = field(default_factory=lambda: {"*"})


# Module paths to discover
RULE_MODULES = [
    "skills.copywriting.auditor.rules.universal",
    "skills.copywriting.auditor.rules.tom",
    "skills.copywriting.auditor.rules.alec",
    "skills.copywriting.auditor.rules.lauren",
    "skills.copywriting.auditor.rules.formatting",
    "skills.copywriting.auditor.rules.ops",
    "skills.copywriting.auditor.rules.webinar_deck",
    "skills.copywriting.auditor.rules.webinar_title",
    "skills.copywriting.auditor.rules.launch_copy",
    "skills.copywriting.auditor.rules.video_ads",
    "skills.copywriting.auditor.rules.sales_page",
    "skills.copywriting.auditor.rules.per_client",
    "skills.copywriting.auditor.rules.semantic",
]


def load_all_rules() -> List[Rule]:
    """Discover and load all rules from the rule modules.

    Returns flat list of all Rule instances across all modules.
    """
    rules = []
    for module_path in RULE_MODULES:
        try:
            module = importlib.import_module(module_path)
            module_rules = getattr(module, "RULES", [])
            layer = getattr(module, "LAYER", module_path.split(".")[-1])
            for rule in module_rules:
                # Ensure layer is set on the rule if not already
                if not rule.layer:
                    rule.layer = layer
                rules.append(rule)
        except ImportError as e:
            # Module not yet implemented or import failure · skip but warn in dev
            # In production we'd log this, but for now just continue
            import sys
            print(f"[auditor:registry] warning · could not load {module_path}: {e}", file=sys.stderr)
            continue
        except AttributeError:
            # Module loaded but has no RULES attribute · skip
            continue
    return rules


def filter_rules_for_asset_type(rules: List[Rule], asset_type: str) -> List[Rule]:
    """Filter rules to those that apply to the given asset_type."""
    return [r for r in rules if "*" in r.applies_to or asset_type in r.applies_to]


# Severity constants
HARD = "HARD"
YELLOW = "YELLOW"
