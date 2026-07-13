/**
 * Sync the growthmate-knowledge repo into the database.
 *
 * Run with: npm run sync:knowledge
 * (Refresh the repo first: `cd ../growthmate-knowledge && git pull`.)
 *
 * Why DB, not direct file reads: the knowledge repo is NOT deployed to Vercel,
 * so the app must read this content from Postgres at runtime. This script is the
 * bridge — run it locally after a git pull; the deployed app then uses the DB.
 *
 * Per stage (lib/knowledge-map.ts), all idempotent upserts:
 *   skills.kbSkillMd   = each skill folder's SKILL.md + workflow/prompt files (the method)
 *   skills.learningsMd = each skill folder's learnings/insights.md (learned corrections)
 *   skills.examplesMd  = best-performer anchors + craft rules (formats to MIRROR)
 *   clients.*          = every clients/<slug>/ (info.json, style-guide.md, term-mappings.json)
 *
 * Requires the stage's skills row to exist (run `npm run seed:skills` first).
 * Point at a different checkout with KNOWLEDGE_REPO_PATH=/abs/path npm run sync:knowledge
 */
import { config } from "dotenv";
config({ path: ".env.local" });
config();

import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, resolve, basename } from "node:path";
import { eq, sql } from "drizzle-orm";
import { db } from "../lib/db/client";
import { skills, clients } from "../lib/db/schema";
import { KB_STAGE_SOURCES } from "../lib/knowledge-map";

const KB = resolve(
  process.env.KNOWLEDGE_REPO_PATH ?? join(process.cwd(), "..", "growthmate-knowledge"),
);

const warnings: string[] = [];

function read(path: string): string | null {
  if (!existsSync(path)) return null;
  try {
    return readFileSync(path, "utf8");
  } catch {
    return null;
  }
}

function readJson(p: string): unknown | null {
  const raw = read(p);
  if (raw === null) return null;
  try {
    return JSON.parse(raw);
  } catch {
    warnings.push(`  [client] could not parse JSON: ${p}`);
    return null;
  }
}

// Recursively collect *.md files under dir whose basename is workflow.md or ends
// with -prompt.md — the method/format files — skipping examples/incidents/deprecated.
function collectMethodFiles(dir: string, acc: string[] = []): string[] {
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
    // workflow + prompt files, plus agent-spec skills (image-ads-creation etc.)
    if (
      name === "workflow.md" ||
      name.endsWith("-prompt.md") ||
      name.endsWith("-specification.md")
    )
      acc.push(full);
  }
  return acc;
}

function syncStageContent() {
  console.log("\nSkills → kbSkillMd / learningsMd / examplesMd");
  return db
    .select({ k: skills.skillKey })
    .from(skills)
    .then(async (rows) => {
      const existing = new Set(rows.map((r) => r.k));
      let updated = 0;

      for (const [stageKey, src] of Object.entries(KB_STAGE_SOURCES)) {
        if (!existing.has(stageKey)) {
          warnings.push(`  [skill] ${stageKey}: no skills row — run \`npm run seed:skills\` first`);
          continue;
        }

        // kbSkillMd = SKILL.md + method files, per skill folder.
        const methodParts: string[] = [];
        const learningParts: string[] = [];
        for (const folder of src.skills) {
          const dir = join(KB, "skills", folder);
          if (!existsSync(dir)) {
            warnings.push(`  [skill] ${stageKey}: KB skill folder missing: ${folder}`);
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

        // examplesMd = anchors + craft.
        const exampleParts: string[] = [];
        for (const a of src.anchors ?? []) {
          const body = read(join(KB, "references", "best-performers", a));
          if (body) exampleParts.push(`# ANCHOR (mirror this structure): ${a}\n\n${body.trim()}`);
          else warnings.push(`  [anchor] ${stageKey}: missing ${a}`);
        }
        for (const c of src.craft ?? []) {
          const body = read(join(KB, "references", "craft", c));
          if (body) exampleParts.push(`# CRAFT RULES: ${c}\n\n${body.trim()}`);
          else warnings.push(`  [craft] ${stageKey}: missing ${c}`);
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
        updated += 1;
        console.log(
          `  ${stageKey}: ${src.skills.join("+")} | ${(src.anchors ?? []).length} anchor(s), ${(src.craft ?? []).length} craft`,
        );
      }
      console.log(`  ${updated} stage(s) updated.`);
    });
}

async function syncClients() {
  console.log("\nClients → clients table");
  const dir = join(KB, "clients");
  if (!existsSync(dir)) {
    warnings.push(`  [client] clients/ not found in ${KB}`);
    return;
  }
  const slugs = readdirSync(dir).filter((d) => {
    if (d.startsWith("_") || d.startsWith(".")) return false;
    try {
      return statSync(join(dir, d)).isDirectory();
    } catch {
      return false;
    }
  });

  let count = 0;
  for (const slug of slugs) {
    const cdir = join(dir, slug);
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
    count += 1;
  }
  console.log(`  ${count} client(s) synced.`);
}

async function main() {
  console.log(`Syncing from: ${KB}`);
  if (!existsSync(KB)) {
    console.error(`\nKnowledge repo not found at ${KB}. Clone it as a sibling or set KNOWLEDGE_REPO_PATH.`);
    process.exit(1);
  }
  await syncStageContent();
  await syncClients();
  if (warnings.length) console.warn(`\nWarnings:\n${warnings.join("\n")}`);
  console.log("\nDone.");
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
