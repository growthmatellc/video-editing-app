/**
 * Storage wrapper for generated artifacts (.pptx decks, etc).
 *
 * Default provider: Vercel Blob. Swap the body of putFile() to use any
 * S3-compatible bucket — nothing else in the app imports the provider directly.
 *
 * If BLOB_READ_WRITE_TOKEN is unset, falls back to writing into /public so local
 * dev still produces a downloadable file without a cloud account.
 */
import { put } from "@vercel/blob";
import { writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";

export async function putFile(
  pathname: string,
  data: Buffer | Uint8Array,
  contentType: string,
): Promise<{ url: string }> {
  const token = process.env.BLOB_READ_WRITE_TOKEN;

  if (token) {
    const blob = await put(pathname, Buffer.from(data), {
      access: "public",
      contentType,
      token,
      addRandomSuffix: true,
    });
    return { url: blob.url };
  }

  // Local fallback: write under public/generated and serve from the app origin.
  const safeName = pathname.replace(/[^a-zA-Z0-9._/-]/g, "_");
  const dir = join(process.cwd(), "public", "generated");
  await mkdir(dir, { recursive: true });
  const fileName = safeName.split("/").pop() || "file";
  const stamped = `${Date.now()}-${fileName}`;
  await writeFile(join(dir, stamped), Buffer.from(data));
  return { url: `/generated/${stamped}` };
}
