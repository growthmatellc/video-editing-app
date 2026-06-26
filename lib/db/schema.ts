import {
  pgTable,
  text,
  integer,
  boolean,
  jsonb,
  timestamp,
  pgEnum,
} from "drizzle-orm/pg-core";

export const projectStatus = pgEnum("project_status", [
  "active",
  "on_hold",
  "delivered",
  "archived",
]);

export const stageStatus = pgEnum("stage_status", [
  "not_started",
  "running",
  "draft",
  "approved",
  "rejected",
]);

// One per client webinar funnel.
export const projects = pgTable("projects", {
  id: text("id").primaryKey(),
  clientName: text("client_name").notNull(),
  slug: text("slug").notNull(),
  status: projectStatus("status").notNull().default("active"),
  ownerId: text("owner_id"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

// One per project. The source of truth.
export const intakes = pgTable("intakes", {
  projectId: text("project_id")
    .primaryKey()
    .references(() => projects.id, { onDelete: "cascade" }),
  rawText: text("raw_text").notNull().default(""),
  fields: jsonb("fields").notNull().default({}),
  submittedAt: timestamp("submitted_at", { withTimezone: true }).notNull().defaultNow(),
});

// One row per pipeline stage per project.
export const stages = pgTable("stages", {
  id: text("id").primaryKey(), // `${projectId}-${stageKey}`
  projectId: text("project_id")
    .notNull()
    .references(() => projects.id, { onDelete: "cascade" }),
  stageKey: text("stage_key").notNull(),
  stageOrder: integer("stage_order").notNull(),
  status: stageStatus("status").notNull().default("not_started"),
  assigneeId: text("assignee_id"),
  outputMd: text("output_md"),
  outputMeta: jsonb("output_meta"),
  draftMd: text("draft_md"), // snapshot of the first generation, for a learning diff later
  scoreJson: jsonb("score_json"),
  gatePassed: boolean("gate_passed").notNull().default(false),
  gateAttempts: integer("gate_attempts").notNull().default(0),
  approvedAt: timestamp("approved_at", { withTimezone: true }),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

// Append-only history. Every re-run archives the prior output here.
export const revisions = pgTable("revisions", {
  id: text("id").primaryKey(),
  stageId: text("stage_id")
    .notNull()
    .references(() => stages.id, { onDelete: "cascade" }),
  outputMd: text("output_md").notNull(),
  feedback: text("feedback"),
  createdById: text("created_by_id"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

// The prompt library. One row per skill.
export const skills = pgTable("skills", {
  skillKey: text("skill_key").primaryKey(),
  skillMd: text("skill_md").notNull(),
  learningsMd: text("learnings_md").notNull().default(""),
  examplesMd: text("examples_md").notNull().default(""),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

export type Project = typeof projects.$inferSelect;
export type NewProject = typeof projects.$inferInsert;
export type Intake = typeof intakes.$inferSelect;
export type Stage = typeof stages.$inferSelect;
export type NewStage = typeof stages.$inferInsert;
export type Revision = typeof revisions.$inferSelect;
export type Skill = typeof skills.$inferSelect;
