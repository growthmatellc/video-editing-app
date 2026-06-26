// theme/tokens.ts  — operator edits this file to rebrand. Nothing else.
export const theme = {
  appName: process.env.NEXT_PUBLIC_APP_NAME ?? "Webinar Studio",
  color: {
    bg: "#0B0B0C",          // app background      OPERATOR INPUT
    surface: "#141416",     // cards / panels      OPERATOR INPUT
    border: "#26262A",      // hairlines           OPERATOR INPUT
    text: "#F5F5F4",        // primary text        OPERATOR INPUT
    textMuted: "#A1A1AA",   // secondary text      OPERATOR INPUT
    accent: "#5B8DEF",      // brand accent        OPERATOR INPUT
    accentText: "#FFFFFF",  // text on accent      OPERATOR INPUT
    ok: "#3FB984",          // approved state
    warn: "#E0B341",        // draft state
  },
  font: {
    display: "var(--font-display)", // headlines   OPERATOR INPUT
    body: "var(--font-body)",       // body        OPERATOR INPUT
    mono: "ui-monospace, monospace",
  },
  radius: "8px",
} as const;

export type Theme = typeof theme;
