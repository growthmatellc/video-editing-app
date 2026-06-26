import { notFound } from "next/navigation";
import { getProject } from "@/lib/project-store";
import { Studio, type StudioStage } from "@/components/Studio";

export const dynamic = "force-dynamic";

export default async function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const data = await getProject(id);
  if (!data) notFound();

  const stages: StudioStage[] = data.stages.map((s) => ({
    stageKey: s.stageKey,
    stageOrder: s.stageOrder,
    status: s.status,
    outputMd: s.outputMd,
    outputMeta: s.outputMeta as Record<string, unknown> | null,
    scoreJson: s.scoreJson as StudioStage["scoreJson"],
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
    />
  );
}
