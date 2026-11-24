/**
 * Tone of voice, read on this device (on with a notice; "stop reading my tone" turns it off; ADR 0024).
 *
 * While the person talks, the mic's own audio is measured here in the browser: pitch (YIN),
 * loudness (RMS) and pace (words per second of speech). Each turn is compared with how this
 * person sounded earlier in the same conversation, never with a population "norm", and only
 * a coarse cue leaves this file, e.g. "energized: faster and louder than usual". No audio,
 * no features and no cue is stored, and the cue goes only to the person's own agent with
 * that turn.
 *
 * It estimates arousal (calm ↔ energized), the dimension prosody carries best. It never names
 * emotions such as anger or sadness: the words carry those, and the agent reads them. The
 * shape follows W3C EmotionML 1.0 (dimension "arousal" from the PAD vocabulary, 0..1, with a
 * confidence), so the cue can be exported in a standard form (`toEmotionML`).
 */

/** Frames quieter than this (RMS) are silence or room noise. */
const VOICED_RMS = 0.012;
const MIN_PITCH_HZ = 70;
const MAX_PITCH_HZ = 400;
/** YIN's threshold: lower is stricter about what counts as a clear pitch. */
const YIN_THRESHOLD = 0.15;
/** Turns needed before a baseline exists: until then there is no cue at all. */
const BASELINE_TURNS = 2;
/** A turn with less voiced audio than this says too little to read. */
const MIN_VOICED_SECONDS = 0.6;

export const PROSODY_PREF_KEY = 'manifest.voice.toneReading';

export interface ProsodyFrame {
  rms: number;
  pitchHz: number | null;
}

export interface TurnProsody {
  voicedSeconds: number;
  /** Median pitch of voiced frames, Hz (null when none was clear). */
  pitchHz: number | null;
  /** Spread of pitch between the 10th and 90th percentile, in semitones. */
  pitchRangeSt: number;
  loudness: number;
  wordsPerSecond: number;
}

export type ToneLabel = 'energized' | 'calm' | 'subdued' | 'steady';

/** What goes to the agent: an enumerated label and fixed phrases, never free text. */
export interface ToneCue {
  label: ToneLabel;
  /** EmotionML arousal, 0 (very calm) .. 1 (very energized). */
  arousal: number;
  confidence: number;
  /** Fixed phrases such as "faster than usual"; at most three. */
  signs: ToneSign[];
}

export type ToneSign =
  | 'faster than usual'
  | 'slower than usual'
  | 'louder than usual'
  | 'quieter than usual'
  | 'more animated pitch than usual'
  | 'flatter pitch than usual'
  | 'higher pitch than usual'
  | 'lower pitch than usual';

/** YIN pitch detection (de Cheveigné & Kawahara, 2002) on one frame; null when unclear. */
export function detectPitch(frame: Float32Array, sampleRate: number): number | null {
  const maxLag = Math.min(Math.floor(sampleRate / MIN_PITCH_HZ), Math.floor(frame.length / 2));
  const minLag = Math.max(2, Math.floor(sampleRate / MAX_PITCH_HZ));
  if (maxLag <= minLag) return null;
  const diff = new Float32Array(maxLag + 1);
  const window = frame.length - maxLag;
  for (let lag = 1; lag <= maxLag; lag += 1) {
    let sum = 0;
    for (let i = 0; i < window; i += 1) {
      const d = frame[i] - frame[i + lag];
      sum += d * d;
    }
    diff[lag] = sum;
  }
  // Cumulative mean normalized difference.
  let running = 0;
  const cmnd = new Float32Array(maxLag + 1);
  cmnd[0] = 1;
  for (let lag = 1; lag <= maxLag; lag += 1) {
    running += diff[lag];
    cmnd[lag] = running > 0 ? (diff[lag] * lag) / running : 1;
  }
  for (let lag = minLag; lag <= maxLag; lag += 1) {
    if (cmnd[lag] < YIN_THRESHOLD) {
      while (lag + 1 <= maxLag && cmnd[lag + 1] < cmnd[lag]) lag += 1;
      // Parabolic interpolation around the dip for a finer estimate.
      const a = cmnd[lag - 1];
      const b = cmnd[lag];
      const c = lag + 1 <= maxLag ? cmnd[lag + 1] : b;
      const denom = a - 2 * b + c;
      const shift = denom !== 0 ? (a - c) / (2 * denom) : 0;
      return sampleRate / (lag + shift);
    }
  }
  return null;
}

/** Pitch needs only the low band: average every `factor` samples (a cheap low-pass), so YIN
 *  does ~factor² less work. 48 kHz → 12 kHz still resolves 70–400 Hz voices finely. */
export function decimate(frame: Float32Array, factor: number): Float32Array {
  if (factor <= 1) return frame;
  const out = new Float32Array(Math.floor(frame.length / factor));
  for (let i = 0; i < out.length; i += 1) {
    let sum = 0;
    for (let j = 0; j < factor; j += 1) sum += frame[i * factor + j];
    out[i] = sum / factor;
  }
  return out;
}

