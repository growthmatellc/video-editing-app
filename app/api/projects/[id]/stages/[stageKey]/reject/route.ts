import { NextResponse } from "next/server";
import { getStage } from "@/lib/project-store";
import { runStage } from "@/lib/skill-executor";
import { getOperatorId } from "@/lib/auth";
import { parseVideoEditRequest } from "@/lib/video-edit/types";

export const runtime = "nodejs";
// Video Edit re-renders a proxy on reject. Match the run route's ceiling.
export const maxDuration = 800;

/**
 * Reject = record the feedback and immediately re-run the stage with that
 * feedback folded in. The prior output is archived into revisions by the
 * executor before the new draft is saved.
 */
export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string; stageKey: string }> },
) {
  const { id, stageKey } = await params;
  let feedback = "";
  let videoEdit: ReturnType<typeof parseVideoEditRequest>;
  try {
    const body = await req.json();
    feedback = typeof body?.feedback === "string" ? body.feedback.trim() : "";
    videoEdit = parseVideoEditRequest(body?.videoEdit);
  } catch {
    // no body
  }
  if (!feedback) {
    return NextResponse.json(
      { error: "Feedback is required to reject and re-run." },
      { status: 400 },
    );
  }

  const stage = await getStage(id, stageKey);
  if (!stage) return NextResponse.json({ error: "Stage not found" }, { status: 404 });

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
