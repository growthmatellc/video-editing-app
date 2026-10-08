/**
 * Timeline interchange for DaVinci Resolve on the finishing Mac.
 *
 * FCPXML 1.9 is the primary import (File > Import > Timeline). Resolve on Mac
 * accepts FCPXML 1.3–1.9; 1.10+ bundles (.fcpxmld) are not what we emit.
 * A CMX 3600 EDL is the fallback (pre-conformed EDL against the one source).
 * Captions are a separate SRT — Resolve does not reliably carry them inside
 * either interchange file.
 */
import type { FrameRate } from "./time";
import { edlRate, fcpxTime, frameDuration, parseTimecode, toTimecode } from "./time";
import type { TimeRange, VideoEditMeta } from "./types";

export const EDL_REEL = "STUDIO";

export function handoffDropDir(): string {
  const raw = process.env.NEXT_PUBLIC_APP_NAME ?? "Webinar Studio";
  const slug = raw.replace(/[^A-Za-z0-9]+/g, "") || "WebinarStudio";
  return `/Users/Shared/${slug}/handoff`;
}

export function safeMediaName(name: string): string {
  const base = name.split(/[/\\]/).pop() || "source.mp4";
  const clean = base.replace(/[^A-Za-z0-9._-]+/g, "_");
  if (/\.(mp4|mov)$/i.test(clean)) return clean;
  return `${clean}.mp4`;
}

