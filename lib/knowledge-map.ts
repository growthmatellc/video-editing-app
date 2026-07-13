/**
 * Maps each pipeline stage to the growthmate-knowledge sources that define how
 * its deliverable is built and what "best" looks like. `npm run sync:knowledge`
 * loads these into the DB (nothing is read from the filesystem at runtime):
 *
 *   skills  -> skills.kbSkillMd    (each folder's SKILL.md + workflow/prompt files = the method)
 *   skills  -> skills.learningsMd  (each folder's learnings/insights.md = learned corrections)
 *   anchors -> skills.examplesMd   (best-performer sequences/decks/pages to MIRROR in structure)
 *   craft   -> skills.examplesMd   (cross-cutting craft rules)
 *
 * Anchors matter most: the SKILL.md files are routers; the real cadence/format
 * lives in the anchor library. Load the anchors a stage should copy the STRUCTURE
 * of (voice/facts get re-skinned from the client context at generation time).
 *
 * `anchors` are paths under references/best-performers/.
 * `craft`   are filenames under references/craft/.
 */
export interface KbStageSource {
  skills: string[];
  anchors?: string[];
  craft?: string[];
}

export const KB_STAGE_SOURCES: Record<string, KbStageSource> = {
  "webinar-blueprint": {
    skills: ["slide-building"],
    anchors: [
      "webinar-decks/jane-mukami-metabolic-alignment-deck-v1.md",
      "webinar-decks/mindstrong-rachel-metabolism-workshop-deck-v1.md",
    ],
  },
  "webinar-title": {
    skills: ["slide-building", "funnel-copy"],
    anchors: [
      "funnel-pages/jane-mukami-registration-page-v1.md",
      "funnel-pages/mindstrong-rachel-reclaim-registration-page-v1.md",
    ],
  },
  "webinar-script": {
    skills: ["slide-building", "scripting"],
    anchors: ["webinar-decks/jane-mukami-metabolic-alignment-deck-v1.md"],
  },
  "webinar-slides": {
    skills: ["slide-building", "presentation-design"],
    anchors: [
      "webinar-decks/jane-mukami-metabolic-alignment-deck-v1.md",
      "webinar-decks/erinne-full-circle-webinar-deck-v1.md",
    ],
  },
  "offer-stack": {
    skills: ["slide-building"],
    anchors: ["webinar-decks/mindstrong-rachel-metabolism-workshop-deck-v1.md"],
  },
  "registration-page": {
    skills: ["funnel-copy"],
    anchors: [
      "funnel-pages/REGISTRATION-PAGE-PATTERN.md",
      "funnel-pages/jane-mukami-registration-page-v1.md",
      "funnel-pages/jesse-korytko-registration-page-v1.md",
    ],
    craft: ["funnel-and-email-rules-lauren.md"],
  },
  "ad-creative": {
    skills: ["scripting"],
    anchors: [
      "video-ads/jane-mukami-v1-belly-fat-hook.md",
      "video-ads/mindstrong-rachel-v4-eat-less-move-more.md",
      "video-ads/veronica-yu-v3-glp1-nutrition-gap.md",
    ],
  },
  "funnel-videos": {
    skills: ["scripting"],
    anchors: [
      "confirmation-videos/webinar-confirmation-video.md",
      "confirmation-videos/call-booking-confirmation-video.md",
    ],
  },
  "email-sequences": {
    skills: ["email-sms-building"],
    anchors: [
      "email-sequences/jane-mukami-live-webinar-show-up-sequence.md",
      "email-sequences/jane-mukami-replay-sequence.md",
      "email-sequences/hylke-soulfire-pre-webinar-sequence.md",
      "email-sequences/jennyjean-replay-sequence.md",
    ],
    craft: ["funnel-and-email-rules-lauren.md", "email-sms-output-formatting.md"],
  },
  "sms-sequences": {
    skills: ["email-sms-building"],
    anchors: [
      "email-sequences/jane-mukami-live-webinar-show-up-sequence.md",
      "email-sequences/jane-mukami-replay-sequence.md",
    ],
    craft: ["email-sms-output-formatting.md"],
  },
  "call-nurture": {
    skills: ["email-sms-building"],
    anchors: [
      "email-sequences/vfactor-health-appointment-nurture-sequence-FULL.md",
      "email-sequences/vfactor-health-appointment-nurture-sequence.md",
      "email-sequences/jennyjean-post-booking-call-sequence.md",
      "email-sequences/hylke-soulfire-post-booking-pre-call-sequence.md",
    ],
    craft: ["funnel-and-email-rules-lauren.md", "email-sms-output-formatting.md"],
  },
  "objection-qa-bank": {
    skills: ["slide-building"],
    anchors: ["webinar-decks/jane-mukami-metabolic-alignment-deck-v1.md"],
  },
  "designer-handoff": {
    skills: ["funnel-copy", "creative-director-v2"],
    anchors: [
      "funnel-pages/jane-mukami-webinar-confirmation-page-v1.md",
      "funnel-pages/jane-mukami-replay-page-v1.md",
    ],
  },
  "funnel-spec": { skills: ["n8n-automation"] },
  "tracking-setup": { skills: ["n8n-automation"] },
};
