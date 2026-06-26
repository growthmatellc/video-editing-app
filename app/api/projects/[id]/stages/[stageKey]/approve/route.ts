import { NextResponse } from "next/server";
import { getStage, setStageStatus } from "@/lib/project-store";

export const runtime = "nodejs";

export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string; stageKey: string }> },
) {
  const { id, stageKey } = await params;
  const stage = await getStage(id, stageKey);
  if (!stage) return NextResponse.json({ error: "Stage not found" }, { status: 404 });
  if (!stage.outputMd) {
    return NextResponse.json(
      { error: "Nothing to approve — run the stage first." },
      { status: 400 },
    );
  }
  await setStageStatus(stage.id, "approved");
  return NextResponse.json({ ok: true, status: "approved" });
}
