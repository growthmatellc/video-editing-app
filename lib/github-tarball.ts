/**
 * Download the growthmate-knowledge repo from GitHub as a tarball and extract it
 * to a temp dir, returning the extracted repo root. Used by the in-app
 * "Sync knowledge" button so the deployed app can pull the latest without a local
 * checkout. Requires GITHUB_TOKEN (read access to the private repo).
 */
import { mkdtempSync, readdirSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { x as extractTar } from "tar";

const REPO = process.env.KNOWLEDGE_REPO ?? "growthmatellc/growthmate-knowledge";
const BRANCH = process.env.KNOWLEDGE_BRANCH ?? "main";

export interface FetchedRepo {
  /** Extracted repo root (contains skills/, references/, clients/). */
  root: string;
  /** Temp dir to remove when done. */
  cleanup: () => void;
}

export async function fetchKnowledgeRepo(): Promise<FetchedRepo> {
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    throw new Error(
      "GITHUB_TOKEN is not set. Add a GitHub token with read access to the knowledge repo to the app's environment.",
    );
  }

  const url = `https://api.github.com/repos/${REPO}/tarball/${BRANCH}`;
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      "User-Agent": "WebinarStudio-sync",
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    redirect: "follow",
  });
  if (!res.ok || !res.body) {
    const detail = res.status === 404 ? " (repo not found or token lacks access)" : "";
    throw new Error(`GitHub tarball fetch failed: ${res.status} ${res.statusText}${detail}`);
  }

  const dir = mkdtempSync(join(tmpdir(), "gm-knowledge-"));
  const cleanup = () => {
    try {
      rmSync(dir, { recursive: true, force: true });
    } catch {
      /* best effort */
    }
  };

  try {
    // node-tar auto-detects gzip; extract the whole archive into `dir`.
    await pipeline(Readable.fromWeb(res.body as never), extractTar({ cwd: dir }));
  } catch (err) {
    cleanup();
    throw err;
  }

  // The archive contains a single top-level dir: <owner>-<repo>-<sha>/
  const root = readdirSync(dir)
    .map((e) => join(dir, e))
    .find((p) => existsSync(join(p, "skills")));
  if (!root) {
    cleanup();
    throw new Error("Extracted archive has no repo root containing skills/.");
  }

  return { root, cleanup };
}
