"use client";

import { useState } from "react";
import { theme } from "@/theme/tokens";
import { formatSeconds } from "@/lib/video-edit/time";
import { rulesBlurb } from "@/lib/video-edit/cuts";
import {
  REASON_LABEL,
  VIDEO_FORMATS,
  readVideoEditMeta,
  type VideoAspect,
  type VideoEditRequest,
  type VideoFormat,
} from "@/lib/video-edit/types";

interface Props {
  projectId: string;
  stage:
    | {
        outputMd: string | null;
        outputMeta: Record<string, unknown> | null;
        status: string;
      }
    | undefined;
  blobUploadEnabled: boolean;
  transcriptionConfigured: boolean;
  busy: null | "run" | "approve" | "reject";
  feedback: string;
  onFeedback: (value: string) => void;
  onUploaded: (outputMeta: Record<string, unknown>) => void;
  onRun: (request: VideoEditRequest) => void;
  onReject: (request: VideoEditRequest) => void;
  onApprove: () => void;
  onHistory: () => void;
  showHistory: boolean;
}

export function VideoEditStage({
  projectId,
  stage,
  blobUploadEnabled,
  transcriptionConfigured,
  busy,
  feedback,
  onFeedback,
  onUploaded,
  onRun,
  onReject,
  onApprove,
  onHistory,
  showHistory,
}: Props) {
  const meta = readVideoEditMeta(stage?.outputMeta ?? null);
  const [format, setFormat] = useState<VideoFormat>(meta?.format ?? "talking-head");
  const [aspect, setAspect] = useState<VideoAspect>(meta?.aspect ?? "9:16");
  const [transcriptText, setTranscriptText] = useState(meta?.transcriptText ?? "");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const landscapeOk = Boolean(meta?.source?.landscape);
  const aspectValue: VideoAspect = aspect === "16:9" && landscapeOk ? "16:9" : "9:16";
  const request: VideoEditRequest = { format, aspect: aspectValue, transcriptText };
  const locked = busy !== null || uploading;
  const hasOutput = Boolean(stage?.outputMd && meta?.outputs);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      let res: Response;
      if (blobUploadEnabled) {
        const { upload } = await import("@vercel/blob/client");
        const blob = await upload(`video-edit/${projectId}/${file.name}`, file, {
          access: "public",
          handleUploadUrl: "/api/uploads",
          multipart: file.size > 4 * 1024 * 1024,
        });
        res = await fetch(`/api/projects/${projectId}/stages/video-edit/source`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            url: blob.url,
            fileName: file.name,
            contentType: file.type,
            size: file.size,
          }),
        });
      } else {
        const form = new FormData();
        form.append("file", file);
        res = await fetch(`/api/projects/${projectId}/stages/video-edit/source`, {
          method: "POST",
          body: form,
        });
      }
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Upload failed");
      onUploaded(data.outputMeta);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="mt-5 space-y-5">
      <section className="grid gap-3 sm:grid-cols-3">
        {VIDEO_FORMATS.map((f) => {
          const active = format === f.id;
          return (
            <button
              key={f.id}
              type="button"
              disabled={locked}
              onClick={() => setFormat(f.id)}
              className="rounded-[var(--radius)] border px-3 py-3 text-left disabled:opacity-50"
              style={{
                borderColor: active ? theme.color.accent : "var(--border)",
                background: "var(--surface)",
              }}
            >
              <div className="text-sm font-medium">{f.label}</div>
              <p className="mt-1 text-xs text-[var(--text-muted)]">{f.detail}</p>
            </button>
          );
        })}
      </section>

      <section className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm font-medium">
            Footage
            <input
              type="file"
              accept="video/mp4,video/quicktime,.mp4,.mov"
              disabled={locked}
              className="mt-1 block text-sm text-[var(--text-muted)] file:mr-3 file:rounded-[var(--radius)] file:border-0 file:bg-[var(--bg)] file:px-3 file:py-1.5 file:text-sm file:text-[var(--text)]"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                void onFile(file);
              }}
            />
          </label>
          {uploading && <span className="text-sm text-[var(--text-muted)]">Uploading…</span>}
        </div>
        {uploadError && <p className="text-sm text-[var(--warn)]">{uploadError}</p>}
        {meta?.source ? (
          <p className="text-sm text-[var(--text-muted)]">
            {meta.source.fileName}
            {meta.source.duration != null ? ` · ${formatSeconds(meta.source.duration)}` : ""}
            {meta.source.width && meta.source.height ? ` · ${meta.source.width}×${meta.source.height}` : ""}
            {meta.source.landscape ? " · landscape source" : " · vertical or square source"}
          </p>
        ) : (
          <p className="text-sm text-[var(--text-muted)]">
            Upload an mp4 or mov. {blobUploadEnabled ? "Large files upload directly to storage." : "Local dev accepts the file on this server. On Vercel, set BLOB_READ_WRITE_TOKEN for files over about 4.5MB."}
          </p>
        )}
        <fieldset className="flex flex-wrap gap-4 text-sm">
          <legend className="sr-only">Frame</legend>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="aspect"
              checked={aspectValue === "9:16"}
              disabled={locked}
              onChange={() => setAspect("9:16")}
            />
            Vertical 9:16
          </label>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="aspect"
              checked={aspectValue === "16:9"}
              disabled={locked || !landscapeOk}
              onChange={() => setAspect("16:9")}
            />
            Landscape 16:9
          </label>
        </fieldset>
        {!landscapeOk && (
          <p className="text-xs text-[var(--text-muted)]">
            Landscape is available only when the upload is clearly wider than it is tall.
          </p>
        )}
      </section>

      <details className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-4">
        <summary className="cursor-pointer text-sm font-medium">
          Transcript {transcriptionConfigured ? "(optional — a key is configured)" : "(needed — no transcription key)"}
        </summary>
        <p className="mt-2 text-xs text-[var(--text-muted)]">
          {transcriptionConfigured
            ? "Leave this empty to transcribe on run. Or paste word times, an SRT, or a WebVTT file to skip the API."
            : "Set DEEPGRAM_API_KEY, ASSEMBLYAI_API_KEY, or OPENAI_API_KEY. Or paste timestamps, one word or line at a time: 0.00 0.40 Hello"}
        </p>
        <textarea
          value={transcriptText}
          onChange={(e) => setTranscriptText(e.target.value)}
          rows={5}
          disabled={locked}
          placeholder={"0.10 0.40 Hello\n0.40 0.70 there"}
          className="mt-2 w-full rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
        />
      </details>

      {hasOutput && meta?.outputs && (
        <section className="space-y-4">
          <div className="flex justify-center rounded-[var(--radius)] border border-[var(--border)] bg-black p-3">
            <video
              key={meta.outputs.previewUrl}
              src={meta.outputs.previewUrl}
              controls
              playsInline
              preload="metadata"
              className="max-h-[520px] w-auto max-w-full rounded-[var(--radius)] bg-black"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Download href={meta.outputs.previewUrl} label="Download preview .mp4" />
            <Download href={meta.outputs.handoffZipUrl} label="Download Resolve handoff .zip" />
            <Download href={meta.outputs.srtUrl} label="SRT" />
            <Download href={meta.outputs.fcpxmlUrl} label="FCPXML" />
            <Download href={meta.outputs.edlUrl} label="EDL" />
          </div>
          <p className="text-sm text-[var(--text-muted)]">
            The preview is a {meta.aspect} proxy with burned-in captions. Unzip the handoff into{" "}
            <code>{meta.handoff.dropDir}</code> on the Mac mini, then in Resolve choose File &gt; Import &gt; Timeline and open edit.fcpxml. Import captions.srt with File &gt; Import &gt; Subtitle onto that timeline.
          </p>
          <p className="text-sm">{meta.captions.note}</p>
          <CutTimeline meta={meta} />
          <div>
            <h3 className="text-sm font-medium">Removed ranges</h3>
            <p className="mt-1 text-xs text-[var(--text-muted)]">{rulesBlurb(meta.rules)}</p>
            {meta.removed.length === 0 ? (
              <p className="mt-2 text-sm text-[var(--text-muted)]">Nothing was removed.</p>
            ) : (
              <table className="mt-2 w-full text-left text-sm">
                <thead className="text-xs text-[var(--text-muted)]">
                  <tr>
                    <th className="py-1 pr-3 font-medium">In</th>
                    <th className="py-1 pr-3 font-medium">Out</th>
                    <th className="py-1 font-medium">Why</th>
                  </tr>
                </thead>
                <tbody>
                  {meta.removed.map((r, i) => (
                    <tr key={i} className="border-t border-[var(--border)]">
                      <td className="py-1.5 pr-3 tabular-nums">{formatSeconds(r.start)}</td>
                      <td className="py-1.5 pr-3 tabular-nums">{formatSeconds(r.end)}</td>
                      <td className="py-1.5">
                        {r.reasons.map((reason) => REASON_LABEL[reason] ?? reason).join(", ")}
                        {r.detail ? <span className="text-[var(--text-muted)]"> — {r.detail}</span> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          {meta.words.length > 0 && (
            <div>
              <h3 className="text-sm font-medium">Transcript</h3>
              <p className="mt-2 text-sm leading-relaxed">
                {meta.words.map((w, i) => {
                  const mid = (w.start + w.end) / 2;
                  const removed = meta.removed.some((r) => mid >= r.start && mid <= r.end);
                  return (
                    <span key={i} className={removed ? "text-[var(--text-muted)] line-through" : undefined}>
                      {w.text}{" "}
                    </span>
                  );
                })}
              </p>
            </div>
          )}
          {meta.warnings.length > 0 && (
            <ul className="space-y-1 text-sm text-[var(--warn)]">
              {meta.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      {!hasOutput && meta?.source && (
        <p className="text-sm text-[var(--text-muted)]">
          Footage is attached. Run the stage to transcribe, cut dead air, fillers, and retakes, and build the preview.
        </p>
      )}

      <div className="space-y-3">
        <textarea
          value={feedback}
          onChange={(e) => onFeedback(e.target.value)}
          rows={3}
          disabled={locked}
          placeholder="Optional note. Recognized on re-run: tighter, looser, silence:0.8, keep fillers, keep retakes, vertical, landscape."
          className="w-full rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
        />
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => onRun(request)}
            disabled={locked || !meta?.source}
            className="rounded-[var(--radius)] px-4 py-2 text-sm font-medium disabled:opacity-50"
            style={{ background: theme.color.accent, color: theme.color.accentText }}
          >
            {busy === "run" ? "Cutting…" : hasOutput ? "Re-run" : "Run stage"}
          </button>
          {hasOutput && stage?.status !== "approved" && (
            <button
              type="button"
              onClick={onApprove}
              disabled={locked}
              className="rounded-[var(--radius)] px-4 py-2 text-sm font-medium disabled:opacity-50"
              style={{ background: theme.color.ok, color: "#06281C" }}
            >
              {busy === "approve" ? "Approving…" : "Approve"}
            </button>
          )}
          {hasOutput && (
            <button
              type="button"
              onClick={() => onReject(request)}
              disabled={locked}
              className="rounded-[var(--radius)] border border-[var(--border)] px-4 py-2 text-sm font-medium disabled:opacity-50 hover:border-[var(--warn)]"
            >
              {busy === "reject" ? "Re-running…" : "Reject & re-run"}
            </button>
          )}
          {hasOutput && (
            <button
              type="button"
              onClick={onHistory}
              className="ml-auto text-sm text-[var(--text-muted)] hover:text-[var(--text)]"
            >
              {showHistory ? "Hide history" : "Revision history"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Download({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      className="inline-block rounded-[var(--radius)] px-3 py-1.5 text-sm font-medium"
      style={{ background: theme.color.accent, color: theme.color.accentText }}
    >
      {label}
    </a>
  );
}

function CutTimeline({ meta }: { meta: NonNullable<ReturnType<typeof readVideoEditMeta>> }) {
  const duration = meta.source.duration;
  if (!duration || duration <= 0) return null;
  const marks = [
    ...meta.kept.map((k) => ({ ...k, removed: false })),
    ...meta.removed.map((r) => ({ start: r.start, end: r.end, removed: true })),
  ].sort((a, b) => a.start - b.start);
  return (
    <div>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-[var(--bg)]" aria-hidden>
        {marks.map((m, i) => (
          <div
            key={i}
            style={{
              width: `${((m.end - m.start) / duration) * 100}%`,
              background: m.removed ? theme.color.warn : theme.color.ok,
            }}
          />
        ))}
      </div>
      <p className="mt-1 text-xs text-[var(--text-muted)]">
        Green stays. Amber is removed.
        {meta.outputDuration != null ? ` Cut length ${formatSeconds(meta.outputDuration)}.` : ""}
      </p>
    </div>
  );
}
