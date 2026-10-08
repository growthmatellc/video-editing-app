import { NextResponse } from "next/server";
import { runStage } from "@/lib/skill-executor";
import { getOperatorId } from "@/lib/auth";
import { parseVideoEditRequest } from "@/lib/video-edit/types";

export const runtime = "nodejs";
// Heavy sequence stages (full email/call sequences) can run several minutes on a
// cold cache with a gate retry. Pro + Fluid Compute honors up to 800s.
export const maxDuration = 800;

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string; stageKey: string }> },
) {
  const { id, stageKey } = await params;
  let feedback: string | undefined;
  let videoEdit: ReturnType<typeof parseVideoEditRequest>;
  try {
    const body = await req.json();
    feedback = typeof body?.feedback === "string" ? body.feedback : undefined;
    videoEdit = parseVideoEditRequest(body?.videoEdit);
  } catch {
    // no body is fine
  }

  const operatorId = await getOperatorId();
  try {
    const result = await runStage(id, stageKey, feedback, operatorId, { videoEdit });
    return NextResponse.json(result, { status: result.ok ? 200 : 500 });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : String(err) },
      { status: 400 },
    );
  }
}
