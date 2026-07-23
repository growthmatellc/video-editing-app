/**
 * TS client for the vendored Python copywriting auditor (POST /api/audit).
 *
 * This is the DETERMINISTIC, code-enforced QC layer (Tom/Alec/Lauren/formatting/
 * ops + Claude-judge semantic rules) from growthmate-knowledge — the real auditor,
 * not the generic LLM re-check in lib/audit.ts. HARD violations drive the
 * auto-rewrite loop in skill-executor; YELLOW violations warn only.
 *
 * The returned report is a superset of lib/audit.ts's AuditResult, so the
 * existing AuditPanel in components/Studio.tsx renders it unchanged.
 */
import type { AuditResult, AuditViolation } from "./audit";
import type { Client } from "./db/schema";

/** Asset types the auditor's rule modules understand (audit_bundle.py). */
export type AuditorAssetType =
  | "email_sequence"
  | "email_launch"
  | "webinar_deck"
  | "webinar_title"
  | "launch_copy"
  | "video_ads"
  | "sales_page"
  | "vsl"
  | "organic_social"
  | "image_ads"
  | "offer_stack"
  | "objection_qa";

/**
 * Asset types with a substantial per-asset deterministic rule module. For these
 * the auditor is authoritative and the LLM audit is redundant. Everything else
 * ("thin" asset types) has only the universal rules in code, so the LLM audit
 * runs alongside as a second blocking gate until per-asset rules are authored.
 */
export const RICH_ASSET_TYPES = new Set<AuditorAssetType>([
  "email_sequence",
  "email_launch",
  "webinar_title",
]);

export interface CopyAuditReport extends AuditResult {
  /** false when the service was unreachable/errored — the pipeline still proceeds. */
  available: boolean;
  hard: number;
  yellow: number;
  assetType: AuditorAssetType;
  /** HARD violations only, pre-formatted for rewrite feedback. */
  hardViolations: AuditViolation[];
}

interface RawViolation {
  rule_id: string;
  rule_name: string;
  severity: "HARD" | "YELLOW";
  section_id: string;
  line_no: number;
  line_content: string;
  message: string;
  fix_hint?: string | null;
}
interface RawReport {
  passed: boolean;
  summary: { total_rules: number; rules_passed: number; hard_violations: number; yellow_violations: number };
  rule_results: { violations: RawViolation[] }[];
}

function auditorUrl(): string {
  if (process.env.COPY_AUDITOR_URL) return process.env.COPY_AUDITOR_URL;
  if (process.env.VERCEL_URL) return `https://${process.env.VERCEL_URL}/api/audit`;
  return `http://localhost:${process.env.PORT ?? 3000}/api/audit`;
}

function mapViolation(v: RawViolation): AuditViolation {
  const where = `${v.section_id}${v.line_no ? ` · L${v.line_no}` : ""}`;
  return {
    rule: `${v.rule_id} ${v.rule_name}`.trim(),
    severity: v.severity === "HARD" ? "high" : "med",
    evidence: v.line_content ? `${where}: ${v.line_content}` : where,
    fix: v.fix_hint || v.message,
  };
}

/** The client fields the auditor's per-client rules use, from Postgres. */
function clientPayload(client: Client | null) {
  if (!client) return undefined;
  return {
    slug: client.slug,
    info: client.infoJson ?? {},
    style_guide: client.styleGuideMd ?? "",
    term_mappings: client.termMappingsJson ?? {},
  };
}

/**
 * Audit a generated bundle. Fails OPEN: on any network/parse error it returns
 * `available: false, passed: true` so a flaky auditor never blocks generation
 * (mirrors auditCopy()'s contract).
 */
export async function auditBundle(opts: {
  markdown: string;
  assetType: AuditorAssetType;
  client: Client | null;
  skipSemantic?: boolean;
}): Promise<CopyAuditReport> {
  const unavailable = (summary: string): CopyAuditReport => ({
    available: false,
    passed: true,
    violations: [],
    hardViolations: [],
    hard: 0,
    yellow: 0,
    assetType: opts.assetType,
    summary,
  });

  try {
    const res = await fetch(auditorUrl(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        markdown: opts.markdown,
        asset_type: opts.assetType,
        client: clientPayload(opts.client),
        skip_semantic: opts.skipSemantic ?? false,
      }),
    });
    if (!res.ok) return unavailable(`Auditor unavailable (HTTP ${res.status}).`);

    const raw = (await res.json()) as RawReport;
    const violations = raw.rule_results.flatMap((r) => r.violations.map(mapViolation));
    const hardViolations = violations.filter((v) => v.severity === "high");
    const hard = raw.summary.hard_violations;
    const yellow = raw.summary.yellow_violations;
    return {
      available: true,
      passed: raw.passed,
      violations,
      hardViolations,
      hard,
      yellow,
      assetType: opts.assetType,
      summary:
        hard === 0
          ? `Auditor clean${yellow ? ` (${yellow} warning${yellow === 1 ? "" : "s"})` : ""}.`
          : `${hard} blocking violation${hard === 1 ? "" : "s"}${yellow ? ` + ${yellow} warning${yellow === 1 ? "" : "s"}` : ""}.`,
    };
  } catch {
    return unavailable("Auditor unavailable (skipped).");
  }
}

/** Build rewrite feedback from HARD violations for the auto-rewrite loop. */
export function hardViolationFeedback(report: CopyAuditReport): string {
  return (
    "Fix these HARD rule violations from the copy auditor. These block shipping — " +
    "correct every one while keeping everything that already complies:\n" +
    report.hardViolations
      .map((v) => `- [${v.rule}] ${v.evidence}\n  → ${v.fix}`)
      .join("\n")
  );
}
