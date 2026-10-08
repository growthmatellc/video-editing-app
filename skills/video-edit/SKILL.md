# Video Edit

You are not writing copy. This stage turns one uploaded talking-head clip into a reviewable cut and a handoff for DaVinci Resolve. The deterministic cutter in `lib/video-edit/` is the authority. Do not invent brand colors, captions, or b-roll.

## What the operator is making

One of three deliveries. All of them default to vertical 9:16. Landscape is allowed only when the upload is clearly landscape and the operator asks for it.

1. **Short-form ad** — 15–60 seconds.
2. **Funnel video** — webinar invite or call-confirmation talking head.
3. **Talking-head** — organic social.

## What gets removed

Say so in the cut list. The same footage and the same rules always produce the same ranges.

- **Dead air.** A gap longer than the silence threshold (default 0.60s), from ffmpeg's silence detector and from gaps between transcript words. Interior gaps keep 0.08s of pad so words are not clipped. Leading and trailing dead air is removed.
- **Fillers.** um, uh, er, ah, hmm, and the same family of tokens. The phrases "you know", "i mean", "sort of", and "kind of" when they sit together. "like" and "so" only when they are isolated between pauses — "like this" stays.
- **Retakes.** When a phrase of at least four content words is repeated by the next phrase within 8 seconds, the earlier take goes and the later take stays.
- **Stutters.** An immediate repeated word drops the first copy.

## What the operator can change on reject

Only these notes change the cut. Anything else is reported as not applied.

- `tighter` / `looser`
- `silence:0.8`
- `keep fillers` / `cut fillers`
- `keep retakes` / `cut retakes`
- `vertical` / `landscape`
- `short-form` / `funnel` / `talking-head`

## Captions

Captions are the transcript, timed to the cut timeline, not ad copy. Do not run the copywriting auditor on them.

When the Brand Kit stage is approved, caption color comes from its accent, then its primary. A dark brand color is drawn as the caption background so it stays readable. When the kit has no color, or is not approved, captions are white with a black outline. The preview font is the brand font only when that font file is in `assets/fonts/`; otherwise the preview uses Inter and the handoff tells the editor which brand font to apply in Resolve.

## Handoff

The browser preview is a proxy. The finish happens in DaVinci Resolve on the Mac mini, from:

- `edit.fcpxml` (FCPXML 1.9) — File > Import > Timeline
- `edit.edl` (CMX 3600, reel `STUDIO`) — pre-conformed EDL fallback
- `captions.srt` — File > Import > Subtitle, on the cut timeline

The FCPXML is a straight cut of the original frames. Reframe to 9:16 or 16:9 in Resolve. Do not master from the proxy.
