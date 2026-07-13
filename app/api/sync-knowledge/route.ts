import { NextResponse } from "next/server";
import { fetchKnowledgeRepo } from "@/lib/github-tarball";
import { syncKnowledge } from "@/lib/knowledge-sync";

export const runtime = "nodejs";
export const maxDuration = 300;

/**
 * Pull the latest growthmate-knowledge from GitHub and sync it into the DB.
 * Powers the in-app "Sync knowledge" button so the team doesn't need a terminal.
 */
export async function POST() {
  let cleanup: (() => void) | undefined;
  try {
    const repo = await fetchKnowledgeRepo();
    cleanup = repo.cleanup;
    const result = await syncKnowledge(repo.root);
    return NextResponse.json({ ok: true, ...result });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  } finally {
    cleanup?.();
  }
}
