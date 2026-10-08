import { NextResponse } from "next/server";
import { handleUpload, type HandleUploadBody } from "@vercel/blob/client";

export const runtime = "nodejs";

/**
 * Token endpoint for browser uploads straight to Vercel Blob.
 * Needed because Vercel request bodies are capped around 4.5MB and raw footage is larger.
 * Local dev without BLOB_READ_WRITE_TOKEN uploads through the stage source route instead.
 */
export async function POST(req: Request) {
  if (!process.env.BLOB_READ_WRITE_TOKEN) {
    return NextResponse.json(
      { error: "BLOB_READ_WRITE_TOKEN is not set, so direct uploads are unavailable." },
      { status: 400 },
    );
  }
  let body: HandleUploadBody;
  try {
    body = (await req.json()) as HandleUploadBody;
  } catch {
    return NextResponse.json({ error: "Expected an upload token request." }, { status: 400 });
  }
  try {
    const json = await handleUpload({
      body,
      request: req,
      onBeforeGenerateToken: async (pathname) => {
        if (!/\.(mp4|mov)$/i.test(pathname)) {
          throw new Error("Upload an .mp4 or .mov file.");
        }
        return {
          allowedContentTypes: ["video/mp4", "video/quicktime", "application/octet-stream"],
          maximumSizeInBytes: 500 * 1024 * 1024,
          addRandomSuffix: true,
        };
      },
    });
    return NextResponse.json(json);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : String(err) },
      { status: 400 },
    );
  }
}
