/**
 * CLI: run a project's pipeline stages in order, unattended.
 *
 *   npm run run:pipeline -- --project <id>              # all runnable stages
 *   npm run run:pipeline -- --project <id> --to webinar-script
 *   npm run run:pipeline -- --project <id> --only webinar-blueprint
 *
 * Stages chain: each one runs with every prior stage's latest output as locked
 * context (see skill-executor's `chainDrafts`). Nothing is auto-approved — every
 * stage lands as a `draft` for a human to review in the app. Approving work no
 * human has read would be a lie, and the gate is the point of the tool.
 *
 * Stops on the first failure by default: stage N+1 builds on stage N, so pressing
 * on after a failure just compounds a bad foundation. --keep-going overrides.
 */
import { config } from "dotenv";
config({ path: ".env.local" });
config();

import { WEBINAR_PIPELINE } from "../lib/pipeline";
import { runStage } from "../lib/skill-executor";
import { getProject } from "../lib/project-store";

function arg(name: string): string | undefined {
  const i = process.argv.indexOf(`--${name}`);
  return i !== -1 ? process.argv[i + 1] : undefined;
}
const has = (name: string) => process.argv.includes(`--${name}`);

async function main() {
  const projectId = arg("project");
  if (!projectId) {
    console.error("Usage: npm run run:pipeline -- --project <id> [--to <stage>] [--only <stage>] [--keep-going]");
    process.exit(1);
  }

  const data = await getProject(projectId);
  if (!data) {
    console.error(`Project not found: ${projectId}`);
    process.exit(1);
  }

  const intakeLen = data.intake?.rawText?.trim().length ?? 0;
  if (!intakeLen) {
    console.error(
      `\nProject "${data.project.clientName}" has an EMPTY intake.\n` +
        `Every stage would invent the client from nothing. Link the project to a client ` +
        `whose onboarding research is synced (npm run sync:knowledge) and recreate it.\n`,
    );
    process.exit(1);
  }

  const only = arg("only");
  const to = arg("to");
  let todo = WEBINAR_PIPELINE.filter((s) => s.runnable !== false);
  if (only) todo = todo.filter((s) => s.key === only);
  else if (to) {
    const stop = WEBINAR_PIPELINE.find((s) => s.key === to);
    if (!stop) {
      console.error(`Unknown stage: ${to}`);
      process.exit(1);
    }
    todo = todo.filter((s) => s.order <= stop.order);
  }

  console.log(`\nProject : ${data.project.clientName} (${projectId})`);
  console.log(`Client  : ${data.project.clientSlug ?? "— none linked —"}`);
  console.log(`Intake  : ${intakeLen.toLocaleString()} chars`);
  console.log(`Stages  : ${todo.length}\n`);

  const failed: string[] = [];
  for (const [i, stage] of todo.entries()) {
    const n = `${i + 1}/${todo.length}`;
    process.stdout.write(`[${n}] ${stage.label} … `);
    const started = Date.now();
    try {
      const r = await runStage(projectId, stage.key, undefined, "cli", { chainDrafts: true });
      const secs = Math.round((Date.now() - started) / 1000);
      if (!r.ok) {
        console.log(`FAILED (${secs}s) — ${r.error}`);
        failed.push(stage.key);
        if (!has("keep-going")) {
          console.error(`\nStopping: later stages build on this one. Fix it, then re-run.`);
          break;
        }
        continue;
      }
      const gate = r.score ? (r.score.passed ? "gate PASS" : "gate FAIL") : "no gate";
      const flags = r.audit?.violations?.length
        ? `, ${r.audit.violations.length} audit violation(s)`
        : "";
      console.log(`draft (${secs}s, ${gate}${flags})`);
    } catch (err) {
      const secs = Math.round((Date.now() - started) / 1000);
      console.log(`ERROR (${secs}s) — ${err instanceof Error ? err.message : String(err)}`);
      failed.push(stage.key);
      if (!has("keep-going")) break;
    }
  }

  console.log(
    `\nDone. Every stage is a DRAFT — nothing was approved. Review them in the app:\n` +
      `  /${projectId}\n`,
  );
  if (failed.length) console.log(`Failed: ${failed.join(", ")}`);
  process.exit(failed.length ? 1 : 0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
