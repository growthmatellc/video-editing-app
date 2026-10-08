/**
 * Captions are the transcript, timed to the cut timeline. Styling uses an
 * approved Brand Kit when one exists. Colors are never invented for a client:
 * the fallback is a plain white caption with a black outline.
 */
import { readdirSync } from "node:fs";
import { join } from "node:path";
import type { BrandKit } from "../slide-deck-schema";
import type { CaptionStyle, TimeRange, TranscriptWord, VideoAspect } from "./types";

const DEFAULT_FILL = "#FFFFFF";
const DEFAULT_OUTLINE = "#000000";
const BUNDLED_FONT = "Inter SemiBold";

export function wordsOnTimeline(words: TranscriptWord[], kept: TimeRange[]): TranscriptWord[] {
  const out: TranscriptWord[] = [];
  for (const w of words) {
    const mid = (w.start + w.end) / 2;
    const k = kept.find((r) => mid >= r.start - 0.001 && mid <= r.end + 0.001);
    if (!k) continue;
    const start = mapTime(Math.max(w.start, k.start), kept);
    const end = mapTime(Math.min(w.end, k.end), kept);
    if (end - start < 0.04) continue;
    out.push({ text: w.text, start, end });
  }
  return out;
}

/** Source time → time on the concatenated cut. */
export function mapTime(t: number, kept: TimeRange[]): number {
  let acc = 0;
  for (const k of kept) {
    if (t <= k.start) return acc;
    if (t <= k.end) return acc + (t - k.start);
    acc += k.end - k.start;
  }
  return acc;
}

export interface Cue {
  start: number;
  end: number;
  text: string;
}

export function cuesFromWords(words: TranscriptWord[]): Cue[] {
  const cues: Cue[] = [];
  let buf: TranscriptWord[] = [];
  const flush = () => {
    if (!buf.length) return;
    const text = buf
      .map((w) => w.text)
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();
    if (text) cues.push({ start: buf[0].start, end: buf[buf.length - 1].end, text });
    buf = [];
  };

  for (const w of words) {
    const prev = buf[buf.length - 1];
    const nextText = [...buf.map((b) => b.text), w.text].join(" ");
    const dur = buf.length ? w.end - buf[0].start : 0;
    const broke = prev && /[.!?]$/.test(prev.text);
    if (buf.length && (buf.length >= 6 || nextText.length > 42 || dur > 2.5 || broke)) flush();
    buf.push(w);
  }
  flush();

  for (let i = 0; i < cues.length; i++) {
    const next = cues[i + 1];
    const ceiling = next ? next.start - 0.04 : cues[i].end;
    if (cues[i].end < cues[i].start + 0.4) {
      cues[i].end = Math.min(Math.max(cues[i].end, cues[i].start + 0.4), Math.max(ceiling, cues[i].end));
    }
    if (next && cues[i].end > next.start - 0.04) {
      cues[i].end = Math.max(cues[i].start + 0.08, next.start - 0.04);
    }
  }
  return cues.filter((c) => c.text && c.end > c.start);
}

export function toSrt(cues: Cue[]): string {
  if (!cues.length) return "";
  return cues
    .map((c, i) => `${i + 1}\n${srtClock(c.start)} --> ${srtClock(c.end)}\n${c.text}\n`)
    .join("\n");
}

function srtClock(t: number): string {
  const ms = Math.max(0, Math.round(t * 1000));
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  const s = Math.floor((ms % 60_000) / 1000);
  const milli = ms % 1000;
  const p = (n: number, w = 2) => String(n).padStart(w, "0");
  return `${p(h)}:${p(m)}:${p(s)},${p(milli, 3)}`;
}

export function hexToAss(hex: string, alpha = "00"): string {
  const h = normalizeHex(hex) ?? DEFAULT_FILL;
  const r = h.slice(1, 3);
  const g = h.slice(3, 5);
  const b = h.slice(5, 7);
  return `&H${alpha}${b}${g}${r}`.toUpperCase();
}

