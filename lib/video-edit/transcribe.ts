/**
 * Word-level transcription. A key is optional: with none, the stage still cuts
 * silences and asks the operator to paste a timestamped transcript (or set a key)
 * before fillers and retakes can be detected.
 *
 * Auto order is Deepgram, then AssemblyAI, then OpenAI Whisper — Deepgram is
 * first because it returns word times and keeps filler words.
 */
import { readFile } from "node:fs/promises";
import type { TranscriptWord } from "./types";

export type TranscriptProvider = "deepgram" | "assemblyai" | "openai";

export function configuredProvider(): TranscriptProvider | null {
  const choice = (process.env.TRANSCRIPTION_PROVIDER ?? "auto").trim().toLowerCase();
  const has: Record<TranscriptProvider, boolean> = {
    deepgram: Boolean(process.env.DEEPGRAM_API_KEY),
    assemblyai: Boolean(process.env.ASSEMBLYAI_API_KEY),
    openai: Boolean(process.env.OPENAI_API_KEY),
  };
  if (choice === "deepgram" || choice === "assemblyai" || choice === "openai") {
    return has[choice] ? choice : null;
  }
  if (has.deepgram) return "deepgram";
  if (has.assemblyai) return "assemblyai";
  if (has.openai) return "openai";
  return null;
}

export function transcriptionMissingMessage(): string {
  const choice = (process.env.TRANSCRIPTION_PROVIDER ?? "auto").trim().toLowerCase();
  if (choice === "deepgram" || choice === "assemblyai" || choice === "openai") {
    const env =
      choice === "deepgram" ? "DEEPGRAM_API_KEY" : choice === "assemblyai" ? "ASSEMBLYAI_API_KEY" : "OPENAI_API_KEY";
    return `TRANSCRIPTION_PROVIDER is ${choice}, but ${env} is not set. Paste a timestamped transcript, or set the key. Silences can still be cut without it.`;
  }
  return "No transcription key is set. Paste a timestamped transcript, or set DEEPGRAM_API_KEY, ASSEMBLYAI_API_KEY, or OPENAI_API_KEY. Silences can still be cut without it. Fillers and retakes need word times.";
}

const MAX_BYTES = 100 * 1024 * 1024;

export async function transcribeFile(opts: {
  filePath: string;
  fileName: string;
  contentType: string;
}): Promise<{ words: TranscriptWord[]; provider: TranscriptProvider }> {
  const provider = configuredProvider();
  if (!provider) throw new Error(transcriptionMissingMessage());
  const bytes = await readFile(opts.filePath);
  if (bytes.length > MAX_BYTES) {
    throw new Error(
      `This file is ${Math.round(bytes.length / (1024 * 1024))}MB. Automatic transcription sends at most 100MB. Paste a timestamped transcript instead.`,
    );
  }
  if (provider === "deepgram") return { words: await deepgram(bytes, opts.contentType), provider };
  if (provider === "assemblyai") return { words: await assembly(bytes), provider };
  return { words: await openai(bytes, opts.fileName), provider };
}

async function deepgram(bytes: Buffer, contentType: string): Promise<TranscriptWord[]> {
  const url = new URL("https://api.deepgram.com/v1/listen");
  url.searchParams.set("model", "nova-2");
  url.searchParams.set("punctuate", "true");
  url.searchParams.set("smart_format", "true");
  url.searchParams.set("filler_words", "true");
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Token ${process.env.DEEPGRAM_API_KEY}`,
      "Content-Type": contentType || "video/mp4",
    },
    body: new Uint8Array(bytes),
  });
  if (!res.ok) throw new Error(`Deepgram returned ${res.status}: ${await safeText(res)}`);
  const json = (await res.json()) as {
    results?: { channels?: { alternatives?: { words?: { word?: string; punctuated_word?: string; start?: number; end?: number }[] }[] }[] };
  };
  const words = json.results?.channels?.[0]?.alternatives?.[0]?.words ?? [];
  return words
    .map((w) => ({
      text: (w.punctuated_word || w.word || "").trim(),
      start: Number(w.start),
      end: Number(w.end),
    }))
    .filter((w) => w.text && w.end > w.start);
}

async function assembly(bytes: Buffer): Promise<TranscriptWord[]> {
  const key = process.env.ASSEMBLYAI_API_KEY ?? "";
  const uploaded = await fetch("https://api.assemblyai.com/v2/upload", {
    method: "POST",
    headers: { authorization: key },
    body: new Uint8Array(bytes),
  });
  if (!uploaded.ok) throw new Error(`AssemblyAI upload returned ${uploaded.status}: ${await safeText(uploaded)}`);
  const { upload_url } = (await uploaded.json()) as { upload_url?: string };
  if (!upload_url) throw new Error("AssemblyAI did not return an upload URL.");

  const created = await fetch("https://api.assemblyai.com/v2/transcript", {
    method: "POST",
    headers: { authorization: key, "content-type": "application/json" },
    body: JSON.stringify({ audio_url: upload_url, disfluencies: true }),
  });
  if (!created.ok) throw new Error(`AssemblyAI returned ${created.status}: ${await safeText(created)}`);
  const job = (await created.json()) as { id?: string };
  if (!job.id) throw new Error("AssemblyAI did not return a transcript id.");

  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    await sleep(2000);
    const poll = await fetch(`https://api.assemblyai.com/v2/transcript/${job.id}`, {
      headers: { authorization: key },
    });
    if (!poll.ok) throw new Error(`AssemblyAI poll returned ${poll.status}: ${await safeText(poll)}`);
    const body = (await poll.json()) as {
      status?: string;
      error?: string;
      words?: { text?: string; start?: number; end?: number }[];
    };
    if (body.status === "error") throw new Error(body.error || "AssemblyAI failed.");
    if (body.status === "completed") {
      return (body.words ?? [])
        .map((w) => ({
          text: (w.text || "").trim(),
          start: Number(w.start) / 1000,
          end: Number(w.end) / 1000,
        }))
        .filter((w) => w.text && w.end > w.start);
    }
  }
  throw new Error("AssemblyAI did not finish within 2 minutes.");
}

async function openai(bytes: Buffer, fileName: string): Promise<TranscriptWord[]> {
  const model = process.env.OPENAI_TRANSCRIBE_MODEL || "whisper-1";
  const form = new FormData();
  form.append("file", new Blob([new Uint8Array(bytes)]), fileName);
  form.append("model", model);
  form.append("response_format", "verbose_json");
  form.append("timestamp_granularities[]", "word");
  const res = await fetch("https://api.openai.com/v1/audio/transcriptions", {
    method: "POST",
    headers: { Authorization: `Bearer ${process.env.OPENAI_API_KEY}` },
    body: form,
  });
  if (!res.ok) throw new Error(`OpenAI transcription returned ${res.status}: ${await safeText(res)}`);
  const json = (await res.json()) as { words?: { word?: string; start?: number; end?: number }[] };
  return (json.words ?? [])
    .map((w) => ({ text: (w.word || "").trim(), start: Number(w.start), end: Number(w.end) }))
    .filter((w) => w.text && w.end > w.start);
}

async function safeText(res: Response): Promise<string> {
  const text = await res.text();
  return text.slice(0, 300);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