export function frameRms(frame: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < frame.length; i += 1) sum += frame[i] * frame[i];
  return Math.sqrt(sum / Math.max(1, frame.length));
}

function percentile(sorted: number[], p: number): number {
  if (!sorted.length) return 0;
  const index = Math.min(sorted.length - 1, Math.max(0, Math.round((sorted.length - 1) * p)));
  return sorted[index];
}

/** One turn's prosody from its frames (each `frameSeconds` long) and the words heard. */
export function summarizeTurn(frames: ProsodyFrame[], frameSeconds: number, words: number): TurnProsody {
  const voiced = frames.filter(f => f.rms >= VOICED_RMS);
  const pitches = voiced
    .map(f => f.pitchHz)
    .filter((p): p is number => p !== null)
    .sort((a, b) => a - b);
  const voicedSeconds = voiced.length * frameSeconds;
  const low = percentile(pitches, 0.1);
  const high = percentile(pitches, 0.9);
  const loud = voiced.map(f => f.rms).sort((a, b) => a - b);
  return {
    voicedSeconds,
    pitchHz: pitches.length >= 3 ? percentile(pitches, 0.5) : null,
    pitchRangeSt: pitches.length >= 3 && low > 0 ? 12 * Math.log2(high / low) : 0,
    loudness: percentile(loud, 0.5),
    wordsPerSecond: voicedSeconds > 0 ? words / voicedSeconds : 0,
  };
}

interface Running {
  n: number;
  mean: number;
  m2: number;
}

const empty = (): Running => ({ n: 0, mean: 0, m2: 0 });

function add(r: Running, x: number): Running {
  const n = r.n + 1;
  const delta = x - r.mean;
  const mean = r.mean + delta / n;
  return { n, mean, m2: r.m2 + delta * (x - mean) };
}

/** How far `x` is from this person's usual, in their own standard deviations (bounded). */
function z(r: Running, x: number, floor: number): number {
  if (r.n < 1) return 0;
  const sd = Math.max(floor, r.n > 1 ? Math.sqrt(r.m2 / (r.n - 1)) : floor);
  return Math.max(-3, Math.min(3, (x - r.mean) / sd));
}

/**
 * This conversation's baseline for one person, and the cue for each new turn. Features are
 * compared in relative terms (log loudness, semitones of pitch), so the mic's gain and the
 * person's natural voice don't matter.
 */
export class ToneBaseline {
  private pace = empty();
  private loud = empty();
  private pitch = empty();
  private range = empty();
  private turns = 0;

  /** The cue for this turn (null until there's a baseline or when the turn is too short). */
  next(turn: TurnProsody): ToneCue | null {
    if (turn.voicedSeconds < MIN_VOICED_SECONDS) return null;
    const loudDb = 20 * Math.log10(Math.max(turn.loudness, 1e-4));
    const pitchSt = turn.pitchHz ? 12 * Math.log2(turn.pitchHz / 100) : null;
    let cue: ToneCue | null = null;
    if (this.turns >= BASELINE_TURNS) {
      const zPace = z(this.pace, turn.wordsPerSecond, 0.35);
      const zLoud = z(this.loud, loudDb, 2);
      const zPitch = pitchSt === null ? 0 : z(this.pitch, pitchSt, 1);
      const zRange = z(this.range, turn.pitchRangeSt, 1);
      cue = toCue(zPace, zLoud, zPitch, zRange, Math.min(1, this.turns / 6));
    }
    this.turns += 1;
    this.pace = add(this.pace, turn.wordsPerSecond);
    this.loud = add(this.loud, loudDb);
    if (pitchSt !== null) this.pitch = add(this.pitch, pitchSt);
    this.range = add(this.range, turn.pitchRangeSt);
    return cue;
  }
}

const SIGN_AT = 1; // one of the person's own standard deviations

export function toCue(zPace: number, zLoud: number, zPitch: number, zRange: number, settled = 1): ToneCue {
  // Arousal rises with pace, loudness, pitch height and pitch movement (Scherer 2003; Juslin &
  // Laukka 2003); weights favour the features that are most robust in browser audio.
  const score = 0.35 * zPace + 0.3 * zLoud + 0.15 * zPitch + 0.2 * zRange;
  const arousal = 1 / (1 + Math.exp(-score * 1.2));
  const signs: ToneSign[] = [];
  const pairs: [number, ToneSign, ToneSign][] = [
    [zPace, 'faster than usual', 'slower than usual'],
    [zLoud, 'louder than usual', 'quieter than usual'],
    [zRange, 'more animated pitch than usual', 'flatter pitch than usual'],
    [zPitch, 'higher pitch than usual', 'lower pitch than usual'],
  ];
  for (const [value, up, down] of pairs.sort((a, b) => Math.abs(b[0]) - Math.abs(a[0]))) {
    if (signs.length < 3 && Math.abs(value) >= SIGN_AT) signs.push(value > 0 ? up : down);
  }
  const label: ToneLabel = arousal >= 0.7 ? 'energized' : arousal <= 0.3 ? (zLoud < -SIGN_AT ? 'subdued' : 'calm') : 'steady';
  const agreement = signs.length / 3;
  const confidence = Math.round(Math.min(0.8, (0.35 + 0.45 * agreement) * settled) * 100) / 100;
  return { label, arousal: Math.round(arousal * 100) / 100, confidence, signs };
}

