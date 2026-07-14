/**
 * Core knowledge-sync logic, shared by the CLI (scripts/sync-knowledge.ts) and
 * the in-app "Sync knowledge" button (app/api/sync-knowledge). Reads a checkout
 * of the growthmate-knowledge repo at `kbPath` and upserts into the DB:
 *   skills.kbSkillMd / learningsMd / examplesMd (per lib/knowledge-map.ts)
 *   clients table (every clients/<slug>/)
 */
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, basename } from "node:path";
import { eq, sql } from "drizzle-orm";
import { db } from "./db/client";
import { skills, clients } from "./db/schema";
import { KB_STAGE_SOURCES } from "./knowledge-map";

export interface SyncResult {
  stages: number;
  clients: number;
  warnings: string[];
}

export async function syncKnowledge(kb: string): Promise<SyncResult> {
  const warnings: string[] = [];

  const read = (path: string): string | null => {
    if (!existsSync(path)) return null;
    try {
      return readFileSync(path, "utf8");
    } catch {
      return null;
    }
  };
  const readJson = (path: string): unknown | null => {
    const raw = read(path);
    if (raw === null) return null;
    try {
      return JSON.parse(raw);
    } catch {
      warnings.push(`could not parse JSON: ${path}`);
      return null;
    }
  };
  // Recursively collect method/format files (workflow.md, *-prompt.md, agent
  // -specification.md), skipping examples/incidents/deprecated.
  const collectMethodFiles = (dir: string, acc: string[] = []): string[] => {
    if (!existsSync(dir)) return acc;
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      let isDir = false;
      try {
        isDir = statSync(full).isDirectory();
      } catch {
        continue;
      }
      if (isDir) {
        collectMethodFiles(full, acc);
        continue;
      }
      const name = entry.toLowerCase();
      if (/example|incident|deprecated|pending/.test(name)) continue;
      if (
        name === "workflow.md" ||
        name.endsWith("-prompt.md") ||
        name.endsWith("-specification.md")
      )
        acc.push(full);
    }
    return acc;
  };

  // --- Skills ---------------------------------------------------------------
  const existing = new Set(
    (await db.select({ k: skills.skillKey }).from(skills)).map((r) => r.k),
  );
  let stageCount = 0;

  for (const [stageKey, src] of Object.entries(KB_STAGE_SOURCES)) {
    if (!existing.has(stageKey)) {
      warnings.push(`${stageKey}: no skills row — run seed:skills first`);
      continue;
    }

    const methodParts: string[] = [];
    const learningParts: string[] = [];
    for (const folder of src.skills) {
      const dir = join(kb, "skills", folder);
      if (!existsSync(dir)) {
        warnings.push(`${stageKey}: KB skill folder missing: ${folder}`);
        continue;
      }
      const skillMd = read(join(dir, "SKILL.md"));
      if (skillMd) methodParts.push(`# GrowthMate skill: ${folder}\n\n${skillMd.trim()}`);
      for (const f of collectMethodFiles(dir)) {
        const body = read(f);
        if (body) methodParts.push(`## ${folder}/${basename(f)}\n\n${body.trim()}`);
      }
      const insights = read(join(dir, "learnings", "insights.md"));
      if (insights) learningParts.push(`# Learnings: ${folder}\n\n${insights.trim()}`);
    }

    const exampleParts: string[] = [];
    for (const a of src.anchors ?? []) {
      const body = read(join(kb, "references", "best-performers", a));
      if (body) exampleParts.push(`# ANCHOR (mirror this structure): ${a}\n\n${body.trim()}`);
      else warnings.push(`${stageKey}: missing anchor ${a}`);
    }
    for (const c of src.craft ?? []) {
      const body = read(join(kb, "references", "craft", c));
      if (body) exampleParts.push(`# CRAFT RULES: ${c}\n\n${body.trim()}`);
      else warnings.push(`${stageKey}: missing craft ${c}`);
    }
    // Craft rules that live inside a skill's own references/ folder. collectMethodFiles
    // above only picks up workflow/prompt/spec files, so these are named explicitly.
    for (const r of src.skillRefs ?? []) {
      const body = read(join(kb, r));
      if (body) exampleParts.push(`# CRAFT RULES: ${r}\n\n${body.trim()}`);
      else warnings.push(`${stageKey}: missing skillRef ${r}`);
    }

    await db
      .update(skills)
      .set({
        kbSkillMd: methodParts.join("\n\n---\n\n"),
        learningsMd: learningParts.join("\n\n---\n\n"),
        examplesMd: exampleParts.join("\n\n---\n\n"),
        updatedAt: sql`now()`,
      })
      .where(eq(skills.skillKey, stageKey));
    stageCount += 1;
  }

  // --- Clients --------------------------------------------------------------
  let clientCount = 0;
  const cdirRoot = join(kb, "clients");
  if (!existsSync(cdirRoot)) {
    warnings.push(`clients/ not found in ${kb}`);
  } else {
    const slugs = readdirSync(cdirRoot).filter((d) => {
      if (d.startsWith("_") || d.startsWith(".")) return false;
      try {
        return statSync(join(cdirRoot, d)).isDirectory();
      } catch {
        return false;
      }
    });
    for (const slug of slugs) {
      const cdir = join(cdirRoot, slug);
      const info = readJson(join(cdir, "info.json")) as Record<string, unknown> | null;
      const styleGuideMd = read(join(cdir, "style-guide.md")) ?? "";
      const termMappingsJson = readJson(join(cdir, "term-mappings.json"));
      const displayName =
        (info?.display_name as string) || (info?.company as string) || slug;
      const vertical = (info?.vertical as string) ?? null;

      await db
        .insert(clients)
        .values({ slug, displayName, vertical, infoJson: info, styleGuideMd, termMappingsJson })
        .onConflictDoUpdate({
          target: clients.slug,
          set: { displayName, vertical, infoJson: info, styleGuideMd, termMappingsJson, updatedAt: sql`now()` },
        });
      clientCount += 1;
    }
  }

  return { stages: stageCount, clients: clientCount, warnings };
}
