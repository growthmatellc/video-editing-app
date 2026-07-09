/**
 * Render a typed SlideDeck to a .pptx and upload it via the storage wrapper.
 * Applies brand-kit colors/fonts. Provider-agnostic: returns a public URL.
 */
import pptxgen from "pptxgenjs";
import type { SlideDeck, Slide, BrandKit } from "./slide-deck-schema";
import { putFile } from "./storage";

// Fallback palette when the brand kit is thin. Hex without the leading '#'.
const DEFAULTS = {
  dark: { bg: "0B0B0C", text: "F5F5F4", muted: "A1A1AA", accent: "5B8DEF" },
  light: { bg: "FFFFFF", text: "111114", muted: "555560", accent: "2F6FE0" },
};

function hex(input: string | undefined, fallback: string): string {
  if (!input) return fallback;
  const cleaned = input.replace("#", "").trim();
  return /^[0-9a-fA-F]{6}$/.test(cleaned) ? cleaned.toUpperCase() : fallback;
}

interface Palette {
  bg: string;
  text: string;
  muted: string;
  accent: string;
  displayFont: string;
  bodyFont: string;
}

function buildPalette(deck: SlideDeck): Palette {
  const base = deck.theme === "light" ? DEFAULTS.light : DEFAULTS.dark;
  const bk: BrandKit = deck.brandKit ?? {};
  return {
    bg: base.bg,
    text: base.text,
    muted: base.muted,
    accent: hex(bk.accentColor ?? bk.primaryColor ?? deck.accentHex, base.accent),
    displayFont: bk.displayFont || "Arial",
    bodyFont: bk.bodyFont || "Arial",
  };
}

const W = 13.333; // 16:9 inches
const H = 7.5;

export async function renderDeck(
  deck: SlideDeck,
): Promise<{ url: string; slideCount: number }> {
  const pptx = new pptxgen();
  pptx.defineLayout({ name: "WIDE", width: W, height: H });
  pptx.layout = "WIDE";
  pptx.author = "Webinar Studio";
  pptx.title = deck.title;

  const p = buildPalette(deck);

  for (const slide of deck.slides) {
    if (!slide || typeof slide !== "object") continue; // skip null/garbage entries
    const s = pptx.addSlide();
    s.background = { color: p.bg };
    drawSlide(s, slide, p, deck.brandKit);
  }

  const buf = (await pptx.write({ outputType: "nodebuffer" })) as Buffer;
  const safeTitle = deck.title.replace(/[^a-zA-Z0-9]+/g, "-").toLowerCase().slice(0, 60);
  const { url } = await putFile(
    `decks/${safeTitle || "deck"}.pptx`,
    buf,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  );
  return { url, slideCount: deck.slides.length };
}

type PptxSlide = ReturnType<pptxgen["addSlide"]>;

