/**
 * Seed the `skills` table from /skills/<key>/SKILL.md.
 *
 * Run with: npm run seed:skills
 *
 * Idempotent: upserts on skillKey, so re-running updates skillMd in place
 * without touching learningsMd / examplesMd (those are edited in-app over time).
 */
import { config } from "dotenv";
// Local env first (Vercel writes here), then .env as a fallback.
config({ path: ".env.local" });
config();

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { db } from "../lib/db/client";
import { skills } from "../lib/db/schema";
import { WEBINAR_PIPELINE } from "../lib/pipeline";
import { sql } from "drizzle-orm";

const SKILLS_DIR = join(process.cwd(), "skills");

// Only seed skills referenced by a pipeline stage, so the table stays in sync
// with the pipeline. (intake / brand-kit have skillKey: null and are skipped.)
const wantedKeys = new Set(
  WEBINAR_PIPELINE.map((s) => s.skillKey).filter((k): k is string => !!k),
);

async function main() {
  const dirs = readdirSync(SKILLS_DIR).filter((d) => {
    try {
      return statSync(join(SKILLS_DIR, d)).isDirectory();
    } catch {
      return false;
    }
  });

  let seeded = 0;
  const missing: string[] = [];

  for (const key of wantedKeys) {
    if (!dirs.includes(key)) {
      missing.push(key);
      continue;
    }
    const md = readFileSync(join(SKILLS_DIR, key, "SKILL.md"), "utf8");
    await db
      .insert(skills)
      .values({ skillKey: key, skillMd: md })
      .onConflictDoUpdate({
        target: skills.skillKey,
        set: { skillMd: md, updatedAt: sql`now()` },
      });
    seeded += 1;
    console.log(`  seeded ${key}`);
  }

  if (missing.length) {
    console.warn(`\n  WARNING: no SKILL.md found for: ${missing.join(", ")}`);
  }
  console.log(`\nDone. ${seeded} skill(s) seeded.`);
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
