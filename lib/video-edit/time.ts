/** Frame-rate and timecode helpers shared by the cut list, EDL, and FCPXML. */

export interface FrameRate {
  /** ffprobe r_frame_rate: frames per second = fpsNum / fpsDen. */
  fpsNum: number;
  fpsDen: number;
}

export const DEFAULT_FPS: FrameRate = { fpsNum: 30, fpsDen: 1 };

export function parseFrameRate(rate: string | undefined): FrameRate {
  if (!rate) return DEFAULT_FPS;
  const m = rate.match(/^(\d+(?:\.\d+)?)(?:\/(\d+(?:\.\d+)?))?$/);
  if (!m) return DEFAULT_FPS;
  const num = Math.round(Number(m[1]));
  const den = m[2] ? Math.round(Number(m[2])) : 1;
  if (!num || !den) return DEFAULT_FPS;
  return { fpsNum: num, fpsDen: den };
}

export function fpsApprox(fr: FrameRate): number {
  return fr.fpsNum / fr.fpsDen;
}

/** Integer fps for a non-drop-frame EDL, plus a note when the source is not integer. */
export function edlRate(fr: FrameRate): { fps: number; note: string | null } {
  const approx = fpsApprox(fr);
  const known = [24, 25, 30, 50, 60];
  const nearest = known.reduce((best, n) => (Math.abs(n - approx) < Math.abs(best - approx) ? n : best));
  if (Math.abs(nearest - approx) < 0.02) return { fps: nearest, note: null };
  const rounded = Math.round(approx) || 30;
  return {
    fps: rounded,
    note: `Source frame rate is ${approx.toFixed(3)}. The EDL uses non-drop-frame ${rounded} fps, so a conform can slip by about a frame. The FCPXML keeps the exact rate.`,
  };
}

export function toTimecode(seconds: number, fps: number): string {
  const fpsInt = Math.max(1, Math.round(fps));
  const frames = Math.max(0, Math.round(seconds * fpsInt));
  const f = frames % fpsInt;
  const totalSec = Math.floor(frames / fpsInt);
  const s = totalSec % 60;
  const m = Math.floor(totalSec / 60) % 60;
  const h = Math.floor(totalSec / 3600);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(h)}:${p(m)}:${p(s)}:${p(f)}`;
}

export function parseTimecode(tc: string | null | undefined, fps: number): number | null {
  if (!tc) return null;
  const m = tc.trim().match(/(\d+):(\d+):(\d+):(\d+)/);
  if (!m) return null;
  const fpsInt = Math.max(1, Math.round(fps));
  return Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]) + Number(m[4]) / fpsInt;
}

/** FCPXML time, snapped to a frame. */
export function fcpxTime(seconds: number, fr: FrameRate): string {
  const frames = Math.max(0, Math.round((seconds * fr.fpsNum) / fr.fpsDen));
  return `${frames * fr.fpsDen}/${fr.fpsNum}s`;
}

export function frameDuration(fr: FrameRate): string {
  return `${fr.fpsDen}/${fr.fpsNum}s`;
}

export function formatSeconds(t: number): string {
  const sign = t < 0 ? "-" : "";
  const v = Math.abs(t);
  const m = Math.floor(v / 60);
  const s = (v - m * 60).toFixed(2).padStart(5, "0");
  return `${sign}${m}:${s}`;
}
