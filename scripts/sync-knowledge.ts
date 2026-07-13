/**
 * CLI: sync the growthmate-knowledge repo (a local checkout) into the database.
 *
 * Run with: npm run sync:knowledge
 * (Refresh the repo first: `cd ../growthmate-knowledge && git pull`.)
 *
 * The in-app "Sync knowledge" button does the same thing but pulls the repo
 * straight from GitHub — see app/api/sync-knowledge. Both call syncKnowledge().
 *
 * Point at a different checkout with KNOWLEDGE_REPO_PATH=/abs/path npm run sync:knowledge
 */
import { config } from "dotenv";
config({ path: ".env.local" });
config();

import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { syncKnowledge } from "../lib/knowledge-sync";

const KB = resolve(
  process.env.KNOWLEDGE_REPO_PATH ?? join(process.cwd(), "..", "growthmate-knowledge"),
);

async function main() {
  console.log(`Syncing from: ${KB}`);
  if (!existsSync(KB)) {
    console.error(`\nKnowledge repo not found at ${KB}. Clone it as a sibling or set KNOWLEDGE_REPO_PATH.`);
    process.exit(1);
  }
  const r = await syncKnowledge(KB);
  console.log(`\nDone. ${r.stages} stage(s), ${r.clients} client(s) synced.`);
  if (r.warnings.length) console.warn(`\nWarnings:\n- ${r.warnings.join("\n- ")}`);
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
