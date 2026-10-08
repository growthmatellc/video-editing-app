import { notFound } from "next/navigation";
import { getProject } from "@/lib/project-store";
import { Studio, type StudioStage } from "@/components/Studio";
import { videoEditEnv } from "@/lib/video-edit/run";

export const dynamic = "force-dynamic";

export default async function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let data: Awaited<ReturnType<typeof getProject>>;
  try {
    data = await getProject(id);
  } catch (err) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-16">
        <div className="rounded-[var(--radius)] border border-[var(--warn)] bg-[var(--surface)] p-5 text-sm">
          <p className="font-medium text-[var(--warn)] mb-1">Could not load this project</p>
          <p className="text-[var(--text-muted)]">
            The database was not reachable. Refresh in a moment, or check{" "}
            <code>DATABASE_URL</code> in your Vercel environment.
          </p>
          <p className="text-[var(--text-muted)] mt-2 font-mono text-xs">
            {err instanceof Error ? err.message : String(err)}
          </p>
        </div>
      </div>
    );
  }
  if (!data) notFound();

  const stages: StudioStage[] = data.stages.map((s) => ({
    stageKey: s.stageKey,
    stageOrder: s.stageOrder,
    status: s.status,
    outputMd: s.outputMd,
    outputMeta: s.outputMeta as Record<string, unknown> | null,
    scoreJson: s.scoreJson as StudioStage["scoreJson"],
    auditJson: s.auditJson as StudioStage["auditJson"],
    gatePassed: s.gatePassed,
    gateAttempts: s.gateAttempts,
  }));

  return (
    <Studio
      projectId={id}
      clientName={data.project.clientName}
      status={data.project.status}
      intakeText={data.intake?.rawText ?? ""}
      initialStages={stages}
      blobUploadEnabled={videoEditEnv().blobUploadEnabled}
      transcriptionConfigured={videoEditEnv().transcriptionConfigured}
    />
  );
}
