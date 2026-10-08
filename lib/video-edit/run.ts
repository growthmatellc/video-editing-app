/**
 * Stage entry for Video Edit. Special-cased like Brand Kit and Webinar Slides:
 * the deliverable is media plus a Resolve handoff, not a prose generation.
 * The copywriting auditor is not involved — captions are the transcript.
 */
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createWriteStream } from "node:fs";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import type { Stage } from "../db/schema";
import { archiveRevision, saveStageOutput, type ProjectWithStages } from "../project-store";
import { putFile } from "../storage";
import type { BrandKit } from "../slide-deck-schema";
import { executeVideoEdit } from "./execute";
import { renderSummary } from "./summary";
import {
  DEFAULT_RULES,
  readVideoEditMeta,
  type VideoEditMeta,
  type VideoEditRequest,
} from "./types";

export async function runVideoEdit(
  data: ProjectWithStages,
  stageRow: Stage,
  feedback: string | undefined,
  operatorId: string | null | undefined,
  request?: VideoEditRequest,
) {
  const stored = readVideoEditMeta(stageRow.outputMeta);
  if (!stored?.source?.url) {
    throw new Error("Upload an mp4 or mov on the Video Edit stage before running it.");
  }

  const brandStage = data.stages.find((s) => s.stageKey === "brand-kit" && s.status === "approved");
  const brand = (brandStage?.outputMeta as { brandKit?: BrandKit } | null)?.brandKit ?? null;

  const dir = await mkdtemp(join(tmpdir(), "video-edit-src-"));
  const localName = stored.source.fileName || "source.mp4";
  const localPath = join(dir, localName);
  try {
    await materialize(stored.source.url, localPath);
    const executed = await executeVideoEdit({
      filePath: localPath,
      fileName: localName,
      contentType: stored.source.contentType,
      format: request?.format ?? stored.format ?? "talking-head",
      aspect: request?.aspect ?? stored.aspect ?? "9:16",
      transcriptText: request?.transcriptText ?? stored.transcriptText ?? "",
      feedback,
      brand,
      clientName: data.project.clientName,
      baseRules: stored.rules ?? DEFAULT_RULES,
    });

    const stamp = Date.now();
    const base = `video-edit/${data.project.id}/${stamp}`;
    const [preview, srtFile, xmlFile, edlFile, zipFile] = await Promise.all([
      putFile(`${base}-preview.mp4`, executed.preview, "video/mp4"),
      putFile(`${base}-captions.srt`, Buffer.from(executed.srt, "utf8"), "application/x-subrip"),
      putFile(`${base}-edit.fcpxml`, Buffer.from(executed.fcpxml, "utf8"), "application/xml"),
      putFile(`${base}-edit.edl`, Buffer.from(executed.edl, "utf8"), "text/plain"),
      putFile(`${base}-handoff.zip`, executed.handoffZip, "application/zip"),
    ]);

    const meta: VideoEditMeta = {
      ...executed.meta,
      source: {
        ...stored.source,
        fileName: executed.meta.handoff.sourceFileName,
      },
      outputs: {
        previewUrl: preview.url,
        srtUrl: srtFile.url,
        fcpxmlUrl: xmlFile.url,
        edlUrl: edlFile.url,
        handoffZipUrl: zipFile.url,
      },
    };
    const outputMd = renderSummary(meta, data.project.clientName);
    const outputMeta = { videoEdit: meta };

    await archiveRevision(stageRow, feedback ?? null, operatorId ?? null);
    await saveStageOutput(stageRow.id, {
      status: "draft",
      outputMd,
      outputMeta,
      draftMd: stageRow.draftMd ?? outputMd,
      scoreJson: null,
      auditJson: null,
      gatePassed: false,
      gateAttempts: 0,
    });

    return {
      ok: true,
      stageKey: "video-edit" as const,
      status: "draft" as const,
      outputMd,
      outputMeta: outputMeta as Record<string, unknown>,
      score: null,
      audit: null,
    };
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

async function materialize(url: string, dest: string): Promise<void> {
  if (url.startsWith("/generated/")) {
    const src = join(process.cwd(), "public", url.replace(/^\/+/, ""));
    const { copyFile } = await import("node:fs/promises");
    await copyFile(src, dest);
    return;
  }
  if (url.startsWith("http://") || url.startsWith("https://")) {
    const res = await fetch(url);
    if (!res.ok || !res.body) {
      throw new Error(`Could not download the uploaded video (${res.status}). Upload it again.`);
    }
    const nodeStream = Readable.fromWeb(res.body as import("stream/web").ReadableStream);
    await pipeline(nodeStream, createWriteStream(dest));
    return;
  }
  throw new Error("The uploaded video URL is not a file this server can read. Upload it again.");
}

/** Used by the project page to tell the operator whether a transcript key exists. */
export function videoEditEnv(): { transcriptionConfigured: boolean; blobUploadEnabled: boolean } {
  const choice = (process.env.TRANSCRIPTION_PROVIDER ?? "auto").trim().toLowerCase();
  const has = {
    deepgram: Boolean(process.env.DEEPGRAM_API_KEY),
    assemblyai: Boolean(process.env.ASSEMBLYAI_API_KEY),
    openai: Boolean(process.env.OPENAI_API_KEY),
  };
  const transcriptionConfigured =
    choice === "deepgram"
      ? has.deepgram
      : choice === "assemblyai"
        ? has.assemblyai
        : choice === "openai"
          ? has.openai
          : has.deepgram || has.assemblyai || has.openai;
  return {
    transcriptionConfigured,
    blobUploadEnabled: Boolean(process.env.BLOB_READ_WRITE_TOKEN),
  };
}
