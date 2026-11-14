/**
 * Fewer, longer TTS segments reduce audible gaps between MP3/browser utterances (less "choppy" playback).
 */
export function coalesceSpeechSegments(segments: string[], maxMergedLength = 400): string[] {
  const cleaned = segments.map(s => s.trim()).filter(Boolean);
  if (!cleaned.length) {
    return [];
  }

  const out: string[] = [];
  let buf = cleaned[0];
  for (let i = 1; i < cleaned.length; i += 1) {
    const next = cleaned[i];
    const candidate = `${buf} ${next}`;
    if (candidate.length <= maxMergedLength) {
      buf = candidate;
    } else {
      out.push(buf);
      buf = next;
    }
  }
  out.push(buf);
  return out;
}
