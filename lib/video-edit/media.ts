/**
 * ffmpeg wrapper. Prefers FFMPEG_PATH, then a binary on PATH, then the
 * ffmpeg-static package (what Vercel runs). No GPU.
 */
import { execFile } from "node:child_process";
import { createRequire } from "node:module";
import { promisify } from "node:util";
import type { TimeRange, VideoAspect } from "./types";
import { parseFrameRate, type FrameRate } from "./time";

const exec = promisify(execFile);

export interface Probe {
  duration: number;
  width: number;
  height: number;
  frameRate: FrameRate;
  hasAudio: boolean;
  audioChannels: number;
  audioRate: number;
  timecode: string | null;
}

export interface Binaries {
  ffmpeg: string;
  ffprobe: string | null;
}

let cached: Binaries | null = null;

export async function resolveBinaries(): Promise<Binaries> {
  if (cached) return cached;
  const fromEnv = process.env.FFMPEG_PATH?.trim();
  if (fromEnv) {
    if (!(await canRun(fromEnv, ["-version"]))) {
      throw new Error(`FFMPEG_PATH is set but could not run: ${fromEnv}`);
    }
    const ffprobe = await findFfprobe(null);
    cached = { ffmpeg: fromEnv, ffprobe };
    return cached;
  }
  if (await canRun("ffmpeg", ["-version"])) {
    cached = { ffmpeg: "ffmpeg", ffprobe: await findFfprobe(null) };
    return cached;
  }
  const bundled = bundledFfmpeg();
  if (bundled && (await canRun(bundled, ["-version"]))) {
    cached = { ffmpeg: bundled, ffprobe: await findFfprobe(null) };
    return cached;
  }
  throw new Error(
    "ffmpeg is not available. Install it locally (it is picked up from PATH) or set FFMPEG_PATH. Deployed functions use the ffmpeg-static package; set FFMPEG_PATH if the function cannot see that binary.",
  );
}

async function findFfprobe(beside: string | null): Promise<string | null> {
  const env = process.env.FFPROBE_PATH?.trim();
  if (env && (await canRun(env, ["-version"]))) return env;
  if (beside) {
    const sibling = beside.replace(/ffmpeg$/, "ffprobe");
    if (sibling !== beside && (await canRun(sibling, ["-version"]))) return sibling;
  }
  if (await canRun("ffprobe", ["-version"])) return "ffprobe";
  return null;
}

function bundledFfmpeg(): string | null {
  try {
    const req = createRequire(import.meta.url);
    const resolved = req("ffmpeg-static") as string | null;
    return resolved || null;
  } catch {
    return null;
  }
}

async function canRun(cmd: string, args: string[]): Promise<boolean> {
  try {
    await exec(cmd, args, { timeout: 15_000 });
    return true;
  } catch {
    return false;
  }
}

export async function probeMedia(filePath: string): Promise<Probe> {
  const bins = await resolveBinaries();
  if (bins.ffprobe) {
    try {
      return await probeWithFfprobe(bins.ffprobe, filePath);
    } catch {
      // fall through to ffmpeg -i
    }
  }
  return probeWithFfmpeg(bins.ffmpeg, filePath);
}

async function probeWithFfprobe(ffprobe: string, filePath: string): Promise<Probe> {
  const { stdout } = await exec(
    ffprobe,
    ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", filePath],
    { timeout: 30_000, maxBuffer: 8 * 1024 * 1024 },
  );
  const json = JSON.parse(stdout) as {
    format?: { duration?: string; tags?: Record<string, string> };
    streams?: {
      codec_type?: string;
      width?: number;
      height?: number;
      r_frame_rate?: string;
      avg_frame_rate?: string;
      channels?: number;
      sample_rate?: string;
      tags?: Record<string, string>;
    }[];
  };
  const video = json.streams?.find((s) => s.codec_type === "video");
  if (!video?.width || !video.height) throw new Error("This file has no video stream.");
  const audio = json.streams?.find((s) => s.codec_type === "audio");
  const duration = Number(json.format?.duration);
  if (!Number.isFinite(duration) || duration <= 0) throw new Error("Could not read the video duration.");
  const tags = { ...json.format?.tags, ...video.tags };
  const timecode = tags?.timecode || tags?.TIMECODE || null;
  return {
    duration,
    width: video.width,
    height: video.height,
    frameRate: parseFrameRate(video.r_frame_rate || video.avg_frame_rate),
    hasAudio: Boolean(audio),
    audioChannels: audio?.channels ?? 0,
    audioRate: audio?.sample_rate ? Number(audio.sample_rate) : 48000,
    timecode,
  };
}

async function probeWithFfmpeg(ffmpeg: string, filePath: string): Promise<Probe> {
  let stderr = "";
  try {
    await exec(ffmpeg, ["-hide_banner", "-i", filePath], { timeout: 30_000 });
  } catch (err) {
    stderr = (err as { stderr?: string }).stderr ?? "";
  }
  const duration = parseDuration(stderr);
  const video = stderr.match(/Video:.*?(\d{2,5})x(\d{2,5})/);
  const fps = stderr.match(/(\d+(?:\.\d+)?)\s+fps/);
  if (!duration || !video) {
    throw new Error("Could not read this video. Export an mp4 or mov with a video stream and try again.");
  }
  const audio = /Audio:/.test(stderr);
  const rate = stderr.match(/(\d+)\s+Hz/);
  const stereo = /stereo|2 channels/.test(stderr);
  const tc = stderr.match(/timecode\s*[:=]\s*(\d+:\d+:\d+:\d+)/i);
  return {
    duration,
    width: Number(video[1]),
    height: Number(video[2]),
    frameRate: fps ? parseFrameRate(String(Math.round(Number(fps[1])))) : parseFrameRate("30/1"),
    hasAudio: audio,
    audioChannels: audio ? (stereo ? 2 : 1) : 0,
    audioRate: rate ? Number(rate[1]) : 48000,
    timecode: tc?.[1] ?? null,
  };
}

