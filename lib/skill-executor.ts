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
import { reviewDraft, PASS_THRESHOLD, type GateScore } from "./gate";
import { auditCopy, type AuditResult } from "./audit";
import { auditBundle, hardViolationFeedback, RICH_ASSET_TYPES, type CopyAuditReport } from "./copy-auditor";
import { VOICE_RULES } from "./voice-rules";
import { STAGE_BY_KEY, STAGE_ASSET_TYPE, VOICE_GATED_STAGES, type StageDef } from "./pipeline";
import {
  getProject,
  getStage,
  getSkill,
  getClient,
  ensureStage,
  archiveRevision,
  saveStageOutput,
  buildIntake,
  type ProjectWithStages,
} from "./project-store";
import type { Client, Intake } from "./db/schema";
import { scrapeBrandKit, brandKitToMarkdown, extractUrl, parseColorOverrides } from "./brand-kit";
import {
  SLIDES_SYSTEM_PROMPT,
  isValidDeck,
  type SlideDeck,
  type BrandKit,
} from "./slide-deck-schema";
import { renderDeck } from "./slide-renderer";
import type { Stage } from "./db/schema";

const MAX_GATE_ATTEMPTS = 2;

// Per-stage output-token budget. Short deliverables (a title, a few SMS) don't
// need 16k tokens — capping them keeps generation fast and within the function
// time limit. Long sequences (full email/call sequences, scripts) keep headroom.
const STAGE_MAX_TOKENS: Record<string, number> = {
  "webinar-title": 4000,
  "sms-sequences": 4000,
  "registration-page": 6000,
  "webinar-blueprint": 8000,
  "offer-stack": 8000,
  "ad-creative": 8000,
  "tracking-setup": 8000,
  "image-ads": 10000,
  "objection-qa-bank": 10000,
  "funnel-spec": 10000,
  "email-sequences": 16000,
  "call-nurture": 16000,
  "webinar-script": 16000,
  "designer-handoff": 16000,
  // The deck depth benchmark (slide-building/SKILL.md) is ~55-70 live slides, each
  // its own JSON object. 8k truncates that to a fraction of the anchors' depth.
  "webinar-slides": 32000,
};
function outputBudget(stageKey: string): number {
  return STAGE_MAX_TOKENS[stageKey] ?? 8000;
}

export interface RunResult {
  ok: boolean;
  stageKey: string;
  status: Stage["status"];
  outputMd: string;
  score?: GateScore | null;
  audit?: AuditResult | null;
  error?: string;
}

