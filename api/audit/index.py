"""Vercel Python function — POST /api/audit.

Runs the vendored GrowthMate copywriting auditor (deterministic Tom/Alec/Lauren/
formatting/ops rules + Claude-as-judge semantic rules) against a generated copy
bundle, and returns the structured JSON report.

The vendored rule logic is UNCHANGED from growthmate-knowledge (see
scripts/vendor-auditor.ts). This handler only adapts the two on-disk couplings:
  - the parser reads a file path      -> we write the request body to a temp file
  - load_client() walks the FS        -> we build ClientData from the request body
                                         (the app already holds it in Postgres)

Request body: { "markdown": str, "asset_type": str,
                "client"?: { slug, info?, style_guide?, term_mappings? },
                "skip_semantic"?: bool }
Response: the auditor's format_json_report() payload (passed, exit_code,
          summary{hard_violations, yellow_violations, ...}, rule_results[]).
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import tempfile

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
    format_json_report,
)
from skills.copywriting.auditor.lib.per_client import (  # noqa: E402
    ClientData,
    _extract_banned_phrases,
    _extract_locked_aha,
    _extract_mechanism,
)

SUPPORTED_ASSET_TYPES = {
    "email_sequence", "email_launch", "webinar_deck", "webinar_title",
    "launch_copy", "video_ads", "sales_page", "vsl", "organic_social",
    "image_ads", "offer_stack", "objection_qa",
}

# The Ops layer audits the KB's Drive-upload workflow (filenames, output paths),
# not the copy itself — irrelevant to in-app generation, so we never run it here.
SKIP_LAYERS = {"Ops"}


def _client_data_from_payload(payload):
    """Build a ClientData from the app's injected client fields (Postgres),
    mirroring load_client() but without touching the filesystem."""
    if not payload:
        return None
    slug = payload.get("slug") or "unknown"
    info = payload.get("info") or {}
    style_guide = payload.get("style_guide") or ""
    term_mappings = payload.get("term_mappings") or {}
    data = ClientData(slug=slug, available=True)
    data.info = info if isinstance(info, dict) else {}
    data.term_mappings = term_mappings if isinstance(term_mappings, dict) else {}
    data.style_guide_text = style_guide
    data.banned_phrases = _extract_banned_phrases(data.style_guide_text, data.info)
    data.locked_aha = _extract_locked_aha(data.info, data.style_guide_text)
    data.mechanism_source_of_truth = _extract_mechanism(data.info, data.style_guide_text)
    return data


def _run(markdown, asset_type, client_data, skip_semantic):
    """Mirror audit_bundle.run_audit() but from an in-memory string + injected
    client_data (no load_client, no client-folder lookup)."""
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
    }

    applicable = filter_rules_for_asset_type(load_all_rules(), asset_type)
    report = AuditReport(
        file_path="(request)",
        asset_type=asset_type,
        client_slug=context["client_slug"],
    )
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
