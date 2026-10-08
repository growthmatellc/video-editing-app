import assert from "node:assert/strict";
import { test } from "node:test";
import { planCuts, parseTranscript } from "./cuts";
import { applyFeedback } from "./feedback";
import { cuesFromWords, mapTime, toSrt, wordsOnTimeline, captionStyleFromBrand, resolveAspect } from "./captions";
import { buildEdl, buildFcpxml } from "./interchange";
import { zipStore } from "./zip";
import { DEFAULT_RULES } from "./types";
import type { TranscriptWord } from "./types";

const rules = { ...DEFAULT_RULES };

function w(text: string, start: number, end: number): TranscriptWord {
  return { text, start, end };
}

test("dead air between words is removed and words are kept", () => {
  const words = [w("Hello", 0.1, 0.4), w("there", 2.0, 2.4)];
  const plan = planCuts({ duration: 3, words, silences: [], rules });
  assert.ok(plan.removed.some((r) => r.reasons.includes("silence")));
  assert.ok(plan.removed[0].start > 0.4);
  assert.ok(plan.removed[0].end < 2.0);
  assert.ok(plan.kept.some((k) => k.start <= 0.1 && k.end >= 0.4));
  assert.ok(plan.kept.some((k) => k.start <= 2.0 && k.end >= 2.4));
});

test("um is removed and like-this is kept", () => {
  const withUm = planCuts({
    duration: 2,
    words: [w("Hello", 0.0, 0.3), w("um", 0.32, 0.5), w("there", 0.52, 0.9)],
    silences: [],
    rules,
  });
  assert.ok(withUm.removed.some((r) => r.reasons.includes("filler") && r.detail.includes("um")));

  const fluent = planCuts({
    duration: 2,
    words: [w("things", 0.0, 0.3), w("like", 0.32, 0.5), w("this", 0.52, 0.8)],
    silences: [],
    rules,
  });
  assert.equal(fluent.removed.some((r) => r.reasons.includes("filler")), false);

  const isolated = planCuts({
    duration: 3,
    words: [w("so", 0.0, 0.2), w("like", 0.6, 0.8), w("anyway", 1.3, 1.7)],
    silences: [],
    rules,
  });
  assert.ok(isolated.removed.some((r) => r.detail.includes("like")));
});

test("an earlier repeated take is removed and the later take stays", () => {
  const words = [
    w("Hello", 0.1, 0.3),
    w("there", 0.3, 0.55),
    w("everyone", 0.55, 0.9),
    w("welcome.", 0.9, 1.25),
    w("Hello", 2.9, 3.15),
    w("there", 3.15, 3.4),
    w("everyone", 3.4, 3.7),
    w("welcome", 3.7, 4.0),
    w("aboard", 4.0, 4.4),
  ];
  const plan = planCuts({ duration: 5, words, silences: [], rules });
  const retake = plan.removed.find((r) => r.reasons.includes("retake"));
  assert.ok(retake, "expected a retake removal");
  assert.ok(retake.start < 1.3);
  assert.ok(plan.kept.some((k) => k.start <= 2.9 && k.end >= 4.4));
});

test("stutter drops the first repeated word", () => {
  const plan = planCuts({
    duration: 2,
    words: [w("the", 0.1, 0.25), w("the", 0.3, 0.5), w("offer", 0.5, 0.9)],
    silences: [],
    rules,
  });
  assert.ok(plan.removed.some((r) => r.reasons.includes("stutter")));
  assert.ok(plan.kept.some((k) => k.start <= 0.3 && k.end >= 0.9));
});

test("captions are timed to the cut, not the source", () => {
  const words = [w("Hello", 0.0, 0.4), w("there", 2.0, 2.5)];
  const plan = planCuts({ duration: 3, words, silences: [], rules });
  const spoken = wordsOnTimeline(words, plan.kept);
  assert.equal(spoken.length, 2);
  assert.ok(spoken[1].start < 1.5, "second word should move earlier on the cut timeline");
  const srt = toSrt(cuesFromWords(spoken));
  assert.match(srt, /Hello/);
  assert.match(srt, /there/);
  assert.equal(mapTime(0, plan.kept), 0);
});

