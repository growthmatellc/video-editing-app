/**
 * CLI: vendor the copywriting auditor (Python) from the growthmate-knowledge repo
 * into the app so it deploys as a Vercel Python function (api/audit/index.py).
 *
 * Run with: npm run vendor:auditor
 * (Refresh the KB first: `cd ../growthmate-knowledge && git pull`.)
 *
 * Re-run this whenever the KB's auditor rules change — same discipline as
 * `npm run sync:knowledge`. Point at a different checkout with
 * KNOWLEDGE_REPO_PATH=/abs/path npm run vendor:auditor
 *
 * The vendored tree preserves the `skills/copywriting/auditor/` path so the
 * module's absolute imports (`from skills.copywriting.auditor.lib...`) resolve
 * with sys.path = api/audit/_vendor (the Python handler sets that).
 */
import { config } from "dotenv";
config({ path: ".env.local" });
config();

import { existsSync, rmSync, mkdirSync, cpSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const KB = resolve(
  process.env.KNOWLEDGE_REPO_PATH ?? join(process.cwd(), "..", "growthmate-knowledge"),
);

const SRC = join(KB, "skills", "copywriting", "auditor");
const VENDOR_ROOT = join(process.cwd(), "api", "audit", "_vendor");
const DEST = join(VENDOR_ROOT, "skills", "copywriting", "auditor");

function main() {
  console.log(`Vendoring auditor from: ${SRC}`);
  if (!existsSync(SRC)) {
    console.error(
      `\nAuditor not found at ${SRC}. Clone growthmate-knowledge as a sibling or set KNOWLEDGE_REPO_PATH.`,
    );
    process.exit(1);
  }

  // Wipe and recreate the vendored tree so deleted rule files don't linger.
  rmSync(VENDOR_ROOT, { recursive: true, force: true });
  mkdirSync(DEST, { recursive: true });

  // Copy the auditor subtree, skipping caches. The auditor is stdlib-only, so
  // there's nothing else to bring along (no requirements.txt, no config YAML).
  cpSync(SRC, DEST, {
    recursive: true,
    filter: (src) => !/__pycache__|\.pyc$|\.DS_Store/.test(src),
  });

  // Namespace parents. auditor/ + its lib/ and rules/ already ship __init__.py;
  // the two levels above them need empty ones so the absolute import resolves.
  for (const pkg of [join(VENDOR_ROOT, "skills"), join(VENDOR_ROOT, "skills", "copywriting")]) {
    writeFileSync(join(pkg, "__init__.py"), "");
  }

  console.log(`Done. Vendored into ${DEST}`);
}

main();
