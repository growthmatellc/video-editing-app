import { NextResponse } from "next/server";
import { listRevisions } from "@/lib/project-store";

export const runtime = "nodejs";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string; stageKey: string }> },
) {
  const { id, stageKey } = await params;
  const revisions = await listRevisions(`${id}-${stageKey}`);
  return NextResponse.json({ revisions });
}
