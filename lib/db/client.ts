import { drizzle, type PostgresJsDatabase } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

// Lazy singleton: we do NOT connect (or throw on a missing URL) at import time,
// so `next build` and any route that never touches the DB stay importable.
const globalForDb = globalThis as unknown as {
  _pg?: ReturnType<typeof postgres>;
  _db?: PostgresJsDatabase<typeof schema>;
};

function getDb(): PostgresJsDatabase<typeof schema> {
  if (globalForDb._db) return globalForDb._db;

  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) {
    throw new Error("DATABASE_URL is not set. Copy .env.example to .env and fill it in.");
  }

  const queryClient =
    globalForDb._pg ?? postgres(connectionString, { prepare: false, max: 5 });
  const instance = drizzle(queryClient, { schema });

  if (process.env.NODE_ENV !== "production") {
    globalForDb._pg = queryClient;
    globalForDb._db = instance;
  }
  return instance;
}

// Proxy so existing `db.select()...` call sites keep working while the real
// connection is created on first use.
export const db = new Proxy({} as PostgresJsDatabase<typeof schema>, {
  get(_target, prop, receiver) {
    const real = getDb();
    const value = Reflect.get(real as object, prop, receiver);
    return typeof value === "function" ? value.bind(real) : value;
  },
});

export { schema };
