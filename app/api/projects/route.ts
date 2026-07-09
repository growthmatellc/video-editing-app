import { NextResponse } from "next/server";
import { createProject, listProjects } from "@/lib/project-store";
import { getOperatorId } from "@/lib/auth";

export const runtime = "nodejs";

export async function GET() {
  const projects = await listProjects();
  return NextResponse.json({ projects });
}

export async function POST(req: Request) {
  let body: { clientName?: string; rawText?: string; clientSlug?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const clientName = body.clientName?.trim();
  const rawText = body.rawText?.trim() ?? "";
  const clientSlug = body.clientSlug?.trim() || null;
  if (!clientName) {
    return NextResponse.json({ error: "clientName is required" }, { status: 400 });
  }

  const ownerId = await getOperatorId();
  const { id } = await createProject({ clientName, rawText, clientSlug, ownerId });
  return NextResponse.json({ id }, { status: 201 });
}
