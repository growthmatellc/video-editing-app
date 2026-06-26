/**
 * The skill executor (section 7). Provider-agnostic: calls lib/llm.ts, never
 * the Anthropic SDK directly.
 *
 * runStage() generates (or re-generates) the deliverable for one stage, folding
 * in every approved prior stage as locked context, runs voice-gated stages
 * through the review gate, special-cases brand-kit (scrape) and webinar-slides
 * (JSON -> .pptx), archives any prior output into revisions, and saves the draft.
 */
import { generate, generateJson, stripFences } from "./llm";
import { runWithGate, type GateScore } from "./gate";
import { VOICE_RULES } from "./voice-rules";
import { STAGE_BY_KEY, VOICE_GATED_STAGES, type StageDef } from "./pipeline";
import {
  getProject,
  getStage,
  getSkill,
  archiveRevision,
  saveStageOutput,
  type ProjectWithStages,
} from "./project-store";
import { scrapeBrandKit, brandKitToMarkdown, extractUrl } from "./brand-kit";
import {
  SLIDES_SYSTEM_PROMPT,
  isValidDeck,
  type SlideDeck,
  type BrandKit,
} from "./slide-deck-schema";
import { renderDeck } from "./slide-renderer";
import type { Stage } from "./db/schema";

const MAX_GATE_ATTEMPTS = 3;

export interface RunResult {
  ok: boolean;
  stageKey: string;
  status: Stage["status"];
  outputMd: string;
  score?: GateScore | null;
  error?: string;
}

