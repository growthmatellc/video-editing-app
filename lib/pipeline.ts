export interface StageDef {
  key: string;
  label: string;
  description: string;
  skillKey: string | null;   // null = special-cased (intake, brand-kit) or human-only
  order: number;
  phase: "intake" | "content" | "funnel" | "launch-config";
  runnable?: boolean;        // false = human-only (intake). Default true.
}

export const WEBINAR_PIPELINE: StageDef[] = [
  {
    key: "intake",
    label: "Intake",
    description: "Client intake — the single source of truth for every downstream stage. Human-entered.",
    skillKey: null, order: 1, phase: "intake", runnable: false,
  },
  {
    key: "brand-kit",
    label: "Brand Kit",
    description: "Scrapes the client's site for colors, fonts, and logo so the slide deck and pages match their identity. Approve before generating slides.",
    skillKey: null, order: 2, phase: "intake", runnable: true,
  },
  {
    key: "webinar-blueprint",
    label: "Webinar Blueprint",
    description: "The strategic spine: the single Big Promise, the 3 belief-shifting points, the content-to-pitch transition thesis, and the offer angle. Everything downstream is built on this.",
    skillKey: "webinar-blueprint", order: 3, phase: "content", runnable: true,
  },
  {
    key: "webinar-title",
    label: "Webinar Title",
    description: "Promise-driven title options for the live webinar/workshop — names that earn the registration, built from the blueprint's Big Promise and mechanism. Pick one before building the script and pages.",
    skillKey: "webinar-title", order: 4, phase: "content", runnable: true,
  },
  {
    key: "webinar-script",
    label: "Webinar Script",
    description: "The full spoken presentation, act by act: open and big promise, teach the 3 points, the transition, the pitch, the close. Pure spoken word.",
    skillKey: "webinar-script", order: 5, phase: "content", runnable: true,
  },
  {
    key: "webinar-slides",
    label: "Webinar Slides",
    description: "Presentation deck — one beat per slide, brand-matched. Renders to .pptx.",
    skillKey: "webinar-slides", order: 6, phase: "content", runnable: true,
  },
  {
    key: "offer-stack",
    label: "Offer Stack",
    description: "The stacked offer: core deliverable, bonuses, value framing, price reveal, guarantee, and scarcity/urgency mechanics for the close.",
    skillKey: "offer-stack", order: 7, phase: "content", runnable: true,
  },
  {
    key: "registration-page",
    label: "Registration Page",
    description: "Registration page copy: headline, sub-headline, what-you'll-learn bullets, presenter bio, and CTA. The promise that earns the signup.",
    skillKey: "registration-page", order: 8, phase: "funnel", runnable: true,
  },
  {
    key: "ad-creative",
    label: "Ad Creative",
    description: "5 paid-social ad concepts (hook angle + primary text + headline) that drive registrations, built off the blueprint and registration promise.",
    skillKey: "ad-creative", order: 9, phase: "funnel", runnable: true,
  },
  {
    key: "funnel-videos",
    label: "Funnel Videos",
    description: "Two spoken-word confirmation video scripts: the webinar-registration confirmation video (reply READY, add to calendar, register on Zoom + curriculum tease + proof) and the call-booking confirmation video (shown after they book the Strategy Session).",
    skillKey: "funnel-videos", order: 10, phase: "funnel", runnable: true,
  },
  {
    key: "email-sequences",
    label: "Email Sequences",
    description: "Confirmation, show-up reminder sequence (the indoctrination runway), live 'we're on' email, replay/no-show recovery, and post-webinar cart-close sequence.",
    skillKey: "email-sequences", order: 11, phase: "launch-config", runnable: true,
  },
  {
    key: "sms-sequences",
    label: "SMS Sequences",
    description: "Show-up reminders, the going-live alert, and replay nudges. Short, high-deliverability copy.",
    skillKey: "sms-sequences", order: 12, phase: "launch-config", runnable: true,
  },
  {
    key: "call-nurture",
    label: "Call Nurture Sequence",
    description: "Post-booking appointment-nurture: the emails + SMS that fire when a prospect books the 1-on-1 Strategy Session, to drive call show-up, frame the conversation, and pre-qualify. Separate from the webinar emails.",
    skillKey: "call-nurture", order: 13, phase: "launch-config", runnable: true,
  },
  {
    key: "objection-qa-bank",
    label: "Objection & Q&A Bank",
    description: "The live close toolkit: top objections with reframes, and a seeded Q&A bank the presenter works through while the cart is open.",
    skillKey: "objection-qa-bank", order: 14, phase: "launch-config", runnable: true,
  },
  {
    key: "designer-handoff",
    label: "Designer Handoff",
    description: "Consolidated build document for the funnel designer: registration page, thank-you/confirmation page, live room, replay page, and checkout, with all approved copy in place.",
    skillKey: "designer-handoff", order: 15, phase: "launch-config", runnable: true,
  },
  {
    key: "funnel-spec",
    label: "Funnel Spec",
    description: "Technical build brief: webinar platform wiring (registration -> reminders -> live/replay -> checkout), automations, and integrations for the contractor.",
    skillKey: "funnel-spec", order: 16, phase: "launch-config", runnable: true,
  },
  {
    key: "tracking-setup",
    label: "Tracking Setup",
    description: "Pixel events, UTM structure, and a registration -> show -> stay -> buy tracking sheet.",
    skillKey: "tracking-setup", order: 17, phase: "launch-config", runnable: true,
  },
];

export const STAGE_BY_KEY: Record<string, StageDef> =
  Object.fromEntries(WEBINAR_PIPELINE.map((s) => [s.key, s]));

export const PHASE_LABELS: Record<StageDef["phase"], string> = {
  intake: "Intake",
  content: "Build the webinar",
  funnel: "Front-end funnel",
  "launch-config": "Launch configuration",
};

// Stages whose prose is run through the quality reviewer (section 8).
export const VOICE_GATED_STAGES = new Set<string>([
  "webinar-blueprint",
  "webinar-title",
  "webinar-script",
  "offer-stack",
  "registration-page",
  "ad-creative",
  "funnel-videos",
  "email-sequences",
  "sms-sequences",
  "call-nurture",
  "objection-qa-bank",
]);

export const PHASE_ORDER: StageDef["phase"][] = [
  "intake",
  "content",
  "funnel",
  "launch-config",
];
