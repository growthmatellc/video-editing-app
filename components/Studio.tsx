"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { theme } from "@/theme/tokens";
import {
  WEBINAR_PIPELINE,
  PHASE_LABELS,
  PHASE_ORDER,
  STAGE_BY_KEY,
  VOICE_GATED_STAGES,
  type StageDef,
} from "@/lib/pipeline";
import { statusColor, statusLabel, type StageStatus } from "@/lib/stage-ui";
import { MarkdownView } from "@/components/MarkdownView";
import { AppHeader } from "@/components/AppHeader";
import type { AuditResult } from "@/lib/audit";

export interface GateScore {
  passed: boolean;
  score: number;
  violations: { severity: "high" | "med" | "low"; note: string }[];
}

export interface StudioStage {
  stageKey: string;
  stageOrder: number;
  status: StageStatus;
  outputMd: string | null;
  outputMeta: Record<string, unknown> | null;
  scoreJson: GateScore | null;
  auditJson: AuditResult | null;
  gatePassed: boolean;
  gateAttempts: number;
}

interface Revision {
  id: string;
  outputMd: string;
  feedback: string | null;
  createdAt: string;
}

interface Props {
  projectId: string;
  clientName: string;
  status: string;
  intakeText: string;
  initialStages: StudioStage[];
}

const TOTAL = WEBINAR_PIPELINE.length;

