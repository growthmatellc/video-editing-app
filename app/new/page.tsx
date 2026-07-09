import { AppHeader } from "@/components/AppHeader";
import { NewProjectForm } from "@/components/NewProjectForm";
import { listClients, type ClientOption } from "@/lib/project-store";

export const dynamic = "force-dynamic";

export default async function NewProjectPage() {
  let clients: ClientOption[] = [];
  try {
    clients = await listClients();
  } catch {
    // If the DB/clients table isn't reachable, fall back to an ad-hoc-only form.
    clients = [];
  }

  return (
    <div className="min-h-screen">
      <AppHeader />
      <main className="mx-auto max-w-2xl px-6 py-10">
        <h1 className="text-2xl font-[family-name:var(--font-display)] font-semibold">
          New project
        </h1>
        <p className="text-[var(--text-muted)] text-sm mt-1 mb-8">
          Pick a client to load their brand and voice, then add the intake for this
          specific webinar. One intake feeds the entire funnel.
        </p>

        <NewProjectForm clients={clients} />
      </main>
    </div>
  );
}
