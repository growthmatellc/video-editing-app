/**
 * Post-delivery rules audit.
 *
 * The review gate (lib/gate.ts) judges voice + persuasive quality generically.
 * This is different: it checks the delivered copy against the CONCRETE, checkable
 * rules of the stage's skill — subject-line format, banned patterns (em dashes),
 * required sections/sequence, length caps, cadence, merge-var conventions, etc.
 *
 * It is a report, not a blocker: violations surface in the UI so the operator can
 * reject-and-re-run. If the audit call fails it returns "clean" so it never blocks.
 */
import { generateJson, REVIEW_MODEL } from "./llm";

export interface AuditViolation {
  rule: string; // the specific rule that was broken
  severity: "high" | "med" | "low";
  evidence: string; // the exact offending text from the copy
  fix: string; // how to correct it
}

export interface AuditResult {
  passed: boolean;
  violations: AuditViolation[];
  summary: string;
}

const AUDITOR_SYSTEM = `You are a strict QC auditor for direct-response copy. You are given (1) the standards/rules for a deliverable and (2) the delivered copy.

Your job: extract the CONCRETE, CHECKABLE rules from the standards, then verify the copy against each one. Checkable rules are things like: required sections or sequence, subject-line format/prefix tags, banned characters or phrases (e.g. "no em dashes"), length caps, required cadence/timing, merge-variable conventions, mandatory elements (CTA, deadline, preview text), formatting rules.

Rules:
- Only include entries that are ACTUAL violations. NEVER list a rule the copy satisfies. If the copy complies, do not mention it at all — no "compliant / no change" entries.
- Quote the exact offending text in "evidence".
- Do NOT flag stylistic taste, or things the standards don't actually require.
- If the standards are silent on something, it is not a violation.
- Respect explicit exceptions in the standards (e.g. a rule that says "applies to SMS 1-3" does not apply to SMS 4). Do not report the exception as a violation.
- "high" = breaks a hard/explicit rule (a stated MUST/NEVER, wrong structure, banned pattern). "med" = a soft rule or partial miss. "low" = minor polish.
- "passed" is true only when there are no high-severity violations.
- If the copy fully complies, return "violations": [] and passed: true.

Return ONLY this JSON, no prose, no fences:
{
  "passed": boolean,
  "summary": string,          // one line: overall verdict
  "violations": [
    { "rule": string, "severity": "high" | "med" | "low", "evidence": string, "fix": string }
  ]
}`;

export async function auditCopy(opts: {
  stageLabel: string;
  rules: string;
  output: string;
}): Promise<AuditResult> {
  if (!opts.rules.trim() || !opts.output.trim()) {
    return { passed: true, violations: [], summary: "No rules to audit against." };
  }
  try {
    const { data } = await generateJson<AuditResult>({
      system: [
        { text: AUDITOR_SYSTEM },
        {
          text: `# Standards and rules for the deliverable "${opts.stageLabel}"\n${opts.rules}`,
          cache: true,
        },
      ],
      user: `Audit this delivered copy against the rules above. Return the JSON verdict.\n\n--- DELIVERED COPY ---\n${opts.output}\n--- END ---`,
      maxTokens: 3000,
      model: REVIEW_MODEL,
    });
    return {
      passed: !!data.passed,
      summary: typeof data.summary === "string" ? data.summary : "",
      violations: Array.isArray(data.violations)
        ? data.violations.filter((v) => v && v.rule && v.severity)
        : [],
    };
  } catch {
    return { passed: true, violations: [], summary: "Audit unavailable (skipped)." };
  }
}
