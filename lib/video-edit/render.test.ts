import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { test } from "node:test";
import { executeVideoEdit } from "./execute";
import { probeMedia } from "./media";

const exec = promisify(execFile);

test("a short clip renders a vertical proxy, srt, fcpxml, and handoff zip", async () => {
  const dir = await mkdtemp(join(tmpdir(), "video-edit-fixture-"));
  const src = join(dir, "talk.mp4");
  try {
    await exec("ffmpeg", [
      "-y",
      "-hide_banner",
      "-f",
      "lavfi",
      "-i",
      "color=c=0x224466:s=640x360:d=5",
      "-f",
      "lavfi",
      "-i",
      "sine=frequency=440:duration=5",
      "-filter_complex",
      "[1:a]volume=0:enable='between(t,1.25,2.85)'[a]",
      "-map",
      "0:v",
      "-map",
      "[a]",
      "-c:v",
      "libx264",
      "-pix_fmt",
      "yuv420p",
      "-c:a",
      "aac",
      "-shortest",
      src,
    ], { timeout: 30_000 });

    const transcript = [
      "0.10 0.30 Hello",
      "0.30 0.55 there",
      "0.55 0.80 everyone",
      "0.80 1.00 um",
      "1.00 1.25 welcome.",
      "2.90 3.15 Hello",
      "3.15 3.40 there",
      "3.40 3.65 everyone",
      "3.65 3.95 welcome",
      "3.95 4.30 aboard",
    ].join("\n");

    const edit = await executeVideoEdit({
      filePath: src,
      fileName: "talk.mp4",
      format: "talking-head",
      aspect: "9:16",
      transcriptText: transcript,
      brand: { accentColor: "#E8C547", displayFont: "Inter" },
      clientName: "Sample",
    });

    assert.equal(edit.meta.captions.fillHex, "#E8C547");
    assert.equal(edit.meta.aspect, "9:16");
    assert.ok(edit.meta.removed.some((r) => r.reasons.includes("retake") || r.reasons.includes("filler")));
    assert.match(edit.srt, /aboard/);
    assert.doesNotMatch(edit.srt, /\bum\b/);
    assert.match(edit.fcpxml, /asset-clip/);
    assert.match(edit.edl, /STUDIO/);
    assert.ok(edit.handoffZip.includes(Buffer.from("HANDOFF.txt")));
    assert.ok(edit.handoffZip.includes(Buffer.from("talk.mp4")));

    const previewPath = join(dir, "preview.mp4");
    const { writeFile } = await import("node:fs/promises");
    await writeFile(previewPath, edit.preview);
    const probe = await probeMedia(previewPath);
    assert.equal(probe.width, 720);
    assert.equal(probe.height, 1280);
    assert.ok(probe.duration > 0.5 && probe.duration < 5);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