export async function runStage(
  projectId: string,
  stageKey: string,
  feedback?: string,
  operatorId?: string | null,
  opts?: { chainDrafts?: boolean },
): Promise<RunResult> {
  const def = STAGE_BY_KEY[stageKey];
  if (!def) throw new Error(`Unknown stage: ${stageKey}`);
  if (def.runnable === false) throw new Error(`Stage ${stageKey} is human-only`);
  const chainDrafts = opts?.chainDrafts ?? false;

  const data = await getProject(projectId);
  if (!data) throw new Error(`Project not found: ${projectId}`);

  // Load the linked knowledge-base client (if any) once; its profile, style
  // guide, and retired-term rules become locked context for every stage.
  const client = data.project.clientSlug ? await getClient(data.project.clientSlug) : null;
  const clientContext = client ? buildClientContext(client) : null;

  // The project's own intake wins (it may carry launch-specific operator notes),
  // but if it's empty we fall back to the linked client's synced onboarding
  // research LIVE — so a project linked to a known client always has knowledge to
  // build from, even when its intake snapshot was never populated (e.g. the client
  // was synced after the project was created). This also always uses the latest
  // research rather than a stale snapshot.
  const projectIntake = data.intake?.rawText?.trim() ?? "";
  const effectiveIntake = projectIntake || buildIntake(client, "");
  if (!effectiveIntake.trim()) {
    throw new Error(
      `Project ${projectId} has no intake and ` +
        (client
          ? `client "${client.slug}" has no synced onboarding research (run npm run sync:knowledge)`
          : `is not linked to a client`) +
        `. Add intake text or link a synced client. Refusing to generate ${stageKey} from nothing.`,
    );
  }
  // Make downstream prompt assembly see the effective intake.
  data.intake = {
    ...(data.intake ?? { projectId, fields: {}, submittedAt: new Date() }),
    rawText: effectiveIntake,
  } as Intake;

  // Auto-create the row if this stage was added to the pipeline after the
  // project was created, so new stages work on existing projects.
  const stageRow = (await getStage(projectId, stageKey)) ?? (await ensureStage(projectId, def));

  // Mark running.
  await saveStageOutput(stageRow.id, { status: "running" });

  try {
    if (stageKey === "brand-kit") {
      return await runBrandKit(data, stageRow, feedback, operatorId);
    }
    if (stageKey === "webinar-slides") {
      return await runSlides(data, def, stageRow, feedback, operatorId, clientContext, chainDrafts);
    }
    return await runProse(data, def, stageRow, feedback, operatorId, clientContext, chainDrafts, client);
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

const PROSE_ROLE = `You are an expert direct-response strategist and copywriter producing one deliverable in a live-webinar funnel. You build on the locked context you are given and never contradict it.\n\nVoice rules (always honor):\n${VOICE_RULES}`;

/**
 * `lead` is the opening role block. Prose stages use PROSE_ROLE; the slide stage
 * passes SLIDES_SYSTEM_PROMPT so its JSON output contract comes first. Everything
 * after it (method, learnings, anchors) is identical either way — the slide deck
 * needs the anchors and learned corrections just as much as the prose stages do.
 */
function buildSystem(
  skillMd: string,
  learningsMd: string,
  examplesMd: string,
  kbSkillMd = "",
  lead: string = PROSE_ROLE,
) {
  // The lead stays uncached: the 4 blocks below already use Anthropic's max of 4
  // cache_control breakpoints, and the lead sits inside the cached prefix regardless.
  const blocks: { text: string; cache?: boolean }[] = [];
  blocks.push({ text: lead });
  // Everything after the role line is cacheable (stable across re-runs).
  blocks.push({ text: `# Stage brief — what to produce\n${skillMd}`, cache: true });
  // GrowthMate craft standard (method + workflows) mapped to this stage.
  if (kbSkillMd.trim()) {
    blocks.push({
      text:
        `# GrowthMate craft standard — the AUTHORITATIVE method for this deliverable.\n` +
        `Follow this method, workflow, cadence, and structure exactly. Where it conflicts ` +
        `with the stage brief above, THIS wins.\n\n${kbSkillMd}`,
      cache: true,
    });
  }
  if (learningsMd.trim()) {
    blocks.push({
      text:
        `# Learned corrections — highest precedence, these override everything above.\n${learningsMd}`,
      cache: true,
    });
  }
  if (examplesMd.trim()) {
    blocks.push({
      text:
        `# Best-performer anchors — MIRROR THESE.\n` +
        `These are the winning, proven formats. Reproduce their STRUCTURE, sequence, ` +
        `section order, cadence, and length — e.g. if an anchor is an 8-email + 4-SMS ` +
        `sequence on a set day-by-day cadence with an escalating final-hour push, your ` +
        `output has the same shape. Re-skin the voice, facts, names, mechanism, and offer ` +
        `from the client context; never copy an anchor's specific client details.\n\n${examplesMd}`,
      cache: true,
    });
  }
  return blocks;
}

/**
 * Every prior stage's output, locked, as context for this one. Skips intake (injected
 * separately) and brand-kit (structured data, injected where relevant).
 *
 * `chainDrafts` exists for the unattended full-pipeline run. Normally only *approved*
 * stages carry forward — the human gate is what promotes a draft into locked context.
 * But a full run generates 17 stages back-to-back with nobody there to approve, so
 * without this every stage after the first would generate blind: the script wouldn't
 * know the blueprint, the slides wouldn't know the script. That defeats the chain,
 * which is the entire point of the pipeline.
 *
 * The alternative — auto-approving each stage so the next one inherits it — would be
 * worse: it marks work "human-approved" that no human has read. So an automated run
 * chains on the latest output instead, and every stage still lands as a `draft`
 * awaiting real review. Drafts are labelled as such in the prompt so a stage knows
 * its foundation is unreviewed and may yet change.
 */
function priorApprovedContext(data: ProjectWithStages, chainDrafts = false): string {
  const parts: string[] = [];
  for (const s of data.stages) {
    const usable = s.status === "approved" || (chainDrafts && s.status === "draft");
    if (!usable) continue;
    if (s.stageKey === "intake" || s.stageKey === "brand-kit") continue;
    if (!s.outputMd) continue;
    const def = STAGE_BY_KEY[s.stageKey];
    const tag = s.status === "approved" ? "APPROVED" : "DRAFT — not yet human-reviewed";
    parts.push(`## ${def?.label ?? s.stageKey} (${tag})\n\n${s.outputMd}`);
  }
  return parts.join("\n\n---\n\n");
}

function buildUser(
  data: ProjectWithStages,
  def: StageDef,
  feedback: string | undefined,
  priorOutput: string | null,
  clientContext: string | null,
  chainDrafts = false,
): string {
  const sections: string[] = [];
  sections.push(`Client: ${data.project.clientName}`);
  if (clientContext) {
    sections.push(`\n${clientContext}`);
  }
  sections.push(`\n# Client intake (source of truth)\n${data.intake?.rawText ?? "(none)"}`);

  const prior = priorApprovedContext(data, chainDrafts);
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

/**
 * Turn a knowledge-base client into a locked-context block: profile (info.json),
 * banned phrases, style guide, and retired-terminology find/replace rules.
 */
function buildClientContext(client: Client): string {
  const parts: string[] = [
    `# Client context — LOCKED source of truth for ${client.displayName}\n` +
      `This overrides anything generic. Match this client's brand, voice, offer naming, and mechanism exactly.`,
  ];

  if (client.infoJson) {
    parts.push(
      `## Client profile (info.json)\n\`\`\`json\n${JSON.stringify(client.infoJson, null, 2)}\n\`\`\``,
    );
    const banned = (client.infoJson as { banned_phrases?: unknown }).banned_phrases;
    if (Array.isArray(banned) && banned.length) {
      parts.push(
        `## Banned phrases (never use these)\n${banned.map((b) => `- ${String(b)}`).join("\n")}`,
      );
    }
  }

  if (client.styleGuideMd && client.styleGuideMd.trim()) {
    parts.push(
      `## Style guide (voice, signoff, mechanism naming, structural preferences — honor every entry)\n${client.styleGuideMd.trim()}`,
    );
  }

  const termRules = formatTermMappings(client.termMappingsJson);
  if (termRules) {
    parts.push(
      `## Retired terminology (ALWAYS replace retired → current, never emit a retired term)\n${termRules}`,
    );
  }

  return parts.join("\n\n");
}

function formatTermMappings(raw: unknown): string | null {
  if (!raw || typeof raw !== "object") return null;
  const mappings = (raw as { mappings?: unknown }).mappings;
  if (!Array.isArray(mappings) || mappings.length === 0) return null;
  const lines = mappings
    .map((m) => {
      const e = m as { retired_term?: string; current_term?: string; context?: string };
      if (!e.retired_term || !e.current_term) return null;
      const ctx = e.context ? ` — ${e.context}` : "";
      return `- "${e.retired_term}" → "${e.current_term}"${ctx}`;
    })
    .filter(Boolean);
  return lines.length ? lines.join("\n") : null;
}

// --- Prose stages ------------------------------------------------------------

async function runProse(
  data: ProjectWithStages,
  def: StageDef,
  stageRow: Stage,
  feedback: string | undefined,
  operatorId: string | null | undefined,
  clientContext: string | null,
  chainDrafts = false,
  client: Client | null = null,
): Promise<RunResult> {
  if (!def.skillKey) throw new Error(`Stage ${def.key} has no skill`);
  const skill = await getSkill(def.skillKey);
  if (!skill) throw new Error(`Skill not seeded: ${def.skillKey}. Run npm run seed:skills.`);

  const system = buildSystem(skill.skillMd, skill.learningsMd, skill.examplesMd, skill.kbSkillMd);
  const baseUser = buildUser(data, def, feedback, stageRow.outputMd, clientContext, chainDrafts);

  // Rules for the LLM audit (stages with no deterministic asset_type) = the
  // skill's method + learned corrections + craft rules/anchors. These carry the
  // concrete checkable rules (e.g. the webinar-title "no em dashes" hard-stop).
  const rules = [skill.skillMd, skill.kbSkillMd, skill.learningsMd, skill.examplesMd]
    .filter((s) => s && s.trim())
    .join("\n\n");

  const { text, score, audit, attempts } = await generateWithGates({
    def,
    client,
    rules,
    maxAttempts: MAX_GATE_ATTEMPTS,
    generate: async (retryFeedback) => {
      const user = retryFeedback
        ? `${baseUser}\n\n# Reviewer feedback to address\n${retryFeedback}`
        : baseUser;
      const { text } = await generate({ system, user, maxTokens: outputBudget(def.key) });
      return stripFences(text);
    },
  });

  return finalize(stageRow, def, { outputMd: text, score, attempts, audit }, feedback, operatorId);
}

/**
 * The unified quality gate. Each attempt: generate a draft, then run every gate
 * that applies to the stage — the editorial voice reviewer (voice-gated stages),
 * and EITHER the deterministic copy auditor (stages mapped to an asset_type) OR
 * the LLM rules audit (everything else, e.g. webinar-title). "Blocking" = any
 * voice HIGH, any deterministic HARD, or any LLM-audit HIGH violation. When
 * blocked and attempts remain, it folds the combined feedback into the prompt and
 * REGENERATES automatically — no human in the loop. Issues that survive
 * maxAttempts land on the draft, flagged.
 *
 * Every prose stage has at least the LLM audit, so violations always drive a
 * rewrite; the deterministic auditor supersedes it wherever an asset_type exists.
 */
async function generateWithGates(opts: {
  def: StageDef;
  client: Client | null;
  rules: string;
  maxAttempts: number;
  generate: (retryFeedback?: string) => Promise<string>;
}): Promise<{ text: string; score: GateScore | null; audit: AuditResult | null; attempts: number }> {
  const { def, client, rules, maxAttempts, generate } = opts;
  const voiceGated = VOICE_GATED_STAGES.has(def.key);
  const assetType = STAGE_ASSET_TYPE[def.key] ?? null;

  let text = "";
  let score: GateScore | null = null;
  let audit: AuditResult | null = null;
  let retryFeedback: string | undefined;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    text = await generate(retryFeedback);

    const [voiceScore, deterministic] = await Promise.all([
      voiceGated
        ? reviewDraft({ stageLabel: def.label, userIntent: def.description, text })
        : Promise.resolve(null),
      assetType ? auditBundle({ markdown: text, assetType, client }) : Promise.resolve(null),
    ]);

    // Rich asset types (emails, title) have deep per-asset code rules — the
    // deterministic auditor is authoritative and the LLM audit is redundant.
    // Thin/unmapped stages have only the universal code rules, so the LLM audit
    // runs alongside as a second BLOCKING gate (both drive rewrites) until their
    // per-asset rules are authored. A downed auditor also falls back to the LLM.
    const detAvailable = !!deterministic && deterministic.available;
    const isRich = detAvailable && !!assetType && RICH_ASSET_TYPES.has(assetType);
    const llmAudit: AuditResult | null = isRich
      ? null
      : await auditCopy({ stageLabel: def.label, rules, output: text });

    score = voiceScore;
    audit = mergeAudits(detAvailable ? (deterministic as CopyAuditReport) : null, llmAudit);

    const voiceHighs = voiceScore ? voiceScore.violations.filter((v) => v.severity === "high") : [];
    const detHard = detAvailable ? (deterministic as CopyAuditReport).hardViolations : [];
    const llmHighs = llmAudit ? llmAudit.violations.filter((v) => v.severity === "high") : [];

    const voiceCleared = !voiceScore || (voiceScore.passed && voiceScore.score >= PASS_THRESHOLD);
    const blocked = voiceHighs.length > 0 || detHard.length > 0 || llmHighs.length > 0;
    if ((!blocked && voiceCleared) || attempt === maxAttempts) {
      return { text, score, audit, attempts: attempt };
    }

    const parts: string[] = [];
    if (!voiceCleared && voiceScore) {
      const toFix = voiceHighs.length ? voiceHighs : voiceScore.violations;
      parts.push(
        "Revise to fix these reviewer issues. Keep everything that worked; change only what these notes call out:\n" +
          toFix.map((v) => `- (${v.severity}) ${v.note}`).join("\n"),
      );
    }
    if (detHard.length) parts.push(hardViolationFeedback(deterministic as CopyAuditReport));
    if (llmHighs.length) parts.push(auditRewriteFeedback(llmHighs));
    retryFeedback = parts.join("\n\n");
  }

  return { text, score, audit, attempts: maxAttempts };
}

/** Combine the deterministic and LLM audit reports into one stored result. */
function mergeAudits(a: AuditResult | null, b: AuditResult | null): AuditResult | null {
  if (a && b) {
    return {
      passed: a.passed && b.passed,
      summary: [a.summary, b.summary].filter(Boolean).join(" "),
      violations: [...a.violations, ...b.violations],
    };
  }
  return a ?? b ?? null;
}

/** Rewrite feedback from the LLM rules audit's high-severity violations. */
function auditRewriteFeedback(highs: AuditResult["violations"]): string {
  return (
    "Fix these HARD rule violations from the QC audit. They block shipping — " +
    "correct every one while keeping everything that already complies:\n" +
    highs
      .map((v) => `- [${v.rule}] ${v.evidence ? `“${v.evidence}” ` : ""}→ ${v.fix}`)
      .join("\n")
  );
}

// --- Brand kit (no LLM) ------------------------------------------------------

async function runBrandKit(
  data: ProjectWithStages,
  stageRow: Stage,
  feedback: string | undefined,
  operatorId: string | null | undefined,
): Promise<RunResult> {
  // Reuse the previously-scraped URL so a re-run with only a color override
  // (e.g. "primary teal") still works without re-pasting the site URL.
  const priorKit = (stageRow.outputMeta as { brandKit?: BrandKit } | null)?.brandKit;
  const url = extractUrl(feedback, data.intake?.rawText) ?? priorKit?.sourceUrl;
  if (!url) {
    throw new Error(
      "No URL found. Paste the client's website URL into the feedback box and run again.",
    );
  }
  const scraped = await scrapeBrandKit(url);

  // Operator color overrides from the feedback box win over auto-detect.
  const overrides = parseColorOverrides(feedback, scraped.palette);
  const brandKit: BrandKit = {
    ...scraped,
    primaryColor: overrides.primary ?? scraped.primaryColor,
    accentColor: overrides.accent ?? scraped.accentColor,
  };
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
  clientContext: string | null,
  chainDrafts = false,
): Promise<RunResult> {
  const skill = await getSkill(def.skillKey ?? "webinar-slides");
  // Same knowledge stack as every prose stage — the deck anchors and the learned
  // corrections in slide-building/learnings/insights.md are what hold the output to
  // the best-performer shape (depth, one-idea-per-slide, the Tom deck-craft gates).
  const system = buildSystem(
    skill?.skillMd ?? "",
    skill?.learningsMd ?? "",
    skill?.examplesMd ?? "",
    skill?.kbSkillMd ?? "",
    SLIDES_SYSTEM_PROMPT,
  );
  const baseUser = buildUser(data, def, feedback, stageRow.outputMd, clientContext, chainDrafts);

  const { data: parsed } = await generateJson<SlideDeck>({
    system,
    user: baseUser,
    maxTokens: outputBudget(def.key),
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
  out: { outputMd: string; score: GateScore | null; attempts: number; audit?: AuditResult | null },
  feedback: string | undefined,
  operatorId: string | null | undefined,
): Promise<RunResult> {
  // The audit was already computed inside the gate loop (deterministic auditor
  // for mapped stages, LLM audit otherwise). Store it; do not re-run.
  const audit: AuditResult | null = out.audit ?? null;

  // gatePassed reflects every gate that applied: voice review and/or the audit.
  const gateStates = [
    out.score ? out.score.passed : null,
    audit ? audit.passed : null,
  ].filter((v): v is boolean => v !== null);
  const gatePassed = gateStates.length ? gateStates.every(Boolean) : false;

  await archiveRevision(stageRow, feedback ?? null, operatorId ?? null);
  await saveStageOutput(stageRow.id, {
    status: "draft",
    outputMd: out.outputMd,
    draftMd: stageRow.draftMd ?? out.outputMd,
    scoreJson: out.score,
    auditJson: audit,
    gatePassed,
    gateAttempts: out.attempts,
  });
  return {
    ok: true,
    stageKey: def.key,
    status: "draft",
    outputMd: out.outputMd,
    score: out.score,
    audit,
  };
}
