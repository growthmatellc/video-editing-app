/**
 * Deterministic cut planner. Given word times and silence ranges, decide which
 * source ranges to drop. The same inputs always produce the same cut list —
 * nothing here calls a model.
 */
import type { CutReason, EditRules, Removal, TimeRange, TranscriptWord } from "./types";

/** Single-word fillers. Matched after stripping punctuation. */
export const ALWAYS_FILLERS = new Set([
  "um",
  "uh",
  "uhh",
  "umm",
  "er",
  "err",
  "ah",
  "ahh",
  "eh",
  "hmm",
  "hm",
  "mm",
  "mmm",
  "erm",
  "uhm",
  "mhm",
  "mhmm",
]);

/** Contiguous phrases removed only when they sit together with no real gap. */
export const PHRASE_FILLERS: string[][] = [
  ["you", "know"],
  ["i", "mean"],
  ["sort", "of"],
  ["kind", "of"],
];

const MIN_KEEP = 0.12;
const RETAKE_WINDOW_SECONDS = 8;
const UTTERANCE_GAP = 0.45;

export function normalizeToken(text: string): string {
  return text
    .toLowerCase()
    .replace(/[’]/g, "'")
    .replace(/[^a-z0-9'-]+/g, "")
    .replace(/^'+|'+$/g, "");
}

export interface CutPlan {
  removed: Removal[];
  kept: TimeRange[];
}

export function planCuts(opts: {
  duration: number;
  words: TranscriptWord[];
  silences: TimeRange[];
  rules: EditRules;
}): CutPlan {
  const duration = Math.max(0, opts.duration);
  if (duration <= 0) return { removed: [], kept: [] };

  const words = opts.words
    .filter((w) => Number.isFinite(w.start) && Number.isFinite(w.end) && w.end > w.start)
    .map((w) => ({
      text: w.text.trim(),
      start: clamp(w.start, 0, duration),
      end: clamp(w.end, 0, duration),
    }))
    .filter((w) => w.text && w.end > w.start)
    .sort((a, b) => a.start - b.start);

  const removals: Removal[] = [
    ...silenceRemovals(words, opts.silences, duration, opts.rules),
  ];
  if (opts.rules.cutFillers) removals.push(...fillerRemovals(words));
  if (opts.rules.cutStutters) removals.push(...stutterRemovals(words));
  if (opts.rules.cutRetakes) removals.push(...retakeRemovals(words));

  const merged = mergeRemovals(removals);
  let kept = invert(merged, duration).filter((k) => k.end - k.start >= MIN_KEEP);
  if (kept.length === 0) {
    // Everything was marked. Hand back one empty plan so the caller can explain
    // it instead of rendering a zero-length file.
    return { removed: merged.length ? decorateAll(merged, duration) : [], kept: [] };
  }
  const removed = invert(kept, duration)
    .map((r) => decorate(r, merged))
    .filter((r) => r.end - r.start >= 0.04);
  // Re-invert so the kept list lines up with the ranges we actually report.
  kept = invert(removed, duration);
  return { removed, kept };
}

export function rulesBlurb(rules: EditRules): string {
  const parts = [
    `Silences longer than ${rules.silenceSeconds.toFixed(2)}s are removed, leaving ${rules.padSeconds.toFixed(2)}s of pad on interior gaps so words are not clipped.`,
  ];
  parts.push(
    rules.cutFillers
      ? "Filler words are removed: um/uh/er/ah/hmm, the phrases “you know”, “i mean”, “sort of”, and “kind of”, plus “like” and “so” only when they sit between pauses."
      : "Filler words are kept.",
  );
  parts.push(
    rules.cutRetakes
      ? "An earlier take is removed when the next phrase repeats it within 8 seconds (the later take is kept)."
      : "Retakes are kept.",
  );
  parts.push(
    rules.cutStutters ? "An immediate repeated word (a stutter) drops the first copy." : "Stutters are kept.",
  );
  return parts.join(" ");
}

function silenceRemovals(
  words: TranscriptWord[],
  silences: TimeRange[],
  duration: number,
  rules: EditRules,
): Removal[] {
  const raw: TimeRange[] = [];
  if (words.length) {
    if (words[0].start > 0) raw.push({ start: 0, end: words[0].start });
    for (let i = 0; i < words.length - 1; i++) {
      raw.push({ start: words[i].end, end: words[i + 1].start });
    }
    const last = words[words.length - 1];
    if (last.end < duration) raw.push({ start: last.end, end: duration });
  }
  for (const s of silences) {
    const start = clamp(s.start, 0, duration);
    const end = clamp(s.end, 0, duration);
    if (end > start) raw.push({ start, end });
  }

  const out: Removal[] = [];
  for (const gap of raw) {
    if (gap.end - gap.start <= rules.silenceSeconds) continue;
    const leading = gap.start <= 0.02;
    const trailing = gap.end >= duration - 0.02;
    const start = gap.start + (leading ? 0 : rules.padSeconds);
    const end = gap.end - (trailing ? 0 : rules.padSeconds);
    if (end - start < 0.05) continue;

    let pieces: TimeRange[] = [{ start, end }];
    for (const w of words) {
      // Filler words are removed on their own pass. A silence may cover them.
      if (rules.cutFillers && isAlwaysFiller(w.text)) continue;
      pieces = pieces.flatMap((p) => subtract(p, { start: w.start, end: w.end }));
    }
    for (const p of pieces) {
      if (p.end - p.start < 0.05) continue;
      out.push({ ...p, reasons: ["silence"], detail: "dead air" });
    }
  }
  return out;
}

function fillerRemovals(words: TranscriptWord[]): Removal[] {
  const out: Removal[] = [];
  const used = new Set<number>();

  for (const phrase of PHRASE_FILLERS) {
    for (let i = 0; i <= words.length - phrase.length; i++) {
      if (phrase.some((_, k) => used.has(i + k))) continue;
      const slice = words.slice(i, i + phrase.length);
      if (!contiguous(slice)) continue;
      if (!slice.every((w, k) => normalizeToken(w.text) === phrase[k])) continue;
      slice.forEach((_, k) => used.add(i + k));
      out.push(span(slice, "filler", phrase.join(" ")));
    }
  }

  for (let i = 0; i < words.length; i++) {
    if (used.has(i)) continue;
    const token = normalizeToken(words[i].text);
    if (!token) continue;
    if (ALWAYS_FILLERS.has(token) || token === "uh-huh" || token === "mm-hmm") {
      used.add(i);
      out.push(span([words[i]], "filler", token));
      continue;
    }
    if ((token === "like" || token === "so") && isolated(words, i)) {
      used.add(i);
      out.push(span([words[i]], "filler", `${token} (between pauses)`));
    }
  }
  return out;
}

function isolated(words: TranscriptWord[], i: number): boolean {
  const prev = words[i - 1];
  const next = words[i + 1];
  const gapBefore = prev ? words[i].start - prev.end : Number.POSITIVE_INFINITY;
  const gapAfter = next ? next.start - words[i].end : Number.POSITIVE_INFINITY;
  const beforeOk = !prev || gapBefore >= 0.2 || isAlwaysFiller(prev.text);
  const afterOk = !next || gapAfter >= 0.2 || isAlwaysFiller(next.text);
  return beforeOk && afterOk;
}

function stutterRemovals(words: TranscriptWord[]): Removal[] {
  const out: Removal[] = [];
  for (let i = 0; i < words.length - 1; i++) {
    const a = normalizeToken(words[i].text);
    const b = normalizeToken(words[i + 1].text);
    if (!a || a !== b) continue;
    if (words[i + 1].start - words[i].end > 0.6) continue;
    out.push(span([words[i]], "stutter", `repeated “${a}”`));
  }
  return out;
}

interface Utterance {
  words: TranscriptWord[];
  start: number;
  end: number;
  tokens: string[];
}

function retakeRemovals(words: TranscriptWord[]): Removal[] {
  const groups: TranscriptWord[][] = [];
  let cur: TranscriptWord[] = [];
  for (const w of words) {
    const prev = cur[cur.length - 1];
    const gap = prev ? w.start - prev.end : 0;
    if (prev && (gap > UTTERANCE_GAP || /[.!?]["']?$/.test(prev.text))) {
      groups.push(cur);
      cur = [];
    }
    cur.push(w);
  }
  if (cur.length) groups.push(cur);

  const utterances: Utterance[] = groups.map((ws) => ({
    words: ws,
    start: ws[0].start,
    end: ws[ws.length - 1].end,
    tokens: ws
      .map((w) => normalizeToken(w.text))
      .filter((t) => t && !ALWAYS_FILLERS.has(t) && t !== "like" && t !== "so"),
  }));

  const drop = new Set<number>();
  for (let i = 0; i < utterances.length; i++) {
    if (drop.has(i)) continue;
    for (let j = i + 1; j < utterances.length && j <= i + 3; j++) {
      if (utterances[j].start - utterances[i].end > RETAKE_WINDOW_SECONDS) break;
      if (!isRetake(utterances[i].tokens, utterances[j].tokens)) continue;
      drop.add(i);
      break;
    }
  }

  return [...drop].map((i) => {
    const u = utterances[i];
    const preview = u.words
      .map((w) => w.text)
      .join(" ")
      .slice(0, 80);
    return span(u.words, "retake", `earlier take “${preview}”`);
  });
}

function isRetake(earlier: string[], later: string[]): boolean {
  if (earlier.length < 4 || later.length < 4) return false;
  const contained = containedInOrder(earlier, later);
  if (contained >= 0.85) return true;
  const a = new Set(earlier);
  const b = new Set(later);
  let inter = 0;
  for (const t of a) if (b.has(t)) inter++;
  const jaccard = inter / (a.size + b.size - inter);
  return jaccard >= 0.8;
}

function containedInOrder(needle: string[], hay: string[]): number {
  let i = 0;
  for (const t of hay) {
    if (t === needle[i]) i++;
    if (i === needle.length) break;
  }
  return i / needle.length;
}

function isAlwaysFiller(text: string): boolean {
  const token = normalizeToken(text);
  return ALWAYS_FILLERS.has(token) || token === "uh-huh" || token === "mm-hmm";
}

function contiguous(words: TranscriptWord[]): boolean {
  for (let i = 1; i < words.length; i++) {
    if (words[i].start - words[i - 1].end > 0.35) return false;
  }
  return true;
}

function span(words: TranscriptWord[], reason: CutReason, detail: string): Removal {
  return {
    start: words[0].start,
    end: words[words.length - 1].end,
    reasons: [reason],
    detail,
  };
}

function subtract(range: TimeRange, cut: TimeRange): TimeRange[] {
  if (cut.end <= range.start || cut.start >= range.end) return [range];
  const out: TimeRange[] = [];
  if (cut.start > range.start + 0.01) {
    out.push({ start: range.start, end: Math.min(cut.start, range.end) });
  }
  if (cut.end < range.end - 0.01) {
    out.push({ start: Math.max(cut.end, range.start), end: range.end });
  }
  return out.filter((r) => r.end - r.start > 0.01);
}

function mergeRemovals(ranges: Removal[]): Removal[] {
  const sorted = [...ranges]
    .filter((r) => r.end - r.start > 0.02)
    .sort((a, b) => a.start - b.start || a.end - b.end);
  const out: Removal[] = [];
  for (const r of sorted) {
    const last = out[out.length - 1];
    if (last && r.start <= last.end + 0.03) {
      last.end = Math.max(last.end, r.end);
      last.reasons = unique([...last.reasons, ...r.reasons]);
      if (r.detail && !last.detail.includes(r.detail)) {
        last.detail = `${last.detail}; ${r.detail}`.slice(0, 180);
      }
    } else {
      out.push({ ...r, reasons: [...r.reasons] });
    }
  }
  return out;
}

function invert(removed: TimeRange[], duration: number): TimeRange[] {
  const sorted = [...removed].sort((a, b) => a.start - b.start);
  const kept: TimeRange[] = [];
  let cursor = 0;
  for (const r of sorted) {
    const start = clamp(r.start, 0, duration);
    const end = clamp(r.end, 0, duration);
    if (start > cursor + 0.001) kept.push({ start: cursor, end: start });
    cursor = Math.max(cursor, end);
  }
  if (duration - cursor > 0.001) kept.push({ start: cursor, end: duration });
  return kept;
}

function decorate(range: TimeRange, source: Removal[]): Removal {
  const hits = source.filter((s) => s.end > range.start + 0.01 && s.start < range.end - 0.01);
  const reasons = unique(hits.flatMap((h) => h.reasons));
  const detail = hits
    .map((h) => h.detail)
    .filter(Boolean)
    .filter((d, i, arr) => arr.indexOf(d) === i)
    .slice(0, 3)
    .join("; ")
    .slice(0, 180);
  return {
    start: round3(range.start),
    end: round3(range.end),
    reasons: reasons.length ? reasons : ["silence"],
    detail: detail || "removed",
  };
}

function decorateAll(merged: Removal[], duration: number): Removal[] {
  return [
    {
      start: 0,
      end: round3(duration),
      reasons: unique(merged.flatMap((m) => m.reasons)),
      detail: "every range was removed",
    },
  ];
}

function unique<T>(items: T[]): T[] {
  return [...new Set(items)];
}

function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n));
}

function round3(n: number): number {
  return Math.round(n * 1000) / 1000;
}

/** Parse an operator-pasted transcript. Plain prose without times returns []. */
export function parseTranscript(text: string): TranscriptWord[] {
  const raw = text.replace(/\r/g, "").trim();
  if (!raw) return [];
  if (raw.includes("-->")) return parseCues(raw);
  const timed: TranscriptWord[] = [];
  let sawUntimed = false;
  for (const line of raw.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || /^WEBVTT\b/.test(trimmed) || /^\d+$/.test(trimmed)) continue;
    const bracket = trimmed.match(
      /^\[?(\d+(?:\.\d+)?)(?:s)?\s*[-–—]\s*(\d+(?:\.\d+)?)(?:s)?\]?\s+(.+)$/,
    );
    const pair = trimmed.match(/^(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(.+)$/);
    const hit = bracket || pair;
    if (!hit) {
      sawUntimed = true;
      continue;
    }
    const start = Number(hit[1]);
    const end = Number(hit[2]);
    if (end > start) timed.push({ start, end, text: hit[3].trim() });
  }
  if (timed.length) return timed.flatMap(splitPhrase);
  if (sawUntimed) return [];
  return [];
}

function parseCues(text: string): TranscriptWord[] {
  const blocks = text.split(/\n\s*\n/);
  const cues: { start: number; end: number; text: string }[] = [];
  for (const block of blocks) {
    const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
    const timingIdx = lines.findIndex((l) => l.includes("-->"));
    if (timingIdx < 0) continue;
    const [a, b] = lines[timingIdx].split("-->");
    const start = parseClock(a);
    const end = parseClock(b);
    const cueText = lines
      .slice(timingIdx + 1)
      .join(" ")
      .replace(/<[^>]+>/g, "")
      .trim();
    if (cueText && end > start) cues.push({ start, end, text: cueText });
  }
  return cues.flatMap(splitPhrase);
}

function parseClock(raw: string): number {
  const s = raw.trim().split(/\s/)[0].replace(",", ".");
  const hms = s.match(/^(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)$/);
  if (!hms) {
    const n = Number(s);
    return Number.isFinite(n) ? n : 0;
  }
  const hours = hms[1] ? Number(hms[1]) : 0;
  return hours * 3600 + Number(hms[2]) * 60 + Number(hms[3]);
}

function splitPhrase(c: { start: number; end: number; text: string }): TranscriptWord[] {
  const parts = c.text.split(/\s+/).filter(Boolean);
  if (!parts.length) return [];
  const dur = c.end - c.start;
  return parts.map((text, i) => ({
    text,
    start: c.start + (dur * i) / parts.length,
    end: c.start + (dur * (i + 1)) / parts.length,
  }));
}
