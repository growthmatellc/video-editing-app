/**
 * Thin, swappable auth wrapper.
 *
 * Auth is OPTIONAL. With AUTH_ENABLED unset or "false" the app runs as a single
 * operator with no login — AuthProvider is a clean passthrough and no auth
 * package is required.
 *
 * To turn auth on:
 *   1. `npm install @clerk/nextjs`
 *   2. set AUTH_ENABLED="true" and the Clerk keys in .env
 *   3. follow the two TODO blocks below (provider + middleware).
 *
 * Nothing else in the app imports Clerk directly, so the provider can be
 * swapped (Auth.js, Lucia, etc.) by editing only this file.
 */
import type { ReactNode } from "react";

export const AUTH_ENABLED = process.env.AUTH_ENABLED === "true";

export function AuthProvider({ children }: { children: ReactNode }) {
  if (!AUTH_ENABLED) return <>{children}</>;

  // TODO (auth on): wrap children in the provider, e.g.
  //   import { ClerkProvider } from "@clerk/nextjs";
  //   return <ClerkProvider>{children}</ClerkProvider>;
  return <>{children}</>;
}

/**
 * Server-side helper: returns the current operator id (used as ownerId /
 * assigneeId / createdById on records), or null when auth is disabled.
 */
export async function getOperatorId(): Promise<string | null> {
  if (!AUTH_ENABLED) return null;

  // TODO (auth on): return the signed-in user id, e.g.
  //   import { auth } from "@clerk/nextjs/server";
  //   const { userId } = await auth();
  //   return userId;
  return null;
}
