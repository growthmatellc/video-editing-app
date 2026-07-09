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

// --- Color parsing -----------------------------------------------------------

interface RGB {
  r: number;
  g: number;
  b: number;
}

function hexToRgb(hex: string): RGB | undefined {
  const v = normalizeHex(hex);
  if (!v) return undefined;
  return {
    r: parseInt(v.slice(1, 3), 16),
    g: parseInt(v.slice(3, 5), 16),
    b: parseInt(v.slice(5, 7), 16),
  };
}

function rgbToHex({ r, g, b }: RGB): string {
  const h = (n: number) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, "0");
  return `#${h(r)}${h(g)}${h(b)}`.toUpperCase();
}

// A color we should ignore for branding: white/black or a low-chroma gray.
function isNeutral({ r, g, b }: RGB): boolean {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  if (min > 232) return true; // near-white
  if (max < 20) return true; // near-black
  return max - min < 24; // gray / desaturated
}

// Hue in degrees (0-360) for distinctness comparison.
function hue({ r, g, b }: RGB): number {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const d = max - min;
  if (d === 0) return 0;
  let h: number;
  if (max === rn) h = ((gn - bn) / d) % 6;
  else if (max === gn) h = (bn - rn) / d + 2;
  else h = (rn - gn) / d + 4;
  h *= 60;
  return h < 0 ? h + 360 : h;
}

function hueDistance(a: RGB, b: RGB): number {
  const diff = Math.abs(hue(a) - hue(b)) % 360;
  return diff > 180 ? 360 - diff : diff;
}

// Collect every color (hex, rgb(), rgba()) in the text, counted by canonical hex,
// skipping fully-transparent and neutral colors.
function collectColors(text: string): Map<string, number> {
  const counts = new Map<string, number>();
  const bump = (rgb: RGB) => {
    if (isNeutral(rgb)) return;
    const key = rgbToHex(rgb);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  };

  for (const m of text.matchAll(/#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b/g)) {
    const rgb = hexToRgb(m[0]);
    if (rgb) bump(rgb);
  }
  for (const m of text.matchAll(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)/gi)) {
    const alpha = m[4] !== undefined ? parseFloat(m[4]) : 1;
    if (alpha === 0) continue; // fully transparent
    bump({ r: parseFloat(m[1]), g: parseFloat(m[2]), b: parseFloat(m[3]) });
  }
  return counts;
}

function findColors(text: string): { primary?: string; accent?: string } {
  // Explicit brand signal wins for primary, if present and not neutral.
  const themeColor = normalizeHex(
    firstMatch(text, /<meta[^>]+name=["']theme-color["'][^>]+content=["']([^"']+)["']/i),
  );
  const themeRgb = themeColor ? hexToRgb(themeColor) : undefined;

  const ranked = [...collectColors(text).entries()]
    .sort((a, b) => b[1] - a[1])
    .map((e) => e[0]);

  const primary = themeRgb && !isNeutral(themeRgb) ? themeColor : ranked[0];
  const primaryRgb = primary ? hexToRgb(primary) : undefined;

  // Accent = most frequent color with a hue clearly distinct from primary,
  // so a navy-primary site yields a coral/teal accent instead of navy again.
  let accent: string | undefined;
  if (primaryRgb) {
    accent = ranked.find((h) => {
      if (h === primary) return false;
      const rgb = hexToRgb(h);
      return rgb ? hueDistance(rgb, primaryRgb) > 35 : false;
    });
  }
  accent = accent ?? ranked.find((h) => h !== primary) ?? primary;

  return { primary, accent };
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

// Fetch up to `max` linked stylesheets so colors/fonts defined in external CSS
// (not just inline) are visible to the extractor. Best-effort; failures ignored.
async function fetchLinkedCss(html: string, base: string, max = 3): Promise<string> {
  const hrefs: string[] = [];
  for (const m of html.matchAll(/<link[^>]+rel=["'][^"']*stylesheet[^"']*["'][^>]*>/gi)) {
    const href = firstMatch(m[0], /href=["']([^"']+)["']/i);
    if (href) hrefs.push(abs(href, base));
    if (hrefs.length >= max) break;
  }
  const sheets = await Promise.all(
    hrefs.map(async (h) => {
      try {
        const r = await fetch(h, {
          headers: { "user-agent": "Mozilla/5.0 (compatible; WebinarStudio/1.0)" },
        });
        return await r.text();
      } catch {
        return "";
      }
    }),
  );
  return sheets.join("\n");
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
    const css = await fetchLinkedCss(html, target);
    const combined = `${html}\n${css}`;
    const colors = findColors(combined);
    const fonts = findFonts(combined);
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
