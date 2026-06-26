"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { theme } from "@/theme/tokens";
import { AppHeader } from "@/components/AppHeader";

export default function NewProjectPage() {
  const router = useRouter();
  const [clientName, setClientName] = useState("");
  const [rawText, setRawText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ clientName, rawText }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Failed to create project");
      router.push(`/${data.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen">
      <AppHeader />
      <main className="mx-auto max-w-2xl px-6 py-10">
        <h1 className="text-2xl font-[family-name:var(--font-display)] font-semibold">
          New project
        </h1>
        <p className="text-[var(--text-muted)] text-sm mt-1 mb-8">
          One intake feeds the entire funnel. Paste everything you know about the
          client, their offer, and their audience.
        </p>

        <form onSubmit={submit} className="space-y-6">
          <div>
            <label className="block text-sm font-medium mb-2">Client name</label>
            <input
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
              required
              placeholder="Acme Coaching"
              className="w-full rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Intake</label>
            <textarea
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              rows={16}
              placeholder={
                "Who is the client and what do they sell?\nWho is the audience and what is their painful status quo?\nWhat is the offer, price, and guarantee?\nWebsite URL (for the brand kit)?\nAny proof, results, or stories?"
              }
              className="w-full rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm leading-relaxed outline-none focus:border-[var(--accent)] font-[family-name:var(--font-body)]"
            />
            <p className="text-xs text-[var(--text-muted)] mt-2">
              The more specific, the better every downstream stage will be. Include the
              site URL so the Brand Kit can scrape it.
            </p>
          </div>

          {error && (
            <p className="text-sm text-[var(--warn)] rounded-[var(--radius)] border border-[var(--warn)] px-3 py-2">
              {error}
            </p>
          )}

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={submitting || !clientName.trim()}
              className="rounded-[var(--radius)] px-4 py-2 text-sm font-medium disabled:opacity-50"
              style={{ background: theme.color.accent, color: theme.color.accentText }}
            >
              {submitting ? "Creating…" : "Create project"}
            </button>
            <button
              type="button"
              onClick={() => router.push("/")}
              className="text-sm text-[var(--text-muted)] hover:text-[var(--text)]"
            >
              Cancel
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
