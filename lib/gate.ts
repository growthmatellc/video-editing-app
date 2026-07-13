/**
 * The review gate: a generate-score-retry loop that enforces quality on
 * voice-sensitive stages (section 8).
 *
 * The reviewer is generic and brand-free. It judges clarity, specificity,
 * persuasive structure, and the voice rules. It never invents facts and never
 * references any agency.
 */
import { generateJson, REVIEW_MODEL } from "./llm";
import { VOICE_RULES } from "./voice-rules";

export interface Violation {
  severity: "high" | "med" | "low";
  note: string;
}

export interface GateScore {
  passed: boolean;
  score: number; // 0-100
  violations: Violation[];
}

export interface GateResult {
  text: string;
  score: GateScore;
  attempts: number;
}

const PASS_THRESHOLD = 80;

function reviewerSystem(stageLabel: string, userIntent: string): string {
  return `You are a strict editorial reviewer for a single deliverable in a live-webinar funnel.

The deliverable being reviewed: ${stageLabel}.
Its intent: ${userIntent}

Judge it on:
- Clarity: is it direct and unambiguous?
- Specificity: is it tied to the client's actual situation, not generic boilerplate that could belong to any business?
- Persuasive structure: does it do its job in the funnel (promise, belief shift, transition, offer, or action as appropriate)?
- Voice rules compliance:
${VOICE_RULES}

You do not invent facts. You do not reference any agency or brand. You only judge the text in front of you.

Return ONLY a JSON object of this exact shape, no prose, no fences:
{
  "passed": boolean,
  "score": number,            // 0-100 overall quality
  "violations": [             // every concrete problem; [] if clean
    { "severity": "high" | "med" | "low", "note": string }
  ]
}
Mark a violation "high" when it materially breaks the deliverable's job or breaks a voice rule. "passed" should be true only when there are no high-severity violations and the work clears a professional bar.`;
}

/**
 * @param generate produces a draft. On a retry it receives the high-severity
 *   reviewer feedback to fold in.
 */
export async function runWithGate(opts: {
  stageLabel: string;
  userIntent: string;
  maxAttempts: number;
  generate: (retryFeedback?: string) => Promise<string>;
}): Promise<GateResult> {
  const { stageLabel, userIntent, maxAttempts, generate } = opts;

  let lastText = "";
  let lastScore: GateScore = { passed: false, score: 0, violations: [] };
  let retryFeedback: string | undefined;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    lastText = await generate(retryFeedback);

    let score: GateScore;
    try {
      const { data } = await generateJson<GateScore>({
        system: [{ text: reviewerSystem(stageLabel, userIntent), cache: true }],
        user: `Review this draft and return the JSON verdict.\n\n---\n${lastText}\n---`,
        maxTokens: 1500,
        model: REVIEW_MODEL,
      });
      score = {
        passed: !!data.passed,
        score: typeof data.score === "number" ? data.score : 0,
        violations: Array.isArray(data.violations) ? data.violations : [],
      };
    } catch {
      // If the reviewer call fails or returns unparseable JSON, do not block the
      // pipeline: accept the draft but record that it was not scored.
      return {
        text: lastText,
        score: { passed: true, score: 0, violations: [] },
        attempts: attempt,
      };
    }

    lastScore = score;
    const cleared = score.passed && score.score >= PASS_THRESHOLD;
    if (cleared || attempt === maxAttempts) {
      return { text: lastText, score, attempts: attempt };
    }

    const highs = score.violations.filter((v) => v.severity === "high");
    const toFix = highs.length ? highs : score.violations;
    retryFeedback =
      "Revise to fix these reviewer issues. Keep everything that worked; change only what these notes call out:\n" +
      toFix.map((v) => `- (${v.severity}) ${v.note}`).join("\n");
  }

  return { text: lastText, score: lastScore, attempts: maxAttempts };
}