function drawSlide(s: PptxSlide, slide: Slide, p: Palette, bk?: BrandKit) {
  // Accent bar down the left edge for visual identity.
  s.addShape("rect", { x: 0, y: 0, w: 0.18, h: H, fill: { color: p.accent } });

  // Optional logo top-right.
  if (bk?.logoUrl) {
    try {
      s.addImage({ path: bk.logoUrl, x: W - 1.7, y: 0.35, w: 1.3, h: 0.5, sizing: { type: "contain", w: 1.3, h: 0.5 } });
    } catch {
      /* logo is best-effort */
    }
  }

  const titleOpts = { fontFace: p.displayFont, color: p.text, bold: true } as const;
  const bodyOpts = { fontFace: p.bodyFont, color: p.text } as const;
  const mutedOpts = { fontFace: p.bodyFont, color: p.muted } as const;
  const PAD = 0.9;
  const contentW = W - PAD * 2;

  switch (slide.type) {
    case "titleSlide":
      s.addText(slide.title, { ...titleOpts, x: PAD, y: 2.6, w: contentW, h: 1.6, fontSize: 44, align: "left" });
      if (slide.subtitle)
        s.addText(slide.subtitle, { ...mutedOpts, x: PAD, y: 4.2, w: contentW, h: 1, fontSize: 22 });
      break;

    case "teachingPoint":
      s.addText(slide.heading, { ...titleOpts, x: PAD, y: 2.4, w: contentW, h: 2, fontSize: 34, valign: "middle" });
      if (slide.support)
        s.addText(slide.support, { ...mutedOpts, x: PAD, y: 4.4, w: contentW, h: 1.2, fontSize: 20 });
      break;

    case "statCallout":
      s.addText(slide.stat, { ...titleOpts, color: p.accent, x: PAD, y: 2.1, w: contentW, h: 2, fontSize: 60 });
      s.addText(slide.context, { ...bodyOpts, x: PAD, y: 4.3, w: contentW, h: 1.4, fontSize: 22 });
      break;

    case "framework": {
      if (slide.heading)
        s.addText(slide.heading, { ...titleOpts, x: PAD, y: 0.7, w: contentW, h: 1, fontSize: 30 });
      const rows = (slide.steps ?? []).map((st) => [
        { text: String(st?.number ?? ""), options: { color: p.accent, bold: true, fontFace: p.displayFont, fontSize: 18, valign: "middle" as const } },
        { text: String(st?.label ?? ""), options: { color: p.text, fontFace: p.bodyFont, fontSize: 18, valign: "middle" as const } },
      ]);
      if (rows.length)
        s.addTable(rows, { x: PAD, y: 1.9, w: contentW, colW: [1.2, contentW - 1.2], rowH: 0.6, border: { type: "none" } });
      break;
    }

    case "caseStudy":
      s.addText(slide.subject, { ...titleOpts, x: PAD, y: 1.6, w: contentW, h: 1.2, fontSize: 30 });
      s.addText(slide.result, { ...bodyOpts, color: p.accent, x: PAD, y: 3.0, w: contentW, h: 1.6, fontSize: 26, bold: true });
      s.addText(slide.timeframe, { ...mutedOpts, x: PAD, y: 4.6, w: contentW, h: 0.8, fontSize: 18 });
      break;

    case "compare": {
      const colW = (contentW - 0.6) / 2;
      s.addText(String(slide.leftLabel ?? ""), { ...titleOpts, x: PAD, y: 0.8, w: colW, h: 0.8, fontSize: 22, color: p.muted });
      s.addText(String(slide.rightLabel ?? ""), { ...titleOpts, x: PAD + colW + 0.6, y: 0.8, w: colW, h: 0.8, fontSize: 22, color: p.accent });
      const leftItems = (slide.leftItems ?? []).map((t) => ({ text: String(t ?? ""), options: { bullet: true, fontSize: 18, color: p.text, fontFace: p.bodyFont, paraSpaceAfter: 8 } }));
      const rightItems = (slide.rightItems ?? []).map((t) => ({ text: String(t ?? ""), options: { bullet: true, fontSize: 18, color: p.text, fontFace: p.bodyFont, paraSpaceAfter: 8 } }));
      if (leftItems.length) s.addText(leftItems, { x: PAD, y: 1.8, w: colW, h: 5 });
      if (rightItems.length) s.addText(rightItems, { x: PAD + colW + 0.6, y: 1.8, w: colW, h: 5 });
      break;
    }

    case "offerStack": {
      s.addText(String(slide.heading ?? ""), { ...titleOpts, x: PAD, y: 0.7, w: contentW, h: 1, fontSize: 30 });
      const rows = (slide.items ?? []).map((it) => [
        { text: String(it?.label ?? ""), options: { color: p.text, fontFace: p.bodyFont, fontSize: 18, valign: "middle" as const } },
        { text: String(it?.value ?? ""), options: { color: p.accent, bold: true, align: "right" as const, fontFace: p.displayFont, fontSize: 18, valign: "middle" as const } },
      ]);
      if (rows.length)
        s.addTable(rows, { x: PAD, y: 1.9, w: contentW, colW: [contentW - 2.6, 2.6], rowH: 0.55, border: { type: "none" } });
      break;
    }

    case "bonus":
      s.addText("BONUS", { ...mutedOpts, color: p.accent, x: PAD, y: 2.0, w: contentW, h: 0.6, fontSize: 18, bold: true });
      s.addText(slide.label, { ...titleOpts, x: PAD, y: 2.7, w: contentW, h: 1.6, fontSize: 32 });
      if (slide.value)
        s.addText(slide.value, { ...bodyOpts, color: p.accent, x: PAD, y: 4.3, w: contentW, h: 1, fontSize: 24, bold: true });
      break;

    case "guarantee":
      s.addText(slide.headline, { ...titleOpts, x: PAD, y: 2.0, w: contentW, h: 1.4, fontSize: 34 });
      s.addText(slide.detail, { ...bodyOpts, x: PAD, y: 3.6, w: contentW, h: 2, fontSize: 20 });
      break;

    case "priceReveal":
      if (slide.totalValue)
        s.addText(`Total value: ${slide.totalValue}`, { ...mutedOpts, x: PAD, y: 2.0, w: contentW, h: 0.8, fontSize: 22, strike: true });
      s.addText(slide.price, { ...titleOpts, color: p.accent, x: PAD, y: 2.8, w: contentW, h: 1.8, fontSize: 56 });
      if (slide.note)
        s.addText(slide.note, { ...mutedOpts, x: PAD, y: 4.7, w: contentW, h: 1, fontSize: 20 });
      break;

    case "cta":
      s.addText(slide.headline, { ...titleOpts, x: PAD, y: 2.2, w: contentW, h: 1.4, fontSize: 36 });
      s.addText(slide.action, { ...bodyOpts, color: p.accent, x: PAD, y: 3.8, w: contentW, h: 1, fontSize: 26, bold: true });
      if (slide.url)
        s.addText(slide.url, { ...mutedOpts, x: PAD, y: 4.9, w: contentW, h: 0.8, fontSize: 20 });
      break;

    case "qa":
      s.addText(slide.label, { ...titleOpts, x: PAD, y: 2.8, w: contentW, h: 1.8, fontSize: 44, align: "center" });
      break;

    case "sectionTransition":
      s.addText(slide.label, { ...titleOpts, color: p.accent, x: PAD, y: 3.0, w: contentW, h: 1.5, fontSize: 40, align: "center", valign: "middle" });
      break;

    default: {
      // Exhaustiveness guard: unknown slide types render their raw label if any.
      const anySlide = slide as { type?: string };
      s.addText(anySlide.type ?? "slide", { color: p.muted, x: PAD, y: 3, w: contentW, h: 1, fontSize: 20 });
    }
  }
}
