// One place that knows about the model + provider. Feature code never imports
// the Anthropic SDK directly — it calls generate() / generateJson() here.
import Anthropic from "@anthropic-ai/sdk";

const model = process.env.LLM_MODEL ?? "claude-opus-4-8";

// Two paths: direct Anthropic, or the Vercel AI Gateway. Pick whichever key is set.
// The gateway speaks the Anthropic Messages API, so the same client works for both;
// only the baseURL and the auth header change.
const gatewayKey = process.env.AI_GATEWAY_API_KEY;
const anthropicKey = process.env.ANTHROPIC_API_KEY;

const client = gatewayKey
  ? new Anthropic({
      apiKey: gatewayKey,
      baseURL: "https://ai-gateway.vercel.sh/v1/anthropic",
    })
  : new Anthropic({ apiKey: anthropicKey });

export interface SystemBlock {
  text: string;
  cache?: boolean;
}

export async function generate(opts: {
  system: SystemBlock[];
  user: string;
  maxTokens?: number;
}): Promise<{ text: string; usage: { input_tokens: number; output_tokens: number } }> {
  if (!gatewayKey && !anthropicKey) {
    throw new Error(
      "No LLM credentials. Set ANTHROPIC_API_KEY or AI_GATEWAY_API_KEY in .env.",
    );
  }

  const res = await client.messages.create({
    model,
    max_tokens: opts.maxTokens ?? 8000,
    system: opts.system.map((b) => ({
      type: "text" as const,
      text: b.text,
      ...(b.cache ? { cache_control: { type: "ephemeral" as const } } : {}),
    })),
    messages: [{ role: "user", content: opts.user }],
  });

  const block = res.content.find((b) => b.type === "text");
  if (!block || block.type !== "text") throw new Error("No text returned");
  return {
    text: block.text.trim(),
    usage: {
      input_tokens: res.usage.input_tokens,
      output_tokens: res.usage.output_tokens,
    },
  };
}

/** Strip accidental ``` fences (optionally language-tagged) the model may wrap output in. */
export function stripFences(text: string): string {
  const trimmed = text.trim();
  const fenced = trimmed.match(/^```[a-zA-Z]*\n([\s\S]*?)\n?```$/);
  return (fenced ? fenced[1] : trimmed).trim();
}

/** Generate and parse a JSON object, tolerating fences and surrounding prose. */
export async function generateJson<T = unknown>(opts: {
  system: SystemBlock[];
  user: string;
  maxTokens?: number;
}): Promise<{ data: T; usage: { input_tokens: number; output_tokens: number } }> {
  const { text, usage } = await generate(opts);
  const cleaned = stripFences(text);
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  const candidate = start >= 0 && end > start ? cleaned.slice(start, end + 1) : cleaned;
  return { data: JSON.parse(candidate) as T, usage };
}

export const LLM_MODEL = model;