function parseDuration(stderr: string): number | null {
  const m = stderr.match(/Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)/);
  if (!m) return null;
  return Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]);
}

export async function detectSilences(filePath: string, duration: number): Promise<TimeRange[]> {
  const { ffmpeg } = await resolveBinaries();
  let stderr = "";
  try {
    const res = await exec(
      ffmpeg,
      ["-hide_banner", "-i", filePath, "-af", "silencedetect=noise=-35dB:d=0.30", "-f", "null", "-"],
      { timeout: 180_000, maxBuffer: 12 * 1024 * 1024 },
    );
    stderr = res.stderr ?? "";
  } catch (err) {
    stderr = (err as { stderr?: string }).stderr ?? "";
    if (!/silence_start/.test(stderr)) return [];
  }
  const ranges: TimeRange[] = [];
  let open: number | null = null;
  for (const line of stderr.split("\n")) {
    const start = line.match(/silence_start:\s*([0-9.]+)/);
    if (start) open = Number(start[1]);
    const end = line.match(/silence_end:\s*([0-9.]+)/);
    if (end && open !== null) {
      ranges.push({ start: open, end: Number(end[1]) });
      open = null;
    }
  }
  if (open !== null && duration - open > 0.3) ranges.push({ start: open, end: duration });
  return ranges;
}

export function buildFilter(opts: {
  kept: TimeRange[];
  hasAudio: boolean;
  width: number;
  height: number;
  srtPath: string | null;
  fontDir: string;
  forceStyle: string;
}): string {
  const vlabels: string[] = [];
  const alabels: string[] = [];
  const parts: string[] = [];
  opts.kept.forEach((k, i) => {
    const start = k.start.toFixed(3);
    const end = k.end.toFixed(3);
    const len = k.end - k.start;
    parts.push(`[0:v]trim=start=${start}:end=${end},setpts=PTS-STARTPTS[v${i}]`);
    vlabels.push(`[v${i}]`);
    if (opts.hasAudio) {
      const fade = len > 0.08 ? `,afade=t=in:st=0:d=0.015,afade=t=out:st=${Math.max(0, len - 0.015).toFixed(3)}:d=0.015` : "";
      parts.push(`[0:a]atrim=start=${start}:end=${end},asetpts=PTS-STARTPTS${fade}[a${i}]`);
      alabels.push(`[a${i}]`);
    }
  });
  const n = opts.kept.length;
  if (opts.hasAudio) {
    parts.push(`${vlabels.map((v, i) => `${v}${alabels[i]}`).join("")}concat=n=${n}:v=1:a=1[vc][ac]`);
  } else {
    parts.push(`${vlabels.join("")}concat=n=${n}:v=1:a=0[vc]`);
  }
  const scale = `scale=${opts.width}:${opts.height}:force_original_aspect_ratio=increase,crop=${opts.width}:${opts.height},setsar=1,format=yuv420p`;
  const burn = opts.srtPath
    ? `,subtitles=${filterPath(opts.srtPath)}:fontsdir=${filterPath(opts.fontDir)}:force_style='${opts.forceStyle.replace(/'/g, "")}'`
    : "";
  parts.push(`[vc]${scale}${burn}[vout]`);
  return parts.join(";");
}

function filterPath(p: string): string {
  return p.replace(/\\/g, "/").replace(/:/g, "\\:").replace(/'/g, "");
}

export async function renderPreview(opts: {
  filePath: string;
  outPath: string;
  kept: TimeRange[];
  hasAudio: boolean;
  width: number;
  height: number;
  srtPath: string | null;
  fontDir: string;
  forceStyle: string;
}): Promise<void> {
  const { ffmpeg } = await resolveBinaries();
  const filter = buildFilter(opts);
  const args = [
    "-y",
    "-hide_banner",
    "-i",
    opts.filePath,
    "-filter_complex",
    filter,
    "-map",
    "[vout]",
  ];
  if (opts.hasAudio) args.push("-map", "[ac]", "-c:a", "aac", "-b:a", "96k");
  else args.push("-an");
  args.push(
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-crf",
    "28",
    "-pix_fmt",
    "yuv420p",
    "-movflags",
    "+faststart",
    opts.outPath,
  );
  try {
    await exec(ffmpeg, args, { timeout: 300_000, maxBuffer: 16 * 1024 * 1024 });
  } catch (err) {
    const stderr = (err as { stderr?: string }).stderr ?? "";
    const tail = stderr.split("\n").slice(-12).join("\n");
    throw new Error(`Preview render failed. ${tail || (err instanceof Error ? err.message : String(err))}`);
  }
}

export function sourceIsLandscape(width: number, height: number): boolean {
  return width > height * 1.15;
}

export type { VideoAspect };
