"""Vercel Python function — POST /api/audit.

Runs the vendored GrowthMate copywriting auditor against a generated copy bundle
and returns the structured JSON report.

The vendored rule logic is UNCHANGED from growthmate-knowledge (see
scripts/vendor-auditor.ts). This handler adapts three things for in-app use:
  - the parser reads a file path      -> we write the request body to a temp file
  - load_client() walks the FS        -> we build ClientData from the request body
                                         (the app already holds it in Postgres)
  - semantic rules DEFER to an agent   -> they emit `pending_judgments`; this
    handler is the "driving agent" and resolves each one with a Haiku judge,
    injecting any FAIL as a normal violation (so the TS client needs no change).

Request body: { "markdown": str, "asset_type": str,
                "client"?: { slug, info?, style_guide?, term_mappings? },
                "skip_semantic"?: bool }
Response: the auditor's format_json_report() payload.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import tempfile
import urllib.request
import urllib.error
from pathlib import Path

# The vendored tree preserves skills/copywriting/auditor/, so this dir is the
# import root for the module's absolute `from skills.copywriting.auditor...`.
VENDOR_ROOT = os.path.join(os.path.dirname(__file__), "_vendor")
if VENDOR_ROOT not in sys.path:
    sys.path.insert(0, VENDOR_ROOT)

from skills.copywriting.auditor.lib.parser import parse_file  # noqa: E402
from skills.copywriting.auditor.lib.registry import (  # noqa: E402
    load_all_rules,
    filter_rules_for_asset_type,
)
from skills.copywriting.auditor.lib.reporter import (  # noqa: E402
    AuditReport,
    RuleResult,
    Violation,
    format_json_report,
)
from skills.copywriting.auditor.lib.per_client import load_client  # noqa: E402
# Track the auditor's own supported set so the app never drifts from the vendor.
from skills.copywriting.auditor.audit_bundle import SUPPORTED_ASSET_TYPES  # noqa: E402

# The Ops layer audits the KB's Drive-upload workflow (filenames, output paths),
# not the copy itself — irrelevant to in-app generation, so we never run it here.
SKIP_LAYERS = {"Ops"}
# Haiku judge for deferred semantic checks. Override with AUDITOR_JUDGE_MODEL.
JUDGE_MODEL = os.environ.get("AUDITOR_JUDGE_MODEL", "claude-haiku-4-5-20251001")


def _client_data_from_payload(payload):
    """Build a ClientData from the app's injected client fields (Postgres). We
    materialize them into a throwaway clients/<slug>/ dir and call the auditor's
    OWN load_client, so we inherit its exact parsing (voice, banned phrases,
    primary_desire, mechanism) and never drift from the vendored version."""
    if not payload:
        return None
    slug = payload.get("slug") or "unknown"
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    term_mappings = payload.get("term_mappings") if isinstance(payload.get("term_mappings"), dict) else {}
    with tempfile.TemporaryDirectory() as tmp:
        cdir = os.path.join(tmp, "clients", slug)
        os.makedirs(cdir, exist_ok=True)
        with open(os.path.join(cdir, "info.json"), "w", encoding="utf-8") as f:
            json.dump(info, f)
        with open(os.path.join(cdir, "style-guide.md"), "w", encoding="utf-8") as f:
            f.write(payload.get("style_guide") or "")
        with open(os.path.join(cdir, "term-mappings.json"), "w", encoding="utf-8") as f:
            json.dump(term_mappings, f)
        # load_client reads everything into the returned object during this call.
        return load_client(slug, clients_root=Path(tmp) / "clients")


def _judge(prompt):
    """Resolve one deferred judgment with a Haiku judge. Returns 'PASS' | 'FAIL'.
    Fails OPEN (PASS) when the key is missing or the call errors — a judge we
    can't reach must never manufacture a blocking violation."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "PASS"
    body = json.dumps({
        "model": JUDGE_MODEL,
        "max_tokens": 200,
        "system": 'You are a strict QC judge. Read the rubric and copy, then reply with ONLY {"verdict":"PASS"} or {"verdict":"FAIL"}. No prose.',
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"Content-Type": "application/json", "x-api-key": api_key,
                 "anthropic-version": "2023-06-01"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        text = "".join(b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text")
        return "FAIL" if '"fail"' in text.lower() or "fail" in text.lower()[:40] else "PASS"
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError):
        return "PASS"


def _run(markdown, asset_type, client_data, skip_semantic):
    """Run the vendored rules from an in-memory string + injected client_data.
    Mechanical rules produce violations; semantic rules emit pending_judgments,
    which we then resolve with a Haiku judge and fold in as violations."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(markdown)
        tmp_path = f.name
    try:
        bundle = parse_file(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    context = {
        "file_path": tmp_path,
        "asset_type": asset_type,
        "client_slug": client_data.slug if client_data else None,
        "client_data": client_data,
        "skip_semantic": skip_semantic,
        "pending_judgments": [],
    }

    applicable = filter_rules_for_asset_type(load_all_rules(), asset_type)
    report = AuditReport(file_path="(request)", asset_type=asset_type, client_slug=context["client_slug"])
    for rule in applicable:
        if rule.layer in SKIP_LAYERS:
            continue
        if skip_semantic and rule.layer == "Semantic":
            continue
        try:
            violations = rule.check(bundle, context)
        except Exception as e:  # one rule crashing never fails the whole audit
            print(f"[auditor] rule {rule.id} crashed: {e}", file=sys.stderr)
            violations = []
        report.rule_results.append(RuleResult(
            rule_id=rule.id, rule_name=rule.name, severity=rule.severity,
            layer=rule.layer, violations=violations or [],
        ))

    # Resolve deferred semantic judgments (the app is the driving agent) and fold
    # FAILs back in as normal violations. skip_semantic never emits pendings.
    for p in context["pending_judgments"]:
        if _judge(p.prompt) != "FAIL":
            continue
        report.rule_results.append(RuleResult(
            rule_id=p.rule_id, rule_name=p.rule_name, severity=p.severity, layer=p.layer,
            violations=[Violation(
                rule_id=p.rule_id, rule_name=p.rule_name, severity=p.severity,
                section_id=p.section_id, line_no=p.line_no, line_content=p.line_content,
                message=f"Judge: fails {p.rule_id} ({p.rule_name}).",
                fix_hint="Revise so this rule passes.",
            )],
        ))
    report.pending_judgments = []  # all resolved above
    return report


class handler(BaseHTTPRequestHandler):
    def _send(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "invalid JSON body"})

        markdown = payload.get("markdown") or ""
        asset_type = payload.get("asset_type")
        if not markdown.strip():
            return self._send(400, {"error": "markdown is required"})
        if asset_type not in SUPPORTED_ASSET_TYPES:
            return self._send(400, {
                "error": f"unsupported asset_type: {asset_type}",
                "supported": sorted(SUPPORTED_ASSET_TYPES),
            })

        client_data = _client_data_from_payload(payload.get("client"))
        skip_semantic = bool(payload.get("skip_semantic"))
        try:
            report = _run(markdown, asset_type, client_data, skip_semantic)
        except Exception as e:
            return self._send(500, {"error": f"audit failed: {e}"})
        return self._send(200, json.loads(format_json_report(report)))
