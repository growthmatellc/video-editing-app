/**
 * CRUD over the five tables, plus stage seeding from WEBINAR_PIPELINE on
 * project create. The intake stage starts `approved` (it is human-entered and
 * is the source of truth, not a generated draft).
 */
import { nanoid } from "nanoid";
import { eq, asc, desc, inArray } from "drizzle-orm";
import { db } from "./db/client";
import {
  projects,
  intakes,
  stages,
  revisions,
  skills,
  type Project,
  type Intake,
  type Stage,
  type Revision,
  type Skill,
} from "./db/schema";
import { WEBINAR_PIPELINE } from "./pipeline";

function slugify(name: string): string {
  return (
    name
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 60) || "project"
  );
}

export async function createProject(input: {
  clientName: string;
  rawText: string;
  ownerId?: string | null;
}): Promise<{ id: string }> {
  const id = nanoid(12);
  const now = new Date();

  await db.insert(projects).values({
    id,
    clientName: input.clientName,
    slug: `${slugify(input.clientName)}-${id.slice(0, 5)}`,
    status: "active",
    ownerId: input.ownerId ?? null,
    createdAt: now,
    updatedAt: now,
  });

  await db.insert(intakes).values({
    projectId: id,
    rawText: input.rawText,
    fields: {},
    submittedAt: now,
  });

  // Seed one stage row per pipeline stage. The intake stage is born approved.
  await db.insert(stages).values(
    WEBINAR_PIPELINE.map((s) => ({
      id: `${id}-${s.key}`,
      projectId: id,
      stageKey: s.key,
      stageOrder: s.order,
      status: (s.key === "intake" ? "approved" : "not_started") as Stage["status"],
      outputMd: s.key === "intake" ? input.rawText : null,
      approvedAt: s.key === "intake" ? now : null,
      updatedAt: now,
    })),
  );

  return { id };
}

export interface ProjectWithStages {
  project: Project;
  intake: Intake | null;
  stages: Stage[];
}

export async function getProject(id: string): Promise<ProjectWithStages | null> {
  const [project] = await db.select().from(projects).where(eq(projects.id, id));
  if (!project) return null;

  const [intake] = await db.select().from(intakes).where(eq(intakes.projectId, id));
  const stageRows = await db
    .select()
    .from(stages)
    .where(eq(stages.projectId, id))
    .orderBy(asc(stages.stageOrder));

  return { project, intake: intake ?? null, stages: stageRows };
}

export interface ProjectSummary {
  project: Project;
  stages: { stageKey: string; stageOrder: number; status: Stage["status"] }[];
}

export async function listProjects(): Promise<ProjectSummary[]> {
  const projectRows = await db
    .select()
    .from(projects)
    .orderBy(desc(projects.updatedAt));
  if (projectRows.length === 0) return [];

  const ids = projectRows.map((p) => p.id);
  const stageRows = await db
    .select({
      projectId: stages.projectId,
      stageKey: stages.stageKey,
      stageOrder: stages.stageOrder,
      status: stages.status,
    })
    .from(stages)
    .where(inArray(stages.projectId, ids))
    .orderBy(asc(stages.stageOrder));

  const byProject = new Map<string, ProjectSummary["stages"]>();
  for (const r of stageRows) {
    const list = byProject.get(r.projectId) ?? [];
    list.push({ stageKey: r.stageKey, stageOrder: r.stageOrder, status: r.status });
    byProject.set(r.projectId, list);
  }

  return projectRows.map((project) => ({
    project,
    stages: byProject.get(project.id) ?? [],
  }));
}

export async function getStage(
  projectId: string,
  stageKey: string,
): Promise<Stage | null> {
  const [row] = await db
    .select()
    .from(stages)
    .where(eq(stages.id, `${projectId}-${stageKey}`));
  return row ?? null;
}

export async function getSkill(skillKey: string): Promise<Skill | null> {
  const [row] = await db.select().from(skills).where(eq(skills.skillKey, skillKey));
  return row ?? null;
}

/** Archive the current output of a stage into revisions (append-only history). */
export async function archiveRevision(
  stage: Stage,
  feedback: string | null,
  createdById: string | null,
): Promise<void> {
  if (!stage.outputMd) return;
  await db.insert(revisions).values({
    id: nanoid(14),
    stageId: stage.id,
    outputMd: stage.outputMd,
    feedback,
    createdById,
    createdAt: new Date(),
  });
}

export async function listRevisions(stageId: string): Promise<Revision[]> {
  return db
    .select()
    .from(revisions)
    .where(eq(revisions.stageId, stageId))
    .orderBy(desc(revisions.createdAt));
}

export async function setStageStatus(
  stageId: string,
  status: Stage["status"],
): Promise<void> {
  const patch: Partial<Stage> = { status, updatedAt: new Date() };
  if (status === "approved") patch.approvedAt = new Date();
  await db.update(stages).set(patch).where(eq(stages.id, stageId));
  await touchProjectByStageId(stageId);
}

/** Update a stage with generated output. */
export async function saveStageOutput(
  stageId: string,
  patch: Partial<Stage>,
): Promise<void> {
  await db
    .update(stages)
    .set({ ...patch, updatedAt: new Date() })
    .where(eq(stages.id, stageId));
  await touchProjectByStageId(stageId);
}

async function touchProjectByStageId(stageId: string): Promise<void> {
  const [row] = await db
    .select({ projectId: stages.projectId })
    .from(stages)
    .where(eq(stages.id, stageId));
  if (row) {
    await db
      .update(projects)
      .set({ updatedAt: new Date() })
      .where(eq(projects.id, row.projectId));
  }
}
