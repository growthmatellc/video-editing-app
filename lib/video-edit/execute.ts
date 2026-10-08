/**
 * Build one video edit from a local media file: transcript, cut list, captioned
 * proxy, and the Resolve handoff files. No database access.
 */
import { readFile, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { BrandKit } from "../slide-deck-schema";
import {
  bundledFontDir,
  captionStyleFromBrand,
  cuesFromWords,
  forceStyle,
  previewSize,
  resolveAspect,
  toSrt,
  wordsOnTimeline,
} from "./captions";
import { parseTranscript, planCuts } from "./cuts";
import { applyFeedback } from "./feedback";
import { buildEdl, buildFcpxml, buildHandoffText, EDL_REEL, handoffDropDir, safeMediaName } from "./interchange";
import { detectSilences, probeMedia, renderPreview, sourceIsLandscape } from "./media";
import { configuredProvider, transcribeFile, transcriptionMissingMessage } from "./transcribe";
import { zipStore } from "./zip";
import {
  DEFAULT_RULES,
  VIDEO_FORMATS,
  type EditRules,
  type TranscriptWord,
  type VideoAspect,
  type VideoEditMeta,
  type VideoFormat,
} from "./types";

const ZIP_SOURCE_LIMIT = 250 * 1024 * 1024;

export interface ExecutedEdit {
  preview: Buffer;
  srt: string;
  fcpxml: string;
  edl: string;
  handoffZip: Buffer;
  meta: Omit<VideoEditMeta, "source" | "outputs">;
}

export async function executeVideoEdit(input: {
  filePath: string;
  fileName: string;
  contentType?: string;
  format: VideoFormat;
  aspect: VideoAspect;
  transcriptText?: string;
  feedback?: string;
  brand?: BrandKit | null;
  clientName: string;
  /** Rules already stored from the previous run. Feedback is applied on top. */
  baseRules?: EditRules;
}): Promise<ExecutedEdit> {
  const probe = await probeMedia(input.filePath);
  const directives = applyFeedback(input.feedback, input.baseRules ?? DEFAULT_RULES);
  const format = directives.format ?? input.format;
  const aspectChoice = resolveAspect(directives.aspect ?? input.aspect, probe.width, probe.height);
  const rules = directives.rules;
  const warnings: string[] = [];
  if (aspectChoice.note) warnings.push(aspectChoice.note);
  if (directives.unused) {
    warnings.push(
      `Part of the note was not a cut instruction and was not applied: “${directives.unused}”. Recognized notes include tighter, looser, silence:0.8, keep fillers, keep retakes, vertical, and landscape.`,
    );
  }

  const pasted = parseTranscript(input.transcriptText ?? "");
  let words: TranscriptWord[] = pasted;
  let transcriptProvider: string | null = pasted.length ? "pasted" : null;

  if (!words.length) {
    if ((input.transcriptText ?? "").trim()) {
      warnings.push(
        "The pasted transcript has no timestamps, so it was not used for cuts or captions. Use start/end times per word or line, an SRT, or a WebVTT file.",
      );
    }
    if (configuredProvider()) {
      try {
        const tr = await transcribeFile({
          filePath: input.filePath,
          fileName: input.fileName,
          contentType: input.contentType || "video/mp4",
        });
        words = tr.words;
        transcriptProvider = tr.provider;
        if (!words.length) warnings.push("The transcript came back with no word times.");
      } catch (err) {
        warnings.push(
          `Transcription failed (${configuredProvider()}): ${err instanceof Error ? err.message : String(err)} Silences were still cut.`,
        );
      }
    } else {
      warnings.push(transcriptionMissingMessage());
    }
  }

  let silences: { start: number; end: number }[] = [];
  try {
    silences = await detectSilences(input.filePath, probe.duration);
  } catch (err) {
    warnings.push(`Silence detection failed: ${err instanceof Error ? err.message : String(err)}`);
  }

  const plan = planCuts({ duration: probe.duration, words, silences, rules });
  if (!plan.kept.length) {
    throw new Error(
      "Every frame was marked for removal. Reject with “looser” or “keep fillers” so more of the take stays, then run again.",
    );
  }

  const outputDuration = plan.kept.reduce((n, k) => n + (k.end - k.start), 0);
  const spec = VIDEO_FORMATS.find((f) => f.id === format);
  if (spec?.minSeconds && outputDuration < spec.minSeconds) {
    warnings.push(
      `This ${spec.label.toLowerCase()} cut is ${outputDuration.toFixed(1)}s. The target is at least ${spec.minSeconds}s.`,
    );
  }
  if (spec?.maxSeconds && outputDuration > spec.maxSeconds) {
    warnings.push(
      `This ${spec.label.toLowerCase()} cut is ${outputDuration.toFixed(1)}s. The target is ${spec.maxSeconds}s or under.`,
    );
  }

  const captions = captionStyleFromBrand(input.brand);
  const spoken = wordsOnTimeline(words, plan.kept);
  const cues = cuesFromWords(spoken);
  const srt = toSrt(cues);
  if (!cues.length) {
    warnings.push("No caption cues were written. The preview has no burned-in captions until there is a timestamped transcript.");
  }

  const fileName = safeMediaName(input.fileName);
  const dropDir = handoffDropDir();
  const fcpxml = buildFcpxml({
    clientName: input.clientName,
    fileName,
    dropDir,
    duration: probe.duration,
    width: probe.width,
    height: probe.height,
    frameRate: probe.frameRate,
    hasAudio: probe.hasAudio,
    audioChannels: probe.audioChannels,
    audioRate: probe.audioRate,
    kept: plan.kept,
  });
  const edlBuilt = buildEdl({
    title: input.clientName,
    fileName,
    frameRate: probe.frameRate,
    timecode: probe.timecode,
    kept: plan.kept,
  });
  if (edlBuilt.note) warnings.push(edlBuilt.note);

  const size = previewSize(aspectChoice.aspect);
  const dir = await mkdtemp(join(tmpdir(), "video-edit-"));
  try {
    const srtPath = cues.length ? join(dir, "captions.srt") : null;
    if (srtPath) await writeFile(srtPath, srt, "utf8");
    const previewPath = join(dir, "preview.mp4");
    await renderPreview({
      filePath: input.filePath,
      outPath: previewPath,
      kept: plan.kept,
      hasAudio: probe.hasAudio,
      width: size.width,
      height: size.height,
      srtPath,
      fontDir: bundledFontDir(),
      forceStyle: forceStyle(captions, aspectChoice.aspect),
    });
    const preview = await readFile(previewPath);
    const sourceBytes = await readFile(input.filePath);
    const sourceIncluded = sourceBytes.length <= ZIP_SOURCE_LIMIT;
    if (!sourceIncluded) {
      warnings.push(
        `The source is over 250MB, so it was left out of the handoff zip. Download it separately and save it as ${fileName} in the drop folder.`,
      );
    }

    const handoffMeta = {
      format,
      aspect: aspectChoice.aspect,
      removed: plan.removed,
      captions,
      handoff: { dropDir, sourceFileName: fileName, reel: EDL_REEL },
      warnings,
      outputDuration,
    };
    const handoffTxt = buildHandoffText({ ...handoffMeta, clientName: input.clientName, sourceIncluded });
    const zipEntries = [
      { name: "HANDOFF.txt", data: Buffer.from(handoffTxt, "utf8") },
      { name: "edit.fcpxml", data: Buffer.from(fcpxml, "utf8") },
      { name: "edit.edl", data: Buffer.from(edlBuilt.edl, "utf8") },
      { name: "captions.srt", data: Buffer.from(srt, "utf8") },
    ];
    if (sourceIncluded) zipEntries.push({ name: fileName, data: sourceBytes });
    const handoffZip = zipStore(zipEntries);

    return {
      preview,
      srt,
      fcpxml,
      edl: edlBuilt.edl,
      handoffZip,
      meta: {
        format,
        aspect: aspectChoice.aspect,
        transcriptText: input.transcriptText ?? "",
        transcriptProvider,
        words,
        rules,
        removed: plan.removed,
        kept: plan.kept,
        captions,
        warnings,
        feedbackApplied: directives.applied,
        outputDuration,
        handoff: { dropDir, sourceFileName: fileName, reel: EDL_REEL },
      },
    };
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

export function landscapeOf(width: number, height: number): boolean {
  return sourceIsLandscape(width, height);
}