test("pasted srt and timestamp lines parse; plain prose does not", () => {
  const lines = parseTranscript("0.10 0.40 Hello\n0.40 0.80 there");
  assert.equal(lines.length, 2);
  assert.equal(lines[0].text, "Hello");
  const srt = parseTranscript("1\n00:00:01,000 --> 00:00:02,000\nHi there\n");
  assert.deepEqual(srt.map((w) => w.text), ["Hi", "there"]);
  assert.equal(parseTranscript("just some words without times").length, 0);
});

test("feedback notes that are not cut rules are left unused", () => {
  const keep = applyFeedback("please keep fillers, the open is flat");
  assert.equal(keep.rules.cutFillers, false);
  assert.match(keep.unused ?? "", /open is flat/);

  const tight = applyFeedback("tighter");
  assert.equal(tight.rules.silenceSeconds, 0.35);
  assert.equal(tight.unused, null);

  const explicit = applyFeedback("silence:0.45");
  assert.equal(explicit.rules.silenceSeconds, 0.45);
});

test("brand kit colors are used only when a hex is present", () => {
  const fallback = captionStyleFromBrand(null);
  assert.equal(fallback.source, "default");
  assert.equal(fallback.fillHex, "#FFFFFF");

  const kit = captionStyleFromBrand({ accentColor: "#E8C547", primaryColor: "#112233", displayFont: "Inter" });
  assert.equal(kit.source, "brand-kit");
  assert.equal(kit.fillHex, "#E8C547");
  assert.equal(kit.fontSubstituted, false);

  const dark = captionStyleFromBrand({ primaryColor: "#112233" });
  assert.equal(dark.boxHex, "#112233");
  assert.equal(dark.fillHex, "#FFFFFF");

  assert.equal(resolveAspect("16:9", 1920, 1080).aspect, "16:9");
  assert.equal(resolveAspect("16:9", 1080, 1920).aspect, "9:16");
  assert.equal(resolveAspect("9:16", 1920, 1080).aspect, "9:16");
});

test("fcpxml and edl list every keep, and the zip contains the handoff files", () => {
  const kept = [
    { start: 0.5, end: 1.5 },
    { start: 3, end: 4 },
  ];
  const xml = buildFcpxml({
    clientName: "Sample & Co",
    fileName: "clip.mp4",
    dropDir: "/Users/Shared/WebinarStudio/handoff",
    duration: 5,
    width: 1920,
    height: 1080,
    frameRate: { fpsNum: 30, fpsDen: 1 },
    hasAudio: true,
    audioChannels: 2,
    audioRate: 48000,
    kept,
  });
  assert.equal(xml.match(/<asset-clip /g)?.length, 2);
  assert.match(xml, /Sample &amp; Co/);
  assert.match(xml, /file:\/\/\/Users\/Shared\/WebinarStudio\/handoff\/clip\.mp4/);
  assert.match(xml, /version="1\.9"/);

  const { edl } = buildEdl({
    title: "Sample",
    fileName: "clip.mp4",
    frameRate: { fpsNum: 30, fpsDen: 1 },
    timecode: null,
    kept,
  });
  assert.equal(edl.match(/STUDIO/g)?.length, 2);
  assert.match(edl, /FROM CLIP NAME: clip\.mp4/);
  assert.match(edl, /NON-DROP FRAME/);

  const zip = zipStore([
    { name: "HANDOFF.txt", data: Buffer.from("hi") },
    { name: "edit.fcpxml", data: Buffer.from(xml) },
  ]);
  assert.equal(zip.subarray(0, 4).toString("hex"), "504b0304");
  assert.ok(zip.includes(Buffer.from("edit.fcpxml")));
  assert.ok(zip.includes(Buffer.from("HANDOFF.txt")));
});