export function captionStyleFromBrand(kit: BrandKit | null | undefined): CaptionStyle {
  const accent = normalizeHex(kit?.accentColor);
  const primary = normalizeHex(kit?.primaryColor);
  const brand = accent ?? primary;
  const requestedFont = cleanFont(kit?.displayFont) ?? cleanFont(kit?.bodyFont);

  if (!brand) {
    return {
      source: "default",
      fillHex: DEFAULT_FILL,
      outlineHex: DEFAULT_OUTLINE,
      boxHex: null,
      fontName: BUNDLED_FONT,
      requestedFont,
      fontSubstituted: Boolean(requestedFont && requestedFont.toLowerCase() !== "inter"),
      note: kit
        ? "The approved Brand Kit has no usable hex color, so captions use white text with a black outline."
        : "No approved Brand Kit yet. Captions use white text with a black outline.",
    };
  }

  const which = accent ? "accent" : "primary";
  const dark = relativeLuminance(brand) < 0.35;
  const fontSubstituted = !requestedFont || !fontFileMatches(requestedFont);
  const fontName = fontSubstituted ? BUNDLED_FONT : requestedFont!;
  const fontNote = fontSubstituted
    ? requestedFont
      ? ` Preview font is ${BUNDLED_FONT} because “${requestedFont}” is not in assets/fonts. Set ${requestedFont} on the subtitle track in Resolve.`
      : ` Preview font is ${BUNDLED_FONT}.`
    : ` Preview font is ${requestedFont}.`;

  if (dark) {
    return {
      source: "brand-kit",
      fillHex: DEFAULT_FILL,
      outlineHex: brand,
      boxHex: brand,
      fontName,
      requestedFont,
      fontSubstituted,
      note:
        `Approved Brand Kit ${which} ${brand} is dark, so the preview draws it as the caption background with white text.${fontNote}`,
    };
  }

  return {
    source: "brand-kit",
    fillHex: brand,
    outlineHex: DEFAULT_OUTLINE,
    boxHex: null,
    fontName,
    requestedFont,
    fontSubstituted,
    note: `Caption color ${brand} is the approved Brand Kit ${which}.${fontNote}`,
  };
}

export function forceStyle(style: CaptionStyle, aspect: VideoAspect): string {
  const size = aspect === "9:16" ? 42 : 28;
  const parts = [
    `Fontname=${style.fontName}`,
    "Bold=1",
    `PrimaryColour=${hexToAss(style.fillHex)}`,
    `OutlineColour=${hexToAss(style.outlineHex)}`,
    `BackColour=${hexToAss(style.boxHex ?? "#000000", style.boxHex ? "00" : "80")}`,
    `BorderStyle=${style.boxHex ? 3 : 1}`,
    `Outline=${style.boxHex ? 0 : 3}`,
    "Shadow=0",
    "Alignment=2",
    "MarginV=70",
    `Fontsize=${size}`,
  ];
  return parts.join(",");
}

export function bundledFontDir(): string {
  return join(process.cwd(), "assets", "fonts");
}

function fontFileMatches(name: string): boolean {
  const n = name.toLowerCase().replace(/[^a-z0-9]+/g, "");
  if (!n) return false;
  if (n === "inter" || n === "intersemibold") return true;
  try {
    return readdirSync(bundledFontDir()).some((file) => {
      const stem = file.toLowerCase().replace(/\.(ttf|otf)$/i, "").replace(/[^a-z0-9]+/g, "");
      if (stem.length < 4 || n.length < 4) return false;
      return stem.includes(n) || n.includes(stem);
    });
  } catch {
    return false;
  }
}

function cleanFont(name: string | undefined): string | null {
  const v = name?.trim();
  if (!v) return null;
  if (/^["'].*["']$/.test(v)) return v.slice(1, -1).trim() || null;
  return v;
}

export function normalizeHex(c: string | undefined): string | null {
  if (!c) return null;
  const v = c.trim();
  if (/^#[0-9a-fA-F]{6}$/.test(v)) return v.toUpperCase();
  if (/^#[0-9a-fA-F]{3}$/.test(v)) {
    const [r, g, b] = v.slice(1).split("");
    return `#${r}${r}${g}${g}${b}${b}`.toUpperCase();
  }
  return null;
}

function relativeLuminance(hex: string): number {
  const n = Number.parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
}

export function previewSize(aspect: VideoAspect): { width: number; height: number } {
  return aspect === "16:9" ? { width: 1280, height: 720 } : { width: 720, height: 1280 };
}

export function resolveAspect(
  requested: VideoAspect,
  width: number,
  height: number,
): { aspect: VideoAspect; note: string | null } {
  if (requested === "16:9") {
    if (width > height * 1.15) return { aspect: "16:9", note: null };
    return {
      aspect: "9:16",
      note: "Landscape was requested, but the upload is not clearly landscape, so the preview stays vertical 9:16.",
    };
  }
  return { aspect: "9:16", note: null };
}
