export interface BrandKit {
  primaryColor?: string;
  accentColor?: string;
  displayFont?: string;
  bodyFont?: string;
  logoUrl?: string;
  sourceUrl?: string;
  scrapedAt?: string;
}

export type Slide =
  | { type: "titleSlide"; title: string; subtitle?: string }
  | { type: "teachingPoint"; heading: string; support?: string }
  | { type: "statCallout"; stat: string; context: string }
  | { type: "framework"; heading?: string; steps: { number: string; label: string }[] }
  | { type: "caseStudy"; subject: string; result: string; timeframe: string }
  | {
      type: "compare";
      leftLabel: string;
      leftItems: string[];
      rightLabel: string;
      rightItems: string[];
    }
  | { type: "offerStack"; heading: string; items: { label: string; value?: string }[] }
  | { type: "bonus"; label: string; value?: string }
  | { type: "guarantee"; headline: string; detail: string }
  | { type: "priceReveal"; totalValue?: string; price: string; note?: string }
  | { type: "cta"; headline: string; action: string; url?: string }
  | { type: "qa"; label: string }
  | { type: "sectionTransition"; label: string };

export interface SlideDeck {
  title: string;
  clientName: string;
  theme: "dark" | "light";
  accentHex?: string;
  brandKit?: BrandKit;
  slides: Slide[];
}

export const SLIDE_TYPES: Slide["type"][] = [
  "titleSlide",
  "teachingPoint",
  "statCallout",
  "framework",
  "caseStudy",
  "compare",
  "offerStack",
  "bonus",
  "guarantee",
  "priceReveal",
  "cta",
  "qa",
  "sectionTransition",
];

/**
 * The system prompt for the webinar-slides stage. The executor injects the
 * approved script as locked context; this tells the model how to shape the deck.
 */
export const SLIDES_SYSTEM_PROMPT = `You convert an approved live-webinar script into a presentation deck expressed as a single SlideDeck JSON object.

Slides carry the VISUAL ANCHOR for a live presentation, not a teleprompter transcript. One beat per slide. The presenter talks around each slide.

Follow the approved script's order and sections. Use sectionTransition slides between the open, each teaching segment, the transition, the pitch, and the close.

Use each slide type for its named purpose:
- titleSlide: the open (title + optional subtitle).
- teachingPoint: a single idea (heading + optional one-line support). This is the default.
- statCallout: a single stat with one line of context.
- framework: an enumerated set of steps ({ number, label }).
- caseStudy: proof ({ subject, result, timeframe }).
- compare: old-way vs new-way (two labelled columns of items).
- offerStack: the stack ({ heading, items: { label, value? } }).
- bonus: a single bonus ({ label, value? }).
- guarantee: the risk reversal ({ headline, detail }).
- priceReveal: { totalValue?, price, note? }.
- cta: a call to action ({ headline, action, url? }).
- qa: the Q&A bridge ({ label }).
- sectionTransition: a divider between sections ({ label }).

Rules:
- Keep on-slide text tight. Headlines, not paragraphs.
- NEVER emit fonts or colors. The renderer applies the approved brand kit.
- Set "theme" to "dark" unless the brand clearly reads light.
- Return ONLY the JSON object. No prose, no markdown fences.

The JSON shape is exactly:
{
  "title": string,
  "clientName": string,
  "theme": "dark" | "light",
  "slides": Slide[]
}
where each Slide is one of the typed objects above.`;

export function isValidDeck(d: unknown): d is SlideDeck {
  if (!d || typeof d !== "object") return false;
  const deck = d as Record<string, unknown>;
  return Array.isArray(deck.slides) && deck.slides.length > 0;
}
