/**
 * Maps each pipeline stage (by skillKey) to the growthmate-knowledge craft
 * skill(s) whose SKILL.md should be folded into that stage's system prompt.
 *
 * The KB skills are craft disciplines (slide-building, scripting, funnel-copy…),
 * not per-stage deliverables, so this is a curated many-stages-to-few-skills map.
 * Deprecated KB skills (webinar-presentation-copy / -design, superseded by the
 * split skills) are intentionally excluded.
 *
 * `npm run sync:knowledge` reads these folders from the knowledge repo and writes
 * the concatenated content into skills.kbSkillMd for each stage. Nothing here is
 * read at runtime from the filesystem — the DB is the runtime source (Vercel-safe).
 */

// stage skillKey -> knowledge-repo skill folder names (skills/<folder>/SKILL.md)
export const KB_SKILL_MAP: Record<string, string[]> = {
  "webinar-blueprint": ["slide-building"], // mechanism ideation + deck spine live here
  "webinar-script": ["slide-building", "scripting"],
  "webinar-slides": ["slide-building", "presentation-design"],
  "offer-stack": ["slide-building"],
  "registration-page": ["funnel-copy"],
  "ad-creative": ["scripting"],
  "email-sequences": ["email-sms-building"],
  "sms-sequences": ["email-sms-building"],
  "objection-qa-bank": ["slide-building"],
  "designer-handoff": ["funnel-copy", "creative-director-v2"],
  "funnel-spec": ["n8n-automation"],
  "tracking-setup": ["n8n-automation"],
};

// Per folder, which markdown file carries the skill body, in preference order.
// All mapped folders currently ship SKILL.md; the fallbacks keep sync resilient
// if a folder is later restructured (e.g. agent-spec style skills).
export const KB_SKILL_FILE_CANDIDATES = [
  "SKILL.md",
  "02-system-prompt.md",
  "README.md",
];
