"use client";

import { useState } from "react";

type State =
  | { kind: "idle" }
  | { kind: "syncing" }
  | { kind: "done"; msg: string }
  | { kind: "error"; msg: string };

export function SyncKnowledgeButton() {
  const [state, setState] = useState<State>({ kind: "idle" });

  async function sync() {
    setState({ kind: "syncing" });
    try {
      const res = await fetch("/api/sync-knowledge", { method: "POST" });
      const data = await res.json();
      if (!res.ok || data.ok === false) {
        throw new Error(data.error ?? "Sync failed");
      }
      setState({
        kind: "done",
        msg: `Synced ${data.stages} stages · ${data.clients} clients`,
      });
      // Refresh the page so any client-list/data changes show.
      setTimeout(() => window.location.reload(), 1200);
    } catch (err) {
      setState({ kind: "error", msg: err instanceof Error ? err.message : String(err) });
    }
  }

  return (
    <div className="flex items-center gap-2">
      {state.kind === "done" && (
        <span className="text-xs text-[var(--ok)]">{state.msg}</span>
      )}
      {state.kind === "error" && (
        <span className="text-xs text-[var(--warn)] max-w-[280px] truncate" title={state.msg}>
          {state.msg}
        </span>
      )}
      <button
        onClick={sync}
        disabled={state.kind === "syncing"}
        title="Pull the latest GrowthMate knowledge from GitHub and sync it into the app"
        className="text-sm text-[var(--text-muted)] hover:text-[var(--text)] disabled:opacity-50"
      >
        {state.kind === "syncing" ? "Syncing…" : "↻ Sync knowledge"}
      </button>
    </div>
  );
}
