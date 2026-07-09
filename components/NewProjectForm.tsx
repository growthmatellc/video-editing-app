"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { theme } from "@/theme/tokens";
import type { ClientOption } from "@/lib/project-store";

export function NewProjectForm({ clients }: { clients: ClientOption[] }) {
  const router = useRouter();
  const [clientSlug, setClientSlug] = useState("");
  const [clientName, setClientName] = useState("");
  const [rawText, setRawText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function onPickClient(slug: string) {
    setClientSlug(slug);
    const picked = clients.find((c) => c.slug === slug);
    // Auto-fill the project name from the client, unless the operator already typed one.
    if (picked && (!clientName.trim() || clients.some((c) => c.displayName === clientName))) {
      setClientName(picked.displayName);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ clientName, rawText, clientSlug: clientSlug || undefined }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Failed to create project");
      router.push(`/${data.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  const picked = clients.find((c) => c.slug === clientSlug);

  return (
    <form onSubmit={submit} className="space-y-6">
      <div>
        <label className="block text-sm font-medium mb-2">Client</label>
        <select
          value={clientSlug}
          onChange={(e) => onPickClient(e.target.value)}
          className="w-full rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
        >
          <option value="">— None (ad-hoc project) —</option>
          {clients.map((c) => (
            <option key={c.slug} value={c.slug}>
              {c.displayName}
              {c.vertical ? ` · ${c.vertical}` : ""}
            </option>
          ))}
        </select>
        <p className="text-xs text-[var(--text-muted)] mt-2">
          {picked
            ? "This client's info, style guide, and retired-term rules will be loaded as locked context into every stage."
            : "Pick a client from the knowledge base to auto-load their brand, voice, and offer context — or leave blank for an ad-hoc project."}
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">Project name</label>
        <input
          value={clientName}
          onChange={(e) => setClientName(e.target.value)}
          required
          placeholder="Acme Coaching — Spring Webinar"
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
          {picked
            ? "Client context is loaded automatically — use this box for anything webinar-specific (this launch's angle, dates, promo)."
            : "The more specific, the better every downstream stage will be. Include the site URL so the Brand Kit can scrape it."}
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
  );
}
