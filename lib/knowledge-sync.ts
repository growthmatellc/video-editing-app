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
      const onboardingMd = collectOnboarding(cdir, read);
      const openGatesMd = extractOpenGates(read(join(cdir, "CHEATSHEET.md")));

      if (!onboardingMd.trim()) {
        warnings.push(
          `${slug}: no onboarding research (CHEATSHEET/briefs/research all empty) — ` +
            `projects for this client will have no auto-intake`,
        );
      }

      await db
        .insert(clients)
        .values({
          slug, displayName, vertical, infoJson: info, styleGuideMd, termMappingsJson,
          onboardingMd, openGatesMd,
        })
        .onConflictDoUpdate({
          target: clients.slug,
          set: {
            displayName, vertical, infoJson: info, styleGuideMd, termMappingsJson,
            onboardingMd, openGatesMd, updatedAt: sql`now()`,
          },
        });
      clientCount += 1;
    }
  }

  return { stages: stageCount, clients: clientCount, warnings };
}

// --- Onboarding research -----------------------------------------------------

type Reader = (path: string) => string | null;

const mdIn = (dir: string): string[] =>
  existsSync(dir)
    ? readdirSync(dir).filter((f) => f.toLowerCase().endsWith(".md")).sort()
    : [];

/**
 * Assemble the /onboard research corpus for one client, in the precedence order
 * clients/README.md defines. This becomes the project's intake.
 *
 * The completed onboarding doc is the client's own words and outranks everything
 * else — it leads, and the banner says so, because the corpus also carries sources
 * that are known to contradict it (the agency-authored case-study PDFs rank lowest).
 * Order alone doesn't tell a model what wins; the banner does.
 */
function collectOnboarding(cdir: string, read: Reader): string {
  const parts: string[] = [];
  const add = (path: string, heading: string) => {
    const body = read(path)?.trim();
    if (body) parts.push(`# ${heading}\n\n${body}`);
  };

  const researchDir = join(cdir, "research");
  const research = mdIn(researchDir);
  // Authoritative source first, whatever its date prefix.
  const completed = research.filter((f) => /onboarding-doc-completed/i.test(f));
  const otherResearch = research.filter((f) => !/onboarding-doc-completed/i.test(f));

  for (const f of completed) {
    add(join(researchDir, f), `AUTHORITATIVE — the client's completed onboarding doc (${f})`);
  }
  add(join(cdir, "CHEATSHEET.md"), "Cheat sheet — the 1-page version, incl. watch-outs");

  const briefsDir = join(cdir, "briefs");
  // human-brief is the narrative orientation; lead the briefs with it.
  const briefs = mdIn(briefsDir);
  for (const f of [...briefs.filter((b) => /human-brief/i.test(b)), ...briefs.filter((b) => !/human-brief/i.test(b))]) {
    add(join(briefsDir, f), `Brief — ${f}`);
  }
  for (const f of otherResearch) add(join(researchDir, f), `Research — ${f}`);
  add(join(cdir, "design", "brand-guidelines-extract.md"), "Brand guidelines");

  if (!parts.length) return "";

  return [
    `# Client onboarding research — THE INTAKE, extracted by /onboard.`,
    `This is the source of truth for this client. Build from it; do not invent facts it does not contain.`,
    ``,
    `SOURCE PRECEDENCE — where sources disagree, the higher one WINS:`,
    `  1. The client's completed onboarding doc (his own words)`,
    `  2. The cheat sheet and human brief`,
    `  3. Everything else (external research, DM playbook, VSL transcripts)`,
    `  LOWEST. Agency-authored case-study PDFs — known to contradict the client's own doc.`,
    ``,
    `Where this corpus flags an OPEN GATE or a watch-out, honor it as a hard constraint.`,
    `Do not resolve a gate yourself to unblock your output.`,
    ``,
    `---`,
    ``,
    parts.join("\n\n---\n\n"),
  ].join("\n");
}

/**
 * Pull the CHEATSHEET's watch-outs + open questions. These are the decisions /onboard
 * deliberately did NOT make (they're Lauren's), and the things that must not be
 * silently guessed — a credential, a medical claim, which proof story leads.
 */
function extractOpenGates(cheatsheet: string | null): string {
  if (!cheatsheet) return "";
  const lines = cheatsheet.split("\n");
  const out: string[] = [];
  let capturing = false;
  for (const line of lines) {
    if (/^#{1,4}\s/.test(line)) {
      capturing = /watch-?out|open question|gate|blocker/i.test(line);
      if (capturing) out.push(line);
      continue;
    }
    if (capturing) out.push(line);
  }
  return out.join("\n").trim();
}
