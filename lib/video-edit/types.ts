/**
 * Shared types for the Video Edit stage. This file is imported by the client
 * review UI, so it must stay free of Node and database imports.
 */

export const VIDEO_FORMATS = [
  {
    id: "short-form-ad",
    label: "Short-form ad",
    detail: "Vertical 9:16. Aimed at 15–60 seconds.",
    minSeconds: 15,
    maxSeconds: 60,
  },
  {
    id: "funnel-video",
    label: "Funnel video",
    detail: "Webinar invite or call confirmation. Vertical 9:16.",
    minSeconds: null,
    maxSeconds: 120,
  },
  {
    id: "talking-head",
    label: "Talking-head",
    detail: "Organic social talking head. Vertical 9:16.",
    minSeconds: null,
    maxSeconds: null,
  },
] as const;

export type VideoFormat = (typeof VIDEO_FORMATS)[number]["id"];
export type VideoAspect = "9:16" | "16:9";

export interface TranscriptWord {
  text: string;
  start: number;
  end: number;
}

export type CutReason = "silence" | "filler" | "retake" | "stutter";

export interface TimeRange {
  start: number;
  end: number;
}

export interface Removal extends TimeRange {
  reasons: CutReason[];
  detail: string;
}

export interface EditRules {
  /** Remove a silence only when the gap is longer than this. */
  silenceSeconds: number;
  /** Leave this much of each interior silence so words are not clipped. */
  padSeconds: number;
  cutFillers: boolean;
  cutRetakes: boolean;
  cutStutters: boolean;
}

export const DEFAULT_RULES: EditRules = {
  silenceSeconds: 0.6,
  padSeconds: 0.08,
  cutFillers: true,
  cutRetakes: true,
  cutStutters: true,
};

export interface CaptionStyle {
  source: "brand-kit" | "default";
  fillHex: string;
  outlineHex: string;
  /**
   * When set, the brand color is drawn as a caption background. Used when the
   * approved brand color is too dark to read as text on footage.
   */
  boxHex: string | null;
  fontName: string;
  requestedFont: string | null;
  fontSubstituted: boolean;
  note: string;
}

export interface VideoSourceMeta {
  url: string;
  fileName: string;
  contentType: string;
  bytes: number;
  width: number | null;
  height: number | null;
  duration: number | null;
  landscape: boolean;
}

export interface VideoEditOutputs {
  previewUrl: string;
  srtUrl: string;
  fcpxmlUrl: string;
  edlUrl: string;
  handoffZipUrl: string;
}

export interface VideoEditHandoff {
  dropDir: string;
  sourceFileName: string;
  reel: string;
}

export interface VideoEditMeta {
  format: VideoFormat;
  aspect: VideoAspect;
  source: VideoSourceMeta;
  /** Operator-pasted transcript, kept so a re-run does not lose it. */
  transcriptText: string;
  transcriptProvider: string | null;
  words: TranscriptWord[];
  rules: EditRules;
  removed: Removal[];
  kept: TimeRange[];
  captions: CaptionStyle;
  outputs: VideoEditOutputs | null;
  warnings: string[];
  feedbackApplied: string[];
  outputDuration: number | null;
  handoff: VideoEditHandoff;
}

export interface VideoEditRequest {
  format?: VideoFormat;
  aspect?: VideoAspect;
  transcriptText?: string;
}

export function isVideoFormat(v: unknown): v is VideoFormat {
  return v === "short-form-ad" || v === "funnel-video" || v === "talking-head";
}

export function isVideoAspect(v: unknown): v is VideoAspect {
  return v === "9:16" || v === "16:9";
}

export function parseVideoEditRequest(v: unknown): VideoEditRequest | undefined {
  if (!v || typeof v !== "object") return undefined;
  const o = v as { format?: unknown; aspect?: unknown; transcriptText?: unknown };
  const req: VideoEditRequest = {};
  if (isVideoFormat(o.format)) req.format = o.format;
  if (isVideoAspect(o.aspect)) req.aspect = o.aspect;
  if (typeof o.transcriptText === "string") req.transcriptText = o.transcriptText.slice(0, 200_000);
  if (!req.format && !req.aspect && req.transcriptText === undefined) return undefined;
  return req;
}

export function readVideoEditMeta(meta: unknown): VideoEditMeta | null {
  if (!meta || typeof meta !== "object") return null;
  const ve = (meta as { videoEdit?: unknown }).videoEdit;
  if (!ve || typeof ve !== "object") return null;
  const v = ve as Partial<VideoEditMeta>;
  if (!v.source || typeof v.source !== "object" || typeof v.source.fileName !== "string") return null;
  return ve as VideoEditMeta;
}

export function formatLabel(id: VideoFormat): string {
  return VIDEO_FORMATS.find((f) => f.id === id)?.label ?? id;
}

export const REASON_LABEL: Record<CutReason, string> = {
  silence: "Dead air",
  filler: "Filler",
  retake: "Retake",
  stutter: "Stutter",
};
