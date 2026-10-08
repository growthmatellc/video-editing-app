import { rulesBlurb } from "./cuts";
import { formatSeconds } from "./time";
import { REASON_LABEL, formatLabel, type VideoEditMeta } from "./types";

export function renderSummary(meta: VideoEditMeta, clientName: string): string {
  const out = meta.outputs;
  const lines: string[] = [
    `# Video edit — ${formatLabel(meta.format)}`,
    "",
    `Preview proxy for **${clientName}**, framed to **${meta.aspect}** (center crop). The Resolve handoff is a straight cut of the original frames so it can be reframed on the Mac mini.`,
    "",
    `- Source: \`${meta.source.fileName}\`${meta.source.duration ? ` (${formatSeconds(meta.source.duration)})` : ""}${meta.source.width && meta.source.height ? `, ${meta.source.width}×${meta.source.height}` : ""}`,
    `- Cut timeline: ${meta.outputDuration != null ? formatSeconds(meta.outputDuration) : "—"}${meta.removed.length ? `, ${meta.removed.length} removed range${meta.removed.length === 1 ? "" : "s"}` : ", nothing removed"}`,
    `- Transcript: ${meta.transcriptProvider ?? (meta.words.length ? "pasted" : "none")}`,
    `- Captions: ${meta.captions.note}`,
    "",
  ];

  if (out) {
    lines.push(
      `**[Download preview .mp4](${out.previewUrl})**`,
      "",
      `**[Download Resolve handoff .zip](${out.handoffZipUrl})** — FCPXML, EDL, SRT, and the source file.`,
      "",
      `[SRT](${out.srtUrl}) · [FCPXML](${out.fcpxmlUrl}) · [EDL](${out.edlUrl})`,
      "",
      `Unzip the handoff into \`${meta.handoff.dropDir}\` and import \`edit.fcpxml\` with File > Import > Timeline. Import \`captions.srt\` onto that timeline with File > Import > Subtitle. If FCPXML will not open, use the EDL as a pre-conformed EDL (reel \`${meta.handoff.reel}\`).`,
      "",
    );
  }

  lines.push("## How the cuts were chosen", "", rulesBlurb(meta.rules), "");
  if (meta.feedbackApplied.length) {
    lines.push("## Feedback applied", "", ...meta.feedbackApplied.map((f) => `- ${f}`), "");
  }

  lines.push("## Removed ranges", "");
  if (!meta.removed.length) {
    lines.push("Nothing was removed.", "");
  } else {
    lines.push("| In | Out | Why |", "| --- | --- | --- |");
    for (const r of meta.removed) {
      const why = r.reasons.map((reason) => REASON_LABEL[reason] ?? reason).join(", ");
      const detail = r.detail.replace(/\|/g, "/");
      lines.push(`| ${formatSeconds(r.start)} | ${formatSeconds(r.end)} | ${why}${detail ? ` — ${detail}` : ""} |`);
    }
    lines.push("");
  }

  if (meta.words.length) {
    lines.push("## Transcript", "", meta.words.map((w) => w.text).join(" "), "");
  }

  if (meta.warnings.length) {
    lines.push("## Notes", "", ...meta.warnings.map((w) => `- ${w}`), "");
  }

  return lines.join("\n").trim() + "\n";
}
