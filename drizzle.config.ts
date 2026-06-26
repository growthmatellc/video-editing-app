import type { Config } from "drizzle-kit";
import { config } from "dotenv";

// Load local env first (Vercel writes here), then .env as a fallback. dotenv
// does not override already-set vars, so .env.local takes precedence.
config({ path: ".env.local" });
config();

export default {
  schema: "./lib/db/schema.ts",
  out: "./drizzle",
  dialect: "postgresql",
  dbCredentials: {
    url: process.env.DATABASE_URL ?? "",
  },
} satisfies Config;