export async function runStage(
  projectId: string,
  stageKey: string,
  feedback?: string,
  operatorId?: string | null,
): Promise<RunResult> {
  const def = STAGE_BY_KEY[stageKey];
  if (!def) throw new Error(`Unknown stage: ${stageKey}`);
  if (def.runnable === false) throw new Error(`Stage ${stageKey} is human-only`);

  const data = await getProject(projectId);
  if (!data) throw new Error(`Project not found: ${projectId}`);
  const stageRow = await getStage(projectId, stageKey);
  if (!stageRow) throw new Error(`Stage row missing: ${stageKey}`);

  // Mark running.
  await saveStageOutput(stageRow.id, { status: "running" });

  try {
    if (stageKey === "brand-kit") {
      return await runBrandKit(data, stageRow, feedback, operatorId);
    }
    if (stageKey === "webinar-slides") {
      return await runSlides(data, def, stageRow, feedback, operatorId);
    }
    return await runProse(data, def, stageRow, feedback, operatorId);
  } catch (err) {
    // Restore a non-running status so the UI is not stuck.
    await saveStageOutput(stageRow.id, {
      status: stageRow.outputMd ? "draft" : "not_started",
    });
    return {
      ok: false,
      stageKey,
      status: stageRow.outputMd ? "draft" : "not_started",
      outputMd: stageRow.outputMd ?? "",
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

// --- Prompt assembly ---------------------------------------------------------

function buildSystem(skillMd: string, learningsMd: string, examplesMd: string) {
  const blocks: { text: string; cache?: boolean }[] = [];
  blocks.push({
    text: `You are an expert direct-response strategist and copywriter producing one deliverable in a live-webinar funnel. You build on the locked context you are given and never contradict it.\n\nVoice rules (always honor):\n${VOICE_RULES}`,
  });
  // Everything after the role line is cacheable (stable across re-runs).
  blocks.push({ text: skillMd, cache: true });
  if (learningsMd.trim()) {
    blocks.push({
      text: `# Overriding rules (learned corrections — these take precedence)\n${learningsMd}`,
      cache: true,
    });
  }
  if (examplesMd.trim()) {
    blocks.push({
      text: `# Quality bar (reference examples — match this level, do not copy)\n${examplesMd}`,
      cache: true,
    });
  }
  return blocks;
}

function priorApprovedContext(data: ProjectWithStages): string {
  // Every approved prior stage's output, locked. Skip intake (already injected
  // separately) and brand-kit (structured data, injected where relevant).
  const parts: string[] = [];
  for (const s of data.stages) {
    if (s.status !== "approved") continue;
    if (s.stageKey === "intake" || s.stageKey === "brand-kit") continue;
    if (!s.outputMd) continue;
    const def = STAGE_BY_KEY[s.stageKey];
    parts.push(`## ${def?.label ?? s.stageKey}\n\n${s.outputMd}`);
  }
  return parts.join("\n\n---\n\n");
}

function buildUser(
  data: ProjectWithStages,
  def: StageDef,
  feedback: string | undefined,
  priorOutput: string | null,
): string {
  const sections: string[] = [];
  sections.push(`Client: ${data.project.clientName}`);
  sections.push(`\n# Client intake (source of truth)\n${data.intake?.rawText ?? "(none)"}`);

  const prior = priorApprovedContext(data);
  if (prior) {
    sections.push(
      `\n# Prior approved stages — locked context, build on them, do not rewrite\n${prior}`,
    );
  }

  if (feedback && feedback.trim()) {
    sections.push(
      `\n# Revision request\nThe previous draft was rejected. Apply this feedback precisely, keep what worked:\n${feedback.trim()}`,
    );
    if (priorOutput) {
      sections.push(`\n# Previous draft to revise\n${priorOutput}`);
    }
  }

  sections.push(
    `\n# Task\nProduce the ${def.label} now. Output the deliverable directly as markdown, no preamble, no fences.`,
  );
  return sections.join("\n");
}

// --- Prose stages ------------------------------------------------------------

async function runProse(
  data: ProjectWithStages,
  def: StageDef,
  stageRow: Stage,
  feedback: string | undefined,
  operatorId: string | null | undefined,
): Promise<RunResult> {
  if (!def.skillKey) throw new Error(`Stage ${def.key} has no skill`);
  const skill = await getSkill(def.skillKey);
  if (!skill) throw new Error(`Skill not seeded: ${def.skillKey}. Run npm run seed:skills.`);

  const system = buildSystem(skill.skillMd, skill.learningsMd, skill.examplesMd);
  const baseUser = buildUser(data, def, feedback, stageRow.outputMd);

  let text: string;
  let score: GateScore | null = null;
  let attempts = 1;

  if (VOICE_GATED_STAGES.has(def.key)) {
    const result = await runWithGate({
      stageLabel: def.label,
      userIntent: def.description,
      maxAttempts: MAX_GATE_ATTEMPTS,
      generate: async (retryFeedback) => {
        const user = retryFeedback
          ? `${baseUser}\n\n# Reviewer feedback to address\n${retryFeedback}`
          : baseUser;
        const { text } = await generate({ system, user, maxTokens: 8000 });
        return stripFences(text);
      },
    });
    text = result.text;
    score = result.score;
    attempts = result.attempts;
  } else {
    const { text: raw } = await generate({ system, user: baseUser, maxTokens: 8000 });
    text = stripFences(raw);
  }

  return finalize(stageRow, def, { outputMd: text, score, attempts }, feedback, operatorId);
}

// --- Brand kit (no LLM) ------------------------------------------------------

async function runBrandKit(
  data: ProjectWithStages,
  stageRow: Stage,
  feedback: string | undefined,
  operatorId: string | null | undefined,
): Promise<RunResult> {
  const url = extractUrl(feedback, data.intake?.rawText);
  if (!url) {
    throw new Error(
      "No URL found. Paste the client's website URL into the feedback box and run again.",
    );
  }
  const brandKit = await scrapeBrandKit(url);
  const md = brandKitToMarkdown(brandKit);

  await archiveRevision(stageRow, feedback ?? null, operatorId ?? null);
  await saveStageOutput(stageRow.id, {
    status: "draft",
    outputMd: md,
    outputMeta: { brandKit },
    draftMd: stageRow.draftMd ?? md,
    scoreJson: null,
    gatePassed: false,
    gateAttempts: 0,
  });

  return { ok: true, stageKey: stageRow.stageKey, status: "draft", outputMd: md, score: null };
}

// --- Slides (JSON -> pptx) ---------------------------------------------------

async function runSlides(
  data: ProjectWithStages,
  def: StageDef,
  stageRow: Stage,
  feedback: string | undefined,
  operatorId: string | null | undefined,
): Promise<RunResult> {
  const system = [{ text: SLIDES_SYSTEM_PROMPT, cache: true }];
  const baseUser = buildUser(data, def, feedback, stageRow.outputMd);

  const { data: parsed } = await generateJson<SlideDeck>({
    system,
    user: baseUser,
    maxTokens: 8000,
  });
  if (!isValidDeck(parsed)) throw new Error("Model did not return a valid SlideDeck with slides.");

  // Inject the approved brand kit, if any.
  const brandStage = data.stages.find((s) => s.stageKey === "brand-kit");
  const brandKit = (brandStage?.outputMeta as { brandKit?: BrandKit } | null)?.brandKit;
  const deck: SlideDeck = {
    ...parsed,
    clientName: parsed.clientName || data.project.clientName,
    brandKit: brandKit ?? parsed.brandKit,
    accentHex: brandKit?.accentColor ?? brandKit?.primaryColor ?? parsed.accentHex,
  };

  const { url: pptxUrl, slideCount } = await renderDeck(deck);

  const summary = [
    `# ${deck.title}`,
    ``,
    `Webinar slide deck, ${slideCount} slides, brand-matched${brandKit?.sourceUrl ? ` to ${brandKit.sourceUrl}` : ""}.`,
    ``,
    `**[Download the .pptx](${pptxUrl})**`,
    ``,
    `## Slide outline`,
    ...deck.slides.map((s, i) => `${i + 1}. \`${s.type}\` — ${slideTitle(s)}`),
  ].join("\n");

  await archiveRevision(stageRow, feedback ?? null, operatorId ?? null);
  await saveStageOutput(stageRow.id, {
    status: "draft",
    outputMd: summary,
    outputMeta: { pptxUrl, deck },
    draftMd: stageRow.draftMd ?? summary,
    scoreJson: null,
    gatePassed: false,
    gateAttempts: 0,
  });

  return { ok: true, stageKey: def.key, status: "draft", outputMd: summary, score: null };
}

function slideTitle(s: SlideDeck["slides"][number]): string {
  const anyS = s as Record<string, unknown>;
  return (
    (anyS.title as string) ||
    (anyS.heading as string) ||
    (anyS.headline as string) ||
    (anyS.label as string) ||
    (anyS.stat as string) ||
    (anyS.subject as string) ||
    ""
  );
}

// --- Shared finalize for prose stages ---------------------------------------

async function finalize(
  stageRow: Stage,
  def: StageDef,
  out: { outputMd: string; score: GateScore | null; attempts: number },
  feedback: string | undefined,
  operatorId: string | null | undefined,
): Promise<RunResult> {
  await archiveRevision(stageRow, feedback ?? null, operatorId ?? null);
  await saveStageOutput(stageRow.id, {
    status: "draft",
    outputMd: out.outputMd,
    draftMd: stageRow.draftMd ?? out.outputMd,
    scoreJson: out.score,
    gatePassed: out.score ? out.score.passed : false,
    gateAttempts: out.attempts,
  });
  return {
    ok: true,
    stageKey: def.key,
    status: "draft",
    outputMd: out.outputMd,
    score: out.score,
  };
}
