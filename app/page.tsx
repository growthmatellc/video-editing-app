import Link from "next/link";
import { listProjects } from "@/lib/project-store";
import { WEBINAR_PIPELINE } from "@/lib/pipeline";
import { theme } from "@/theme/tokens";
import { StageStrip } from "@/components/StageStrip";
import { AppHeader } from "@/components/AppHeader";

export const dynamic = "force-dynamic";

const TOTAL = WEBINAR_PIPELINE.length;

export default async function HomePage() {
  let projects: Awaited<ReturnType<typeof listProjects>> = [];
  let dbError: string | null = null;
  try {
    projects = await listProjects();
  } catch (err) {
    dbError = err instanceof Error ? err.message : String(err);
  }

  return (
    <div className="min-h-screen">
      <AppHeader />
      <main className="mx-auto max-w-5xl px-6 py-10">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-[family-name:var(--font-display)] font-semibold">
              Projects
            </h1>
            <p className="text-[var(--text-muted)] text-sm mt-1">
              One project per client webinar funnel.
            </p>
          </div>
          <Link
            href="/new"
            className="rounded-[var(--radius)] px-4 py-2 text-sm font-medium"
            style={{ background: theme.color.accent, color: theme.color.accentText }}
          >
            New project
          </Link>
        </div>

        {dbError ? (
          <div className="rounded-[var(--radius)] border border-[var(--warn)] bg-[var(--surface)] p-5 text-sm">
            <p className="font-medium text-[var(--warn)] mb-1">Database not reachable</p>
            <p className="text-[var(--text-muted)]">
              Set <code>DATABASE_URL</code> in <code>.env</code>, then run{" "}
              <code>npm run db:push</code> and <code>npm run seed:skills</code>.
            </p>
            <p className="text-[var(--text-muted)] mt-2 font-mono text-xs">{dbError}</p>
          </div>
        ) : projects.length === 0 ? (
          <div className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-10 text-center">
            <p className="text-[var(--text-muted)]">No projects yet.</p>
            <Link
              href="/new"
              className="inline-block mt-4 rounded-[var(--radius)] px-4 py-2 text-sm font-medium"
              style={{ background: theme.color.accent, color: theme.color.accentText }}
            >
              Create your first project
            </Link>
          </div>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2">
            {projects.map(({ project, stages }) => {
              const byKey = new Map(stages.map((s) => [s.stageKey, s]));
              const strip = WEBINAR_PIPELINE.map((def) => ({
                stageKey: def.key,
                stageOrder: def.order,
                status: byKey.get(def.key)?.status ?? ("not_started" as const),
              }));
              const approved = strip.filter((s) => s.status === "approved").length;
              const percent = Math.round((approved / TOTAL) * 100);
              return (
                <li key={project.id}>
                  <Link
                    href={`/${project.id}`}
                    className="block rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-5 hover:border-[var(--accent)] transition-colors"
                  >
                    <div className="flex items-baseline justify-between">
                      <h2 className="font-[family-name:var(--font-display)] text-lg font-semibold">
                        {project.clientName}
                      </h2>
                      <span className="text-xs text-[var(--text-muted)] capitalize">
                        {project.status.replace("_", " ")}
                      </span>
                    </div>
                    <StageStrip stages={strip} className="mt-4" />
                    <div className="mt-3 flex items-center justify-between text-xs text-[var(--text-muted)]">
                      <span>
                        {approved} / {TOTAL} approved
                      </span>
                      <span>{percent}%</span>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </main>
    </div>
  );
}
