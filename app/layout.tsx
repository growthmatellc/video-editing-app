import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { theme } from "@/theme/tokens";
import { AuthProvider } from "@/lib/auth";

// OPERATOR INPUT: swap these for the brand's display/body typefaces.
const bodyFont = Inter({ variable: "--font-body", subsets: ["latin"] });
const displayFont = Space_Grotesk({ variable: "--font-display", subsets: ["latin"] });

export const metadata: Metadata = {
  title: theme.appName,
  description: `${theme.appName} — run a live-webinar funnel through one ordered pipeline.`,
};

// Build the CSS variables for the brand tokens. This is the ONLY place hex codes
// leave theme/tokens.ts and enter the DOM.
const themeVars: React.CSSProperties = {
  ["--bg" as string]: theme.color.bg,
  ["--surface" as string]: theme.color.surface,
  ["--border" as string]: theme.color.border,
  ["--text" as string]: theme.color.text,
  ["--text-muted" as string]: theme.color.textMuted,
  ["--accent" as string]: theme.color.accent,
  ["--accent-text" as string]: theme.color.accentText,
  ["--ok" as string]: theme.color.ok,
  ["--warn" as string]: theme.color.warn,
  ["--radius" as string]: theme.radius,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      style={themeVars}
      className={`${bodyFont.variable} ${displayFont.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