export function Studio({
  projectId,
  clientName,
  status,
  intakeText,
  initialStages,
}: Props) {
  const [stages, setStages] = useState<StudioStage[]>(initialStages);
  const [selectedKey, setSelectedKey] = useState<string>(
    initialStages.find((s) => s.status === "draft")?.stageKey ?? "webinar-blueprint",
  );
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState<null | "run" | "approve" | "reject">(null);
  const [error, setError] = useState<string | null>(null);
  const [showRevisions, setShowRevisions] = useState(false);
  const [revisions, setRevisions] = useState<Revision[]>([]);

  const stageMap = useMemo(() => {
    const m = new Map<string, StudioStage>();
    for (const s of stages) m.set(s.stageKey, s);
    return m;
  }, [stages]);

  const def: StageDef = STAGE_BY_KEY[selectedKey];
  const stage = stageMap.get(selectedKey);
  const approvedCount = stages.filter((s) => s.status === "approved").length;
  const percent = Math.round((approvedCount / TOTAL) * 100);

  function patchStage(key: string, patch: Partial<StudioStage>) {
    setStages((prev) =>
      prev.map((s) => (s.stageKey === key ? { ...s, ...patch } : s)),
    );
  }

  async function runStage(kind: "run" | "reject", feedbackOverride?: string) {
    const fb = (feedbackOverride ?? feedback).trim();
    if (kind === "reject" && !fb) {
      setError("Add feedback before rejecting.");
      return;
    }
    setBusy(kind);
    setError(null);
    patchStage(selectedKey, { status: "running" });
    // Backstop so the UI never hangs forever if the serverless function is
    // killed at its time limit (60s on Vercel Hobby) without a clean response.
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 90_000);
    try {
      const res = await fetch(
        `/api/projects/${projectId}/stages/${selectedKey}/${kind === "reject" ? "reject" : "run"}`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ feedback: fb || undefined }),
          signal: controller.signal,
        },
      );
      if (res.status === 504 || res.status === 502) {
        throw new Error("TIMEOUT");
      }
      const data = await res.json();
      if (!res.ok || data.ok === false) {
        throw new Error(data.error ?? "Generation failed");
      }
      patchStage(selectedKey, {
        status: data.status ?? "draft",
        outputMd: data.outputMd ?? null,
        scoreJson: data.score ?? null,
        auditJson: data.audit ?? null,
        gatePassed: data.score?.passed ?? false,
      });
      setFeedback("");
      setShowRevisions(false);
    } catch (err) {
      const name = err instanceof Error ? err.name : "";
      const msg = err instanceof Error ? err.message : String(err);
      const timedOut = name === "AbortError" || msg === "TIMEOUT";
      setError(
        timedOut
          ? "This stage ran past the 60-second serverless time limit (Vercel Hobby plan) and was cut off. The heavier stages (email/SMS/call sequences, script) need more time — upgrade the project to Vercel Pro (300s limit) to run them. Lighter stages usually finish in time; a second run is often faster once cached."
          : msg,
      );
      patchStage(selectedKey, { status: stage?.outputMd ? "draft" : "not_started" });
    } finally {
      clearTimeout(timer);
      setBusy(null);
    }
  }

  async function approve() {
    setBusy("approve");
    setError(null);
    try {
      const res = await fetch(
        `/api/projects/${projectId}/stages/${selectedKey}/approve`,
        { method: "POST" },
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Approve failed");
      patchStage(selectedKey, { status: "approved" });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  // Re-run this stage with the audit's violations folded in as fix instructions.
  function fixFromAudit(audit: AuditResult) {
    const fixes = audit.violations
      .map((v) => `- (${v.severity}) ${v.rule}: ${v.fix}${v.evidence ? ` [offending: "${v.evidence}"]` : ""}`)
      .join("\n");
    const text = `Fix these rule violations from the QC audit. Keep everything that already complies:\n${fixes}`;
    setFeedback(text);
    runStage("run", text);
  }

  async function loadRevisions() {
    const next = !showRevisions;
    setShowRevisions(next);
    if (next) {
      const res = await fetch(
        `/api/projects/${projectId}/stages/${selectedKey}/revisions`,
      );
      const data = await res.json();
      setRevisions(data.revisions ?? []);
    }
  }

  const pptxUrl = (stage?.outputMeta as { pptxUrl?: string } | null)?.pptxUrl;
  const isIntake = selectedKey === "intake";
  const runnable = def?.runnable !== false;
  const canApprove = stage && stage.outputMd && stage.status !== "approved";

  return (
    <div className="min-h-screen flex flex-col">
      <AppHeader />
      <div className="border-b border-[var(--border)] bg-[var(--surface)]">
        <div className="mx-auto max-w-6xl px-6 py-4 flex items-center justify-between">
          <div>
            <Link
              href="/"
              className="text-xs text-[var(--text-muted)] hover:text-[var(--text)]"
            >
              ← All projects
            </Link>
            <h1 className="text-xl font-[family-name:var(--font-display)] font-semibold mt-1">
              {clientName}
            </h1>
          </div>
          <div className="text-right">
            <div className="text-sm text-[var(--text-muted)] capitalize">
              {status.replace("_", " ")}
            </div>
            <div className="text-2xl font-[family-name:var(--font-display)] font-semibold">
              {percent}%
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-6xl w-full px-6 py-8 flex gap-8 flex-1">
        {/* Stage rail */}
        <nav className="w-64 shrink-0 space-y-6">
          {PHASE_ORDER.map((phase) => {
            const phaseStages = WEBINAR_PIPELINE.filter((s) => s.phase === phase);
            return (
              <div key={phase}>
                <h2 className="text-xs uppercase tracking-wide text-[var(--text-muted)] mb-2">
                  {PHASE_LABELS[phase]}
                </h2>
                <ul className="space-y-0.5">
                  {phaseStages.map((s) => {
                    const st = stageMap.get(s.key);
                    const active = s.key === selectedKey;
                    return (
                      <li key={s.key}>
                        <button
                          onClick={() => {
                            setSelectedKey(s.key);
                            setFeedback("");
                            setError(null);
                            setShowRevisions(false);
                          }}
                          className={`w-full text-left px-3 py-2 rounded-[var(--radius)] text-sm flex items-center gap-2.5 transition-colors ${
                            active
                              ? "bg-[var(--bg)] border border-[var(--border)]"
                              : "hover:bg-[var(--bg)] border border-transparent"
                          }`}
                        >
                          <span
                            className="h-2 w-2 rounded-full shrink-0"
                            style={{ background: statusColor(st?.status ?? "not_started") }}
                          />
                          <span className="flex-1 truncate">{s.label}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </nav>

        {/* Main pane */}
        <main className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-4 mb-1">
            <div>
              <h2 className="text-lg font-[family-name:var(--font-display)] font-semibold">
                {def?.label}
              </h2>
              <p className="text-sm text-[var(--text-muted)] mt-1 max-w-2xl">
                {def?.description}
              </p>
            </div>
            <span
              className="shrink-0 rounded-full px-2.5 py-1 text-xs font-medium"
              style={{
                background: "var(--bg)",
                color: statusColor(stage?.status ?? "not_started"),
                border: `1px solid ${statusColor(stage?.status ?? "not_started")}`,
              }}
            >
              {statusLabel(stage?.status ?? "not_started")}
            </span>
          </div>

          {/* Gate score */}
          {stage?.scoreJson && VOICE_GATED_STAGES.has(selectedKey) && (
            <GateBadge score={stage.scoreJson} attempts={stage.gateAttempts} />
          )}

          {/* Rules audit */}
          {stage?.auditJson && !isIntake && (
            <AuditPanel audit={stage.auditJson} onFix={fixFromAudit} busy={busy !== null} />
          )}

          {error && (
            <p className="mt-4 text-sm text-[var(--warn)] rounded-[var(--radius)] border border-[var(--warn)] px-3 py-2">
              {error}
            </p>
          )}

          {/* Output */}
          <div className="mt-5 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-6 min-h-[200px]">
            {isIntake ? (
              <div className="prose-stage whitespace-pre-wrap">{intakeText || "(no intake)"}</div>
            ) : stage?.outputMd ? (
              <>
                {pptxUrl && (
                  <a
                    href={pptxUrl}
                    className="inline-block mb-4 rounded-[var(--radius)] px-4 py-2 text-sm font-medium"
                    style={{ background: theme.color.accent, color: theme.color.accentText }}
                  >
                    Download .pptx
                  </a>
                )}
                <MarkdownView>{stage.outputMd}</MarkdownView>
              </>
            ) : (
              <p className="text-[var(--text-muted)] text-sm">
                {selectedKey === "brand-kit"
                  ? "Paste the client's website URL in the box below and run to scrape their brand kit."
                  : "Not generated yet. Run this stage to produce the deliverable."}
              </p>
            )}
          </div>

          {/* Controls */}
          {runnable && !isIntake && (
            <div className="mt-5 space-y-3">
              <textarea
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                rows={3}
                placeholder={
                  selectedKey === "brand-kit"
                    ? "Paste the client's website URL here…"
                    : "Optional: feedback to fold into a re-run, or paste a revision request before rejecting."
                }
                className="w-full rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
              />
              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={() => runStage("run")}
                  disabled={busy !== null}
                  className="rounded-[var(--radius)] px-4 py-2 text-sm font-medium disabled:opacity-50"
                  style={{ background: theme.color.accent, color: theme.color.accentText }}
                >
                  {busy === "run"
                    ? "Generating…"
                    : stage?.outputMd
                      ? "Re-run"
                      : "Run stage"}
                </button>

                {canApprove && (
                  <button
                    onClick={approve}
                    disabled={busy !== null}
                    className="rounded-[var(--radius)] px-4 py-2 text-sm font-medium disabled:opacity-50"
                    style={{ background: theme.color.ok, color: "#06281C" }}
                  >
                    {busy === "approve" ? "Approving…" : "Approve"}
                  </button>
                )}

                {stage?.outputMd && (
                  <button
                    onClick={() => runStage("reject")}
                    disabled={busy !== null}
                    className="rounded-[var(--radius)] border border-[var(--border)] px-4 py-2 text-sm font-medium disabled:opacity-50 hover:border-[var(--warn)]"
                  >
                    {busy === "reject" ? "Re-running…" : "Reject & re-run"}
                  </button>
                )}

                {stage?.outputMd && (
                  <button
                    onClick={loadRevisions}
                    className="ml-auto text-sm text-[var(--text-muted)] hover:text-[var(--text)]"
                  >
                    {showRevisions ? "Hide history" : "Revision history"}
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Revisions */}
          {showRevisions && (
            <div className="mt-6 space-y-4">
              <h3 className="text-sm font-medium text-[var(--text-muted)]">
                Revision history ({revisions.length})
              </h3>
              {revisions.length === 0 && (
                <p className="text-sm text-[var(--text-muted)]">No prior revisions.</p>
              )}
              {revisions.map((r) => (
                <details
                  key={r.id}
                  className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-4"
                >
                  <summary className="cursor-pointer text-sm">
                    {new Date(r.createdAt).toLocaleString()}
                    {r.feedback ? " — rejected with feedback" : ""}
                  </summary>
                  {r.feedback && (
                    <p className="mt-2 text-xs text-[var(--text-muted)]">
                      <span className="font-medium">Feedback:</span> {r.feedback}
                    </p>
                  )}
                  <div className="mt-3 border-t border-[var(--border)] pt-3">
                    <MarkdownView>{r.outputMd}</MarkdownView>
                  </div>
                </details>
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function GateBadge({ score, attempts }: { score: GateScore; attempts: number }) {
  const color = score.passed ? theme.color.ok : theme.color.warn;
  return (
    <div className="mt-4 rounded-[var(--radius)] border bg-[var(--surface)] p-3" style={{ borderColor: color }}>
      <div className="flex items-center gap-3 text-sm">
        <span className="font-medium" style={{ color }}>
          Gate {score.passed ? "passed" : "did not pass"}
        </span>
        <span className="text-[var(--text-muted)]">Score {score.score}/100</span>
        <span className="text-[var(--text-muted)]">
          {attempts} attempt{attempts === 1 ? "" : "s"}
        </span>
      </div>
      {score.violations.length > 0 && (
        <ul className="mt-2 space-y-1">
          {score.violations.map((v, i) => (
            <li key={i} className="text-xs text-[var(--text-muted)]">
              <span className="uppercase font-medium mr-1.5" style={{ color: v.severity === "high" ? theme.color.warn : undefined }}>
                {v.severity}
              </span>
              {v.note}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AuditPanel({
  audit,
  onFix,
  busy,
}: {
  audit: AuditResult;
  onFix: (audit: AuditResult) => void;
  busy: boolean;
}) {
  const clean = audit.violations.length === 0;
  const color = clean ? theme.color.ok : theme.color.warn;
  return (
    <div className="mt-3 rounded-[var(--radius)] border bg-[var(--surface)] p-3" style={{ borderColor: color }}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium" style={{ color }}>
            Rules audit {clean ? "clean" : `— ${audit.violations.length} issue${audit.violations.length === 1 ? "" : "s"}`}
          </span>
          {audit.summary && <span className="text-[var(--text-muted)] text-xs">{audit.summary}</span>}
        </div>
        {!clean && (
          <button
            onClick={() => onFix(audit)}
            disabled={busy}
            className="shrink-0 rounded-[var(--radius)] border px-2.5 py-1 text-xs font-medium disabled:opacity-50 hover:border-[var(--accent)]"
            style={{ borderColor: "var(--border)" }}
          >
            Fix &amp; re-run
          </button>
        )}
      </div>
      {!clean && (
        <ul className="mt-2 space-y-1.5">
          {audit.violations.map((v, i) => (
            <li key={i} className="text-xs text-[var(--text-muted)]">
              <span
                className="uppercase font-medium mr-1.5"
                style={{ color: v.severity === "high" ? theme.color.warn : undefined }}
              >
                {v.severity}
              </span>
              <span className="text-[var(--text)]">{v.rule}</span>
              {v.evidence && <span className="italic"> — “{v.evidence}”</span>}
              {v.fix && <span> → {v.fix}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
