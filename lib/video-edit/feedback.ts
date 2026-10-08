/**
 * Turn a reject/re-run note into cut rules. Only phrases listed here change the
 * edit. Anything else is returned unused so the UI can say it was not applied.
 */
import type { EditRules, VideoAspect, VideoFormat } from "./types";
import { DEFAULT_RULES } from "./types";

export interface FeedbackDirectives {
  rules: EditRules;
  format?: VideoFormat;
  aspect?: VideoAspect;
  applied: string[];
  unused: string | null;
}

export function applyFeedback(
  feedback: string | undefined,
  base: EditRules = DEFAULT_RULES,
): FeedbackDirectives {
  const rules: EditRules = { ...base };
  const applied: string[] = [];
  let unused = (feedback ?? "").trim();
  let format: VideoFormat | undefined;
  let aspect: VideoAspect | undefined;

  const take = (re: RegExp): string | null => {
    const m = unused.match(re);
    if (!m || m.index === undefined) return null;
    unused = `${unused.slice(0, m.index)} ${unused.slice(m.index + m[0].length)}`
      .replace(/\s+/g, " ")
      .trim();
    return m[0];
  };

  if (
    take(/\b(?:keep|don'?t|do not)\s+(?:cut\s+)?(?:the\s+)?(?:fillers?|ums?|uhs?)\b/i) ||
    take(/\b(?:don'?t|do not)\s+remove\s+(?:the\s+)?(?:fillers?|ums?|uhs?)\b/i)
  ) {
    rules.cutFillers = false;
    applied.push("Keeping filler words.");
  } else if (take(/\b(?:cut|remove|drop)\s+(?:the\s+)?fillers?\b/i)) {
    rules.cutFillers = true;
    applied.push("Cutting filler words.");
  }

  if (
    take(/\b(?:keep|don'?t|do not)\s+(?:cut\s+)?(?:the\s+)?retakes?\b/i) ||
    take(/\b(?:don'?t|do not)\s+remove\s+(?:the\s+)?retakes?\b/i)
  ) {
    rules.cutRetakes = false;
    applied.push("Keeping retakes.");
  } else if (take(/\b(?:cut|remove|drop)\s+(?:the\s+)?retakes?\b/i)) {
    rules.cutRetakes = true;
    applied.push("Cutting repeated takes.");
  }

  const silence = take(/\bsilence\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:s|sec|seconds)?\b/i);
  if (silence) {
    const n = Number(silence.match(/(\d+(?:\.\d+)?)/)?.[1]);
    if (n >= 0.15 && n <= 3) {
      rules.silenceSeconds = Math.round(n * 100) / 100;
      applied.push(`Silence threshold set to ${rules.silenceSeconds.toFixed(2)}s.`);
    }
  } else if (take(/\b(?:tighter|more aggressive|cut more silence)\b/i)) {
    rules.silenceSeconds = 0.35;
    applied.push("Tighter silences (0.35s).");
  } else if (take(/\b(?:looser|less aggressive|keep (?:the )?pauses)\b/i)) {
    rules.silenceSeconds = 1;
    applied.push("Looser silences (1.00s).");
  }

  if (take(/\b(?:landscape|16:9|16x9)\b/i)) {
    aspect = "16:9";
    applied.push("Landscape requested.");
  }
  if (take(/\b(?:vertical|portrait|9:16|9x16)\b/i)) {
    aspect = "9:16";
    applied.push("Vertical 9:16.");
  }
  if (take(/\bshort[-\s]?form(?:\s+ads?)?\b/i)) {
    format = "short-form-ad";
    applied.push("Format set to short-form ad.");
  }
  if (take(/\bfunnel(?:\s+videos?)?\b/i)) {
    format = "funnel-video";
    applied.push("Format set to funnel video.");
  }
  if (take(/\btalking[-\s]?head\b/i)) {
    format = "talking-head";
    applied.push("Format set to talking-head.");
  }

  unused = unused.replace(/^[\s,.;:-]+|[\s,.;:-]+$/g, "").trim();
  return { rules, format, aspect, applied, unused: unused.length ? unused : null };
}
