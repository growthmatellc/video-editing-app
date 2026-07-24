"""reporter.py — format violations into human-readable + JSON output."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class Violation:
    rule_id: str           # e.g., "T-18", "UE-6", "OPS-1"
    rule_name: str         # e.g., "no countdown openings"
    severity: str          # "HARD" | "YELLOW"
    section_id: str        # e.g., "Email #2", "SMS #B1"
    line_no: int           # 1-indexed line in the source file
    line_content: str      # the offending line content
    message: str           # human-readable explanation
    fix_hint: Optional[str] = None  # how to fix

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PendingJudgment:
    """A semantic check the auditor could not decide mechanically, deferred to an agent judge.

    The auditor does the deterministic part — finding the copy and assembling the rubric — and
    hands back a self-contained `prompt`. The DRIVING agent resolves each one in a FRESH judge
    context (a subagent that never saw the drafting), so the author isn't grading its own work.
    A FAIL becomes a Violation at `severity`. See semantic.py and each skill's QC gate step.
    """
    rule_id: str
    rule_name: str
    layer: str
    severity: str          # the severity to assign IF the judge returns FAIL (HARD | YELLOW)
    section_id: str
    line_no: int
    line_content: str      # the copy under judgment, for display
    prompt: str            # self-contained: rubric + the copy + the PASS/FAIL verdict instruction

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RuleResult:
    rule_id: str
    rule_name: str
    severity: str
    layer: str  # "Tom" | "Alec" | "Lauren" | "Formatting" | "Ops" | "Per-Client" | "Asset-Specific" | "Semantic"
    violations: List[Violation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.violations) == 0

    @property
    def effective_severity(self) -> str:
        """The severity of what was actually FOUND, not the rule's registered label.

        A rule registered HARD may legitimately emit a YELLOW violation (TL-6 blocks on two
        workshop names but only warns when the name merely disagrees with the client's canonical
        record). Reporting that as a hard FAIL overstates it and erodes trust in the gate.
        """
        if not self.violations:
            return self.severity
        return "HARD" if any(v.severity == "HARD" for v in self.violations) else "YELLOW"

    @property
    def hard_failed(self) -> bool:
        return self.effective_severity == "HARD" and not self.passed


@dataclass
class AuditReport:
    file_path: str
    asset_type: str
    client_slug: Optional[str]
    rule_results: List[RuleResult] = field(default_factory=list)
    pending_judgments: List["PendingJudgment"] = field(default_factory=list)

    @property
    def all_violations(self) -> List[Violation]:
        return [v for r in self.rule_results for v in r.violations]

    @property
    def hard_violations(self) -> List[Violation]:
        return [v for v in self.all_violations if v.severity == "HARD"]

    @property
    def yellow_violations(self) -> List[Violation]:
        return [v for v in self.all_violations if v.severity == "YELLOW"]

    @property
    def passed(self) -> bool:
        """Audit passes if no HARD violations. YELLOW violations allowed."""
        return len(self.hard_violations) == 0

    @property
    def exit_code(self) -> int:
        return 0 if self.passed else 1


# ANSI color codes for terminal output
class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"


def format_text_report(report: AuditReport, use_color: bool = True) -> str:
    """Format the audit report as human-readable text.

    Args:
        report: the AuditReport to format
        use_color: whether to include ANSI color codes

    Returns:
        Multi-line string suitable for terminal display.
    """
    def c(text, color):
        return f"{color}{text}{Color.RESET}" if use_color else text

    lines = []
    lines.append(c(f"AUDITING {report.file_path}", Color.BOLD))
    lines.append(f"Asset type: {report.asset_type}")
    if report.client_slug:
        lines.append(f"Client: {report.client_slug}")
    rule_count = len(report.rule_results)
    lines.append(f"Rules evaluated: {rule_count}")
    lines.append("")

    # Group by layer for cleaner output
    by_layer = {}
    for result in report.rule_results:
        by_layer.setdefault(result.layer, []).append(result)

    for layer, results in by_layer.items():
        lines.append(c(f"━━━ {layer} ━━━", Color.CYAN))
        for result in results:
            if result.passed:
                status_icon = c("✅", Color.GREEN)
                status_label = c("pass", Color.GREEN)
                lines.append(f"  {status_icon} {result.rule_id:<6}  {result.rule_name:<40} : {status_label}")
            elif result.effective_severity == "HARD":
                status_icon = c("❌", Color.RED)
                status_label = c(f"FAIL ({len(result.violations)} violation{'s' if len(result.violations) != 1 else ''})", Color.RED)
                lines.append(f"  {status_icon} {result.rule_id:<6}  {result.rule_name:<40} : {status_label}")
                for v in result.violations:
                    lines.append(c(f"     Line {v.line_no} ({v.section_id}): {v.line_content[:100]}", Color.GRAY))
                    lines.append(c(f"       {v.message}", Color.GRAY))
                    if v.fix_hint:
                        lines.append(c(f"       Fix: {v.fix_hint}", Color.GRAY))
            else:  # YELLOW
                status_icon = c("⚠ ", Color.YELLOW)
                status_label = c(f"warn ({len(result.violations)} violation{'s' if len(result.violations) != 1 else ''})", Color.YELLOW)
                lines.append(f"  {status_icon} {result.rule_id:<6}  {result.rule_name:<40} : {status_label}")
                for v in result.violations:
                    lines.append(c(f"     Line {v.line_no} ({v.section_id}): {v.line_content[:100]}", Color.GRAY))
                    lines.append(c(f"       {v.message}", Color.GRAY))
                    if v.fix_hint:
                        lines.append(c(f"       Fix: {v.fix_hint}", Color.GRAY))
        lines.append("")

    # Semantic judgments the agent must resolve (defer mode)
    if report.pending_judgments:
        lines.append(c("━━━ Semantic · agent judge (resolve in a FRESH context) ━━━", Color.CYAN))
        for p in report.pending_judgments:
            icon = c("◻", Color.YELLOW)
            lines.append(f"  {icon} {p.rule_id:<8} {p.rule_name:<44} : needs judgment "
                         f"(FAIL → {p.severity})")
            lines.append(c(f"     ({p.section_id}) {p.line_content[:90]}", Color.GRAY))
        lines.append("")

    # Summary
    lines.append(c("━━━ SUMMARY ━━━", Color.CYAN))
    hard_count = len(report.hard_violations)
    yellow_count = len(report.yellow_violations)
    rules_pass = sum(1 for r in report.rule_results if r.passed)
    rules_hard_fail = sum(1 for r in report.rule_results if r.hard_failed)
    rules_yellow = sum(1 for r in report.rule_results if not r.passed and r.effective_severity == "YELLOW")

    pending_count = len(report.pending_judgments)
    lines.append(f"  Rules passed:       {rules_pass} / {rule_count}")
    lines.append(f"  HARD violations:    {hard_count} ({rules_hard_fail} rule{'s' if rules_hard_fail != 1 else ''})")
    lines.append(f"  YELLOW warnings:    {yellow_count} ({rules_yellow} rule{'s' if rules_yellow != 1 else ''})")
    if pending_count:
        lines.append(f"  Pending judgments:  {pending_count} (agent must judge in a fresh context)")
    lines.append("")

    if not report.passed:
        lines.append(c(f"STATUS: FAIL · ship blocked · fix the {hard_count} HARD violation{'s' if hard_count != 1 else ''} above and re-audit", Color.RED))
    elif pending_count:
        lines.append(c(f"STATUS: MECHANICAL PASS · {pending_count} semantic judgment{'s' if pending_count != 1 else ''} still to resolve · "
                       f"not clear to ship until judged", Color.YELLOW))
    elif yellow_count > 0:
        lines.append(c(f"STATUS: PASS (with {yellow_count} warning{'s' if yellow_count != 1 else ''}) · ship allowed", Color.YELLOW))
    else:
        lines.append(c("STATUS: PASS · ship clear", Color.GREEN))

    return "\n".join(lines)


def format_json_report(report: AuditReport) -> str:
    """Format the audit report as JSON for programmatic consumption."""
    data = {
        "file_path": report.file_path,
        "asset_type": report.asset_type,
        "client_slug": report.client_slug,
        "passed": report.passed,
        "exit_code": report.exit_code,
        "summary": {
            "total_rules": len(report.rule_results),
            "rules_passed": sum(1 for r in report.rule_results if r.passed),
            "hard_violations": len(report.hard_violations),
            "yellow_violations": len(report.yellow_violations),
            "pending_judgments": len(report.pending_judgments),
        },
        "rule_results": [
            {
                "rule_id": r.rule_id,
                "rule_name": r.rule_name,
                "severity": r.severity,
                "layer": r.layer,
                "passed": r.passed,
                "violations": [v.to_dict() for v in r.violations],
            }
            for r in report.rule_results
        ],
        "pending_judgments": [p.to_dict() for p in report.pending_judgments],
    }
    return json.dumps(data, indent=2)
