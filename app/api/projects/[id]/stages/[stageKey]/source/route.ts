import { NextResponse } from "next/server";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { getOperatorId } from "@/lib/auth";
import { archiveRevision, ensureStage, getProject, getStage, saveStageOutput } from "@/lib/project-store";
import { STAGE_BY_KEY } from "@/lib/pipeline";
import { putFile } from "@/lib/storage";
import { captionStyleFromBrand } from "@/lib/video-edit/captions";
import { EDL_REEL, handoffDropDir, safeMediaName } from "@/lib/video-edit/interchange";
import { probeMedia, sourceIsLandscape } from "@/lib/video-edit/media";
import {
  DEFAULT_RULES,
  readVideoEditMeta,
  type VideoEditMeta,
  type VideoSourceMeta,
} from "@/lib/video-edit/types";

export const runtime = "nodejs";
export const maxDuration = 60;

const MAX_BYTES = 500 * 1024 * 1024;

/**
 * Attach raw footage to the Video Edit stage. Does not render.
 * Multipart for local dev. JSON { url, fileName } after a Vercel Blob client upload.
 */
export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string; stageKey: string }> },
) {
  const { id, stageKey } = await params;
  if (stageKey !== "video-edit") {
    return NextResponse.json({ error: "Footage upload is only for the Video Edit stage." }, { status: 404 });
  }
  const data = await getProject(id);
  if (!data) return NextResponse.json({ error: "Project not found" }, { status: 404 });

  const incoming = await readIncoming(req);
  if (!incoming.ok) return NextResponse.json({ error: incoming.error }, { status: 400 });

  const fileName = safeMediaName(incoming.fileName);
  let url = incoming.url;
  if (incoming.bytes) {
    const stored = await putFile(`video-edit/${id}/${fileName}`, incoming.bytes, incoming.contentType);
    url = stored.url;
  }
  if (!url) return NextResponse.json({ error: "Upload did not produce a file URL." }, { status: 400 });

  const probed = await probeUrl(url, incoming.bytes, fileName);
  const source: VideoSourceMeta = {
    url,
    fileName,
    contentType: incoming.contentType,
    bytes: incoming.bytes?.length ?? incoming.size ?? 0,
    width: probed?.width ?? null,
    height: probed?.height ?? null,
    duration: probed?.duration ?? null,
    landscape: probed ? sourceIsLandscape(probed.width, probed.height) : false,
  };

  const def = STAGE_BY_KEY["video-edit"];
  const stage = (await getStage(id, "video-edit")) ?? (await ensureStage(id, def));
  const prev = readVideoEditMeta(stage.outputMeta);
  const operatorId = await getOperatorId();
  if (stage.outputMd) await archiveRevision(stage, "Replaced source footage", operatorId);

  const videoEdit: VideoEditMeta = {
    format: prev?.format ?? "talking-head",
    aspect: "9:16",
    source,
    transcriptText: prev?.transcriptText ?? "",
    transcriptProvider: null,
    words: [],
    rules: prev?.rules ?? DEFAULT_RULES,
    removed: [],
    kept: [],
    captions: captionStyleFromBrand(null),
    outputs: null,
    warnings: probed
      ? []
      : ["Could not read duration or frame size yet. Running the stage will try again."],
    feedbackApplied: [],
    outputDuration: null,
    handoff: { dropDir: handoffDropDir(), sourceFileName: fileName, reel: EDL_REEL },
  };

  const outputMeta = { videoEdit };
  await saveStageOutput(stage.id, {
    status: "not_started",
    outputMd: null,
    outputMeta,
    scoreJson: null,
    auditJson: null,
    gatePassed: false,
    gateAttempts: 0,
    approvedAt: null,
  });

  return NextResponse.json({ ok: true, outputMeta });
}

async function readIncoming(req: Request): Promise<
  | { ok: true; fileName: string; contentType: string; bytes: Buffer | null; url: string | null; size: number | null }
  | { ok: false; error: string }
> {
  const contentType = req.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    let body: { url?: unknown; fileName?: unknown; contentType?: unknown; size?: unknown };
    try {
      body = await req.json();
    } catch {
      return { ok: false, error: "Expected a JSON body." };
    }
    if (typeof body.fileName !== "string" || !/\.(mp4|mov)$/i.test(body.fileName)) {
      return { ok: false, error: "Upload an .mp4 or .mov file." };
    }
    if (typeof body.url !== "string" || !/^https?:\/\//i.test(body.url)) {
      return { ok: false, error: "The uploaded file URL is missing." };
    }
    const size = typeof body.size === "number" ? body.size : null;
    if (size !== null && size > MAX_BYTES) return { ok: false, error: "That file is over 500MB." };
    return {
      ok: true,
      fileName: body.fileName,
      contentType: typeof body.contentType === "string" && body.contentType ? body.contentType : mimeFor(body.fileName),
      bytes: null,
      url: body.url,
      size,
    };
  }

  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return { ok: false, error: "Could not read the upload. For files over a few megabytes on Vercel, set BLOB_READ_WRITE_TOKEN." };
  }
  const file = form.get("file");
  if (!(file instanceof File)) return { ok: false, error: "Choose an mp4 or mov file." };
  if (!/\.(mp4|mov)$/i.test(file.name)) return { ok: false, error: "Upload an .mp4 or .mov file." };
  if (file.size > MAX_BYTES) return { ok: false, error: "That file is over 500MB." };
  if (file.size === 0) return { ok: false, error: "That file is empty." };
  return {
    ok: true,
    fileName: file.name,
    contentType: file.type || mimeFor(file.name),
    bytes: Buffer.from(await file.arrayBuffer()),
    url: null,
    size: file.size,
  };
}

function mimeFor(name: string): string {
  return name.toLowerCase().endsWith(".mov") ? "video/quicktime" : "video/mp4";
}

async function probeUrl(
  url: string,
  bytes: Buffer | null,
  fileName: string,
): Promise<{ width: number; height: number; duration: number } | null> {
  const dir = await mkdtemp(join(tmpdir(), "video-edit-probe-"));
  const dest = join(dir, fileName);
  try {
    if (bytes) {
      await writeFile(dest, bytes);
    } else {
      const res = await fetch(url);
      if (!res.ok) return null;
      await writeFile(dest, Buffer.from(await res.arrayBuffer()));
    }
    const probe = await probeMedia(dest);
    return { width: probe.width, height: probe.height, duration: probe.duration };
  } catch {
    return null;
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}
