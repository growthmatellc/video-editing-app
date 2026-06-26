/**
 * Best-effort brand-kit scraper. No LLM. Fetches a site's HTML and pulls
 * primary/accent color, display/body font, and a logo URL from common signals.
 * Everything is optional — a thin result is fine; the operator can fill gaps.
 */
import type { BrandKit } from "./slide-deck-schema";

const URL_RE = /https?:\/\/[^\s)"'<>]+/i;

export function extractUrl(...sources: (string | null | undefined)[]): string | null {
  for (const src of sources) {
    if (!src) continue;
    const m = src.match(URL_RE);
    if (m) return m[0];
  }
  return null;
}

function abs(url: string, base: string): string {
  try {
    return new URL(url, base).toString();
  } catch {
    return url;
  }
}

function firstMatch(html: string, re: RegExp): string | undefined {
  const m = html.match(re);
  return m ? m[1] : undefined;
}

function normalizeHex(c: string | undefined): string | undefined {
  if (!c) return undefined;
  const v = c.trim();
  if (/^#[0-9a-fA-F]{6}$/.test(v)) return v.toUpperCase();
  if (/^#[0-9a-fA-F]{3}$/.test(v)) {
    const [r, g, b] = v.slice(1).split("");
    return `#${r}${r}${g}${g}${b}${b}`.toUpperCase();
  }
  return undefined;
}

function findColors(html: string): { primary?: string; accent?: string } {
  const primary = normalizeHex(
    firstMatch(html, /<meta[^>]+name=["']theme-color["'][^>]+content=["']([^"']+)["']/i),
  );
  // Pull distinct hex codes that appear in inline styles / style blocks.
  const hexes = Array.from(html.matchAll(/#[0-9a-fA-F]{6}\b/g)).map((m) =>
    m[0].toUpperCase(),
  );
  const counts = new Map<string, number>();
  for (const h of hexes) {
    if (["#FFFFFF", "#000000"].includes(h)) continue;
    counts.set(h, (counts.get(h) ?? 0) + 1);
  }
  const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1]).map((e) => e[0]);
  const accent = ranked.find((h) => h !== primary) ?? ranked[0];
  return { primary: primary ?? ranked[0], accent };
}

function findFonts(html: string): { display?: string; body?: string } {
  const families = new Set<string>();
  // Google Fonts links: ...family=Inter:wght...&family=Space+Grotesk...
  for (const m of html.matchAll(/family=([^:&"']+)/gi)) {
    families.add(decodeURIComponent(m[1].replace(/\+/g, " ")).trim());
  }
  // font-family declarations.
  const ff = firstMatch(html, /font-family\s*:\s*([^;"'}]+)/i);
  if (ff) {
    const first = ff.split(",")[0].replace(/["']/g, "").trim();
    if (first && !/^(inherit|initial|sans-serif|serif|monospace)$/i.test(first))
      families.add(first);
  }
  const list = [...families];
  return { display: list[0], body: list[1] ?? list[0] };
}

function findLogo(html: string, base: string): string | undefined {
  const candidates = [
    firstMatch(html, /<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']/i),
    firstMatch(html, /<link[^>]+rel=["'][^"']*icon[^"']*["'][^>]+href=["']([^"']+)["']/i),
    firstMatch(html, /<img[^>]+(?:class|alt|id)=["'][^"']*logo[^"']*["'][^>]+src=["']([^"']+)["']/i),
    firstMatch(html, /<img[^>]+src=["']([^"']*logo[^"']*)["']/i),
  ].filter(Boolean) as string[];
  return candidates.length ? abs(candidates[0], base) : undefined;
}

export async function scrapeBrandKit(url: string): Promise<BrandKit> {
  const target = url.startsWith("http") ? url : `https://${url}`;
  const scrapedAt = new Date().toISOString();
  try {
    const res = await fetch(target, {
      headers: { "user-agent": "Mozilla/5.0 (compatible; WebinarStudio/1.0)" },
      redirect: "follow",
    });
    const html = await res.text();
    const colors = findColors(html);
    const fonts = findFonts(html);
    return {
      primaryColor: colors.primary,
      accentColor: colors.accent,
      displayFont: fonts.display,
      bodyFont: fonts.body,
      logoUrl: findLogo(html, target),
      sourceUrl: target,
      scrapedAt,
    };
  } catch {
    return { sourceUrl: target, scrapedAt };
  }
}

export function brandKitToMarkdown(bk: BrandKit): string {
  const row = (k: string, v?: string) => `- **${k}:** ${v ?? "[PLACEHOLDER]"}`;
  return [
    `# Brand Kit`,
    ``,
    bk.sourceUrl ? `Scraped from ${bk.sourceUrl}` : `No source URL provided.`,
    ``,
    row("Primary color", bk.primaryColor),
    row("Accent color", bk.accentColor),
    row("Display font", bk.displayFont),
    row("Body font", bk.bodyFont),
    row("Logo", bk.logoUrl),
    ``,
    `Confirm or correct these before generating the slide deck. The deck and any`,
    `brand-matched pages read from this kit.`,
  ].join("\n");
}