export function buildFcpxml(opts: {
  clientName: string;
  fileName: string;
  dropDir: string;
  duration: number;
  width: number;
  height: number;
  frameRate: FrameRate;
  hasAudio: boolean;
  audioChannels: number;
  audioRate: number;
  kept: TimeRange[];
}): string {
  const fr = opts.frameRate;
  const width = even(opts.width || 1920);
  const height = even(opts.height || 1080);
  const name = xml(opts.clientName.trim() || "Video Edit");
  const fileName = opts.fileName;
  const src = fileUrl(opts.dropDir, fileName);
  const assetDur = fcpxTime(opts.duration, fr);
  const seqDur = fcpxTime(sumDuration(opts.kept), fr);
  const audio =
    opts.hasAudio
      ? ` hasAudio="1" audioSources="1" audioChannels="${Math.max(1, opts.audioChannels || 2)}" audioRate="${opts.audioRate || 48000}"`
      : ` hasAudio="0"`;

  let offset = 0;
  const clips = opts.kept
    .map((k) => {
      const start = fcpxTime(k.start, fr);
      const duration = fcpxTime(k.end - k.start, fr);
      const at = fcpxTime(offset, fr);
      offset += k.end - k.start;
      return `            <asset-clip ref="r2" offset="${at}" name="${xml(fileName)}" start="${start}" duration="${duration}" tcFormat="NDF"/>`;
    })
    .join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.9">
  <resources>
    <format id="r1" name="FFVideoFormatRateUndefined" frameDuration="${frameDuration(fr)}" width="${width}" height="${height}" colorSpace="1-1-1 (Rec. 709)"/>
    <asset id="r2" name="${xml(fileName)}" uid="webinar-studio-source" src="${xml(src)}" start="0s" duration="${assetDur}" hasVideo="1" format="r1" videoSources="1"${audio}/>
  </resources>
  <library>
    <event name="${name}">
      <project name="${name} video edit">
        <sequence format="r1" duration="${seqDur}" tcStart="0s" tcFormat="NDF"${opts.hasAudio ? ` audioLayout="stereo" audioRate="48k"` : ""}>
          <spine>
${clips}
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
`;
}

export function buildEdl(opts: {
  title: string;
  fileName: string;
  frameRate: FrameRate;
  timecode: string | null;
  kept: TimeRange[];
}): { edl: string; note: string | null } {
  const { fps, note } = edlRate(opts.frameRate);
  const origin = parseTimecode(opts.timecode, fps) ?? 0;
  const title = opts.title.replace(/[^\w .'-]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 60) || "Video Edit";
  const lines = [
    `TITLE: ${title}`,
    "FCM: NON-DROP FRAME",
    "",
  ];
  let record = 0;
  opts.kept.forEach((k, i) => {
    const n = String(i + 1).padStart(3, "0");
    const srcIn = toTimecode(origin + k.start, fps);
    const srcOut = toTimecode(origin + k.end, fps);
    const recIn = toTimecode(record, fps);
    const recOut = toTimecode(record + (k.end - k.start), fps);
    record += k.end - k.start;
    lines.push(`${n}  ${EDL_REEL.padEnd(8, " ")} V     C        ${srcIn} ${srcOut} ${recIn} ${recOut}`);
    lines.push(`* FROM CLIP NAME: ${opts.fileName}`);
    lines.push("");
  });
  return { edl: `${lines.join("\n")}\n`, note };
}

export function buildHandoffText(meta: Pick<
  VideoEditMeta,
  "format" | "aspect" | "removed" | "captions" | "handoff" | "warnings" | "outputDuration"
> & { clientName: string; sourceIncluded: boolean }): string {
  const { handoff, captions } = meta;
  const cuts =
    meta.removed.length === 0
      ? "No ranges were removed."
      : meta.removed
          .map((r) => {
            const why = r.reasons.join(", ");
            return `- ${r.start.toFixed(2)}s–${r.end.toFixed(2)}s  ${why}${r.detail ? ` — ${r.detail}` : ""}`;
          })
          .join("\n");

  const sourceLine = meta.sourceIncluded
    ? `The source file ${handoff.sourceFileName} is in this zip.`
    : `The source file was too large to put in the zip. Download it from the stage and save it as ${handoff.sourceFileName} in the same folder.`;

  return `Video edit handoff
==================

Client: ${meta.clientName}
Format: ${meta.format}
Preview framing: ${meta.aspect}
Cut timeline length: ${meta.outputDuration?.toFixed(2) ?? "unknown"}s

Drop folder
-----------
Unzip these files DIRECTLY into:

  ${handoff.dropDir}

The files should sit in that folder, not inside an extra nested folder.
${sourceLine}
edit.fcpxml looks for the source at:

  ${handoff.dropDir}/${handoff.sourceFileName}

This app does not control DaVinci. Import the files on the Mac mini.

Import the cut (FCPXML — use this first)
----------------------------------------
1. Open DaVinci Resolve and create or open the project.
2. Choose File > Import > Timeline… (Shift-Command-I).
3. Select edit.fcpxml.
4. Leave "Automatically import source clips into media pool" on.
5. The timeline matches the SOURCE frame size and frame rate. It is a straight cut of the original camera frames. The mp4 in the browser is only a review proxy, framed to ${meta.aspect} with a center crop.
6. For a vertical delivery, set the timeline resolution to 1080x1920 and set clip scaling to Fill, then reframe. For landscape, use 1920x1080.
7. If a clip is offline (red), right-click it in the Media Pool, choose Relink Selected Clips, and point at ${handoff.dropDir}.

Import captions
---------------
captions.srt is timed to the CUT timeline. The first frame of the edit is 00:00:00,000. Do not lay it on the raw camera clip.
With the cut timeline open, choose File > Import > Subtitle… and select captions.srt.

Style that subtitle track in Resolve:
  Color: ${captions.fillHex}${captions.boxHex ? ` text on a ${captions.boxHex} background` : ""}
  Outline: ${captions.outlineHex}
  Font: ${captions.requestedFont && captions.fontSubstituted ? captions.requestedFont : captions.fontName}
${captions.note}

The preview mp4 already has burned-in captions for review in the browser. Do not master from that proxy.

If FCPXML will not open
-----------------------
1. Import ${handoff.sourceFileName} into the Media Pool.
2. Right-click that clip and choose Timelines > Import > Pre-conformed EDL.
3. Select edit.edl. The reel name is ${handoff.reel}. Source timecode starts at the file's embedded timecode, or at 00:00:00:00 when the file has none.
4. Import captions.srt the same way as above.

What was cut
------------
${cuts}

${meta.warnings.length ? `Notes\n-----\n${meta.warnings.map((w) => `- ${w}`).join("\n")}\n` : ""}`.trimEnd() + "\n";
}

function sumDuration(ranges: TimeRange[]): number {
  return ranges.reduce((n, r) => n + Math.max(0, r.end - r.start), 0);
}

function even(n: number): number {
  const r = Math.max(2, Math.round(n));
  return r % 2 === 0 ? r : r - 1;
}

function xml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fileUrl(dir: string, name: string): string {
  const path = `${dir.replace(/\/+$/, "")}/${name}`;
  return `file://${encodeURI(path)}`;
}
