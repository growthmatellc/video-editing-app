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
 * Two syncs, both idempotent (upsert):
 *   1. Skills  — folds each mapped KB craft skill (lib/knowledge-map.ts) into
 *                skills.kbSkillMd for its pipeline stage. Requires the stage's
 *                skills row to already exist (run `npm run seed:skills` first).
 *   2. Clients — mirrors every clients/<slug>/ (info.json, style-guide.md,
 *                term-mappings.json) into the clients table.
 *
 * Point at a different checkout with KNOWLEDGE_REPO_PATH=/abs/path npm run sync:knowledge
 */
import { config } from "dotenv";
config({ path: ".env.local" });
config();

import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { eq, sql } from "drizzle-orm";
import { db } from "../lib/db/client";
import { skills, clients } from "../lib/db/schema";
import { KB_SKILL_MAP, KB_SKILL_FILE_CANDIDATES } from "../lib/knowledge-map";

const KB = resolve(
  process.env.KNOWLEDGE_REPO_PATH ?? join(process.cwd(), "..", "growthmate-knowledge"),
);

const warnings: string[] = [];

function readSkillBody(folder: string): string | null {
  const dir = join(KB, "skills", folder);
  if (!existsSync(dir)) return null;
  for (const cand of KB_SKILL_FILE_CANDIDATES) {
    const p = join(dir, cand);
    if (existsSync(p)) return readFileSync(p, "utf8");
  }
  return null;
}

function readJson(p: string): unknown | null {
  if (!existsSync(p)) return null;
  try {
    return JSON.parse(readFileSync(p, "utf8"));
  } catch {
    warnings.push(`  [client] could not parse JSON: ${p}`);
    return null;
  }
}

async function syncSkills() {
  console.log("\nSkills → skills.kbSkillMd");
  const existing = new Set(
    (await db.select({ k: skills.skillKey }).from(skills)).map((r) => r.k),
  );

  let updated = 0;
  for (const [stageKey, folders] of Object.entries(KB_SKILL_MAP)) {
    const parts: string[] = [];
    for (const folder of folders) {
      const body = readSkillBody(folder);
      if (!body) {
        warnings.push(`  [skill] ${stageKey}: KB skill not found/empty: ${folder}`);
        continue;
      }
      parts.push(`# GrowthMate craft skill: ${folder}\n\n${body.trim()}`);
    }
    const kbSkillMd = parts.join("\n\n---\n\n");
    if (!kbSkillMd) continue;

    if (!existing.has(stageKey)) {
      warnings.push(
        `  [skill] ${stageKey}: no skills row yet — run \`npm run seed:skills\` first`,
      );
      continue;
    }
    await db
      .update(skills)
      .set({ kbSkillMd, updatedAt: sql`now()` })
      .where(eq(skills.skillKey, stageKey));
    updated += 1;
    console.log(`  folded ${folders.join(" + ")} → ${stageKey}`);
  }
  console.log(`  ${updated} stage(s) updated with KB craft skills.`);
}

async function syncClients() {
  console.log("\nClients → clients table");
  const dir = join(KB, "clients");
  if (!existsSync(dir)) {
    warnings.push(`  [client] clients/ not found in ${KB}`);
    return;
  }

  const slugs = readdirSync(dir).filter((d) => {
    if (d.startsWith("_") || d.startsWith(".")) return false; // _template, dotfiles
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
    const styleGuideMd = existsSync(join(cdir, "style-guide.md"))
      ? readFileSync(join(cdir, "style-guide.md"), "utf8")
      : "";
    const termMappingsJson = readJson(join(cdir, "term-mappings.json"));

    const displayName =
      (info?.display_name as string) || (info?.company as string) || slug;
    const vertical = (info?.vertical as string) ?? null;

    await db
      .insert(clients)
      .values({ slug, displayName, vertical, infoJson: info, styleGuideMd, termMappingsJson })
      .onConflictDoUpdate({
        target: clients.slug,
        set: {
          displayName,
          vertical,
          infoJson: info,
          styleGuideMd,
          termMappingsJson,
          updatedAt: sql`now()`,
        },
      });
    count += 1;
    console.log(`  ${slug} — ${displayName}`);
  }
  console.log(`  ${count} client(s) synced.`);
}

async function main() {
  console.log(`Syncing from: ${KB}`);
  if (!existsSync(KB)) {
    console.error(
      `\nKnowledge repo not found at ${KB}.\n` +
        `Clone it as a sibling, or set KNOWLEDGE_REPO_PATH to its location.`,
    );
    process.exit(1);
  }

  await syncSkills();
  await syncClients();

  if (warnings.length) {
    console.warn(`\nWarnings:\n${warnings.join("\n")}`);
  }
  console.log("\nDone.");
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