/** The cue as a W3C EmotionML 1.0 document (dimension set: PAD, arousal only). */
export function toEmotionML(cue: ToneCue): string {
  return (
    '<emotionml xmlns="http://www.w3.org/2009/10/emotionml" version="1.0" ' +
    'dimension-set="http://www.w3.org/TR/emotion-voc/xml#pad-dimensions">' +
    `<emotion expressed-through="voice"><dimension name="arousal" value="${cue.arousal}" confidence="${cue.confidence}"/></emotion>` +
    '</emotionml>'
  );
}

/** On unless the person said to stop (no button: they say it; ADR 0024). */
export function toneReadingEnabled(): boolean {
  try {
    return window.localStorage.getItem(PROSODY_PREF_KEY) !== 'off';
  } catch {
    return true;
  }
}

/** "Stop reading my tone" → false, "read my tone again" → true, anything else → null. */
export function toneCommand(text: string): boolean | null {
  const t = text.toLowerCase();
  if (!/\btone\b/.test(t)) return null;
  if (/\b(stop|don'?t|do not|turn off|no more|quit)\b.*\b(read|reading|listen|listening|track|tracking|tone)\b/.test(t)) return false;
  if (/\b(start|turn on|resume|again|go ahead and|please)\b.*\b(read|reading|listen|listening|track|tracking)\b|\bread(ing)? my tone\b/.test(t)) return true;
  return null;
}

export const TONE_NOTICE =
  'Reading your tone of voice on this device to match your energy. No audio leaves it. Say "stop reading my tone" to turn it off.';

export function setToneReading(on: boolean): void {
  try {
    window.localStorage.setItem(PROSODY_PREF_KEY, on ? 'on' : 'off');
  } catch {
    // Private mode: it stays on for this conversation only.
  }
}

/**
 * Measures the mic while the person talks. `take` ends a turn: it returns the cue for it
 * (or null) and starts the next one. Nothing is kept beyond the running baseline numbers.
 */
export interface ProsodyMeter {
  /** The person started a new turn: drop what came before (keeping the last second, since
   *  recognition reports the first words a little after they were said). */
  begin: () => void;
  take: (words: number) => ToneCue | null;
  stop: () => void;
}

const FRAME_SIZE = 2048;
const FRAME_MS = 50;

export function startProsodyMeter(stream: MediaStream): ProsodyMeter | null {
  const Ctx =
    typeof window !== 'undefined'
      ? (window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext)
      : undefined;
  if (!Ctx || !stream.getAudioTracks().length) return null;
  let context: AudioContext;
  try {
    context = new Ctx();
  } catch {
    return null;
  }
  let source: MediaStreamAudioSourceNode;
  let analyser: AnalyserNode;
  try {
    source = context.createMediaStreamSource(stream);
    analyser = context.createAnalyser();
    analyser.fftSize = FRAME_SIZE;
    source.connect(analyser); // not to the speakers: measured only
  } catch {
    void context.close?.().catch(() => undefined);
    return null; // this browser can't measure the mic: voice works as before
  }
  const buffer = new Float32Array(FRAME_SIZE);
  const baseline = new ToneBaseline();
  const factor = Math.max(1, Math.floor(context.sampleRate / 12000));
  const pitchRate = context.sampleRate / factor;
  let frames: ProsodyFrame[] = [];
  const timer = window.setInterval(() => {
    analyser.getFloatTimeDomainData(buffer);
    const rms = frameRms(buffer);
    // Pitch only for voiced frames, on the decimated signal: well under a millisecond each.
    frames.push({ rms, pitchHz: rms >= VOICED_RMS ? detectPitch(decimate(buffer, factor), pitchRate) : null });
    if (frames.length > 1200) frames = frames.slice(-1200); // at most a minute of numbers
  }, FRAME_MS);
  return {
    begin: () => {
      frames = frames.slice(-Math.round(1000 / FRAME_MS));
    },
    take: words => {
      const turn = summarizeTurn(frames, FRAME_MS / 1000, words);
      frames = [];
      return baseline.next(turn);
    },
    stop: () => {
      window.clearInterval(timer);
      source.disconnect();
      void context.close().catch(() => undefined);
    },
  };
}
