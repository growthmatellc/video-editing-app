#!/usr/bin/env python3
"""audit_bundle.py — main CLI for the Growth Mate copywriting output auditor.

Audits a copywriting output bundle against ALL applicable rule layers:
  Tom T-1 to T-20, Alec E-1 to E-10, Lauren UE-1 to UE-6, Formatting F-1 to F-12,
  Ops rules, Per-asset structural rules, Per-client rules (locked AHAs, banned phrases,
  mechanism source-of-truth), and Semantic rules (Claude-as-judge).

Usage:
    python audit_bundle.py <path-to-md> --asset-type <type> [--client <slug>] [--json] [--no-semantic]

Examples:
    python audit_bundle.py clients/trent-harrison/outputs/.../bundle-v6.md --asset-type email_sequence --client trent-harrison

Exit codes:
    0 = PASS (no HARD violations · YELLOW warnings allowed)
    1 = FAIL (one or more HARD violations · ship blocked)
    2 = error (file not found, parse error, etc.)

Asset types supported:
    email_sequence, email_launch, webinar_deck, launch_copy, video_ads, sales_page, vsl, organic_social
"""

import argparse
import os
import sys
from pathlib import Path

# Make sibling modules importable when called directly from anywhere
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent  # skills/copywriting/auditor → repo root
sys.path.insert(0, str(REPO_ROOT))

from skills.copywriting.auditor.lib.parser import parse_file
from skills.copywriting.auditor.lib.registry import load_all_rules, filter_rules_for_asset_type
from skills.copywriting.auditor.lib.reporter import (
    AuditReport,
    RuleResult,
    format_text_report,
    format_json_report,
)
from skills.copywriting.auditor.lib.per_client import load_client


SUPPORTED_ASSET_TYPES = {
    "email_sequence",
    "email_launch",
    "webinar_deck",
    "launch_copy",
    "funnel_pages",
    "video_ads",
    "image_ads",
    "sales_page",
    "vsl",
    "organic_social",
}


def run_audit(
    file_path: str,
    asset_type: str,
    client_slug: str = None,
    skip_semantic: bool = False,
    semantic_mode: str = "defer",
) -> AuditReport:
    """Run the full audit.

    Args:
        file_path: path to the markdown bundle file
        asset_type: one of SUPPORTED_ASSET_TYPES
        client_slug: optional client slug for per-client rules
        skip_semantic: if True, skip Claude-as-judge semantic rules (faster + free)

    Returns:
        AuditReport with all rule results.
    """
    # Parse the file
    try:
        bundle = parse_file(file_path)
    except FileNotFoundError:
        print(f"[auditor] ERROR · file not found: {file_path}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"[auditor] ERROR · parse failed: {e}", file=sys.stderr)
        sys.exit(2)

    # Load per-client data
    client_data = None
    if client_slug:
        client_data = load_client(client_slug)

    # Build context dict passed to every check function. `pending_judgments` is the sink the
    # semantic rules append to in defer mode (the default) instead of calling out to an LLM —
    # the driving agent resolves them in a fresh judge context. See semantic.py.
    context = {
        "file_path": file_path,
        "asset_type": asset_type,
        "client_slug": client_slug,
        "client_data": client_data,
        "skip_semantic": skip_semantic,
        "semantic_mode": semantic_mode,
        "pending_judgments": [],
    }

    # Load and filter rules
    all_rules = load_all_rules()
    applicable_rules = filter_rules_for_asset_type(all_rules, asset_type)

    # Run each rule
    report = AuditReport(
        file_path=file_path,
        asset_type=asset_type,
        client_slug=client_slug,
    )
    for rule in applicable_rules:
        # Skip semantic rules if requested (e.g., to save Claude API calls during dev)
        if skip_semantic and rule.layer == "Semantic":
            continue
        try:
            violations = rule.check(bundle, context)
        except Exception as e:
            # Don't let one rule crash the whole audit · log and continue
            print(f"[auditor] rule {rule.id} ({rule.name}) crashed: {e}", file=sys.stderr)
            violations = []
        result = RuleResult(
            rule_id=rule.id,
            rule_name=rule.name,
            severity=rule.severity,
            layer=rule.layer,
            violations=violations or [],
        )
        report.rule_results.append(result)

    report.pending_judgments = context.get("pending_judgments", [])
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Audit a Growth Mate copywriting output bundle against all applicable rules.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("file_path", help="Path to the markdown bundle file")
    parser.add_argument(
        "--asset-type",
        required=True,
        choices=sorted(SUPPORTED_ASSET_TYPES),
        help="Asset type · determines which rules apply",
    )
    parser.add_argument(
        "--client",
        help="Client slug (e.g., trent-harrison) for per-client rule application",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of formatted text (for programmatic consumption)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color codes in text output",
    )
    parser.add_argument(
        "--no-semantic",
        action="store_true",
        help="Skip semantic (agent-judge) rules entirely · no judgments emitted",
    )
    parser.add_argument(
        "--semantic-mode",
        choices=["defer", "http"],
        default="defer",
        help="defer (default): emit semantic checks as pending_judgments for an agent to judge · "
             "http: headless fallback that POSTs to Haiku (needs ANTHROPIC_API_KEY)",
    )
    args = parser.parse_args()

    report = run_audit(
        file_path=args.file_path,
        asset_type=args.asset_type,
        client_slug=args.client,
        skip_semantic=args.no_semantic,
        semantic_mode=args.semantic_mode,
    )

    if args.json:
        print(format_json_report(report))
    else:
        print(format_text_report(report, use_color=not args.no_color))

    sys.exit(report.exit_code)


if __name__ == "__main__":
    main()
