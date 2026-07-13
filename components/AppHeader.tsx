import Link from "next/link";
import { theme } from "@/theme/tokens";
import { SyncKnowledgeButton } from "@/components/SyncKnowledgeButton";

/**
 * App chrome. The name comes from theme.appName (NEXT_PUBLIC_APP_NAME). Drop a
 * logo at /public/logo.svg and it will show here — rebranding is env + tokens.
 */
export function AppHeader() {
  return (
    <header className="border-b border-[var(--border)] bg-[var(--surface)]">
      <div className="mx-auto max-w-5xl px-6 py-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          <span
            className="inline-block h-5 w-5 rounded-[4px]"
            style={{ background: theme.color.accent }}
            aria-hidden
          />
          <span className="font-[family-name:var(--font-display)] text-base font-semibold">
            {theme.appName}
          </span>
        </Link>
        <div className="flex items-center gap-5">
          <SyncKnowledgeButton />
          <Link
            href="/new"
            className="text-sm text-[var(--text-muted)] hover:text-[var(--text)]"
          >
            + New
          </Link>
        </div>
      </div>
    </header>
  );
}
