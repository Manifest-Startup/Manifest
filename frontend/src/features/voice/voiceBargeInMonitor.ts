import { computeTimeDomainRms } from './voiceAudioMath';

export { computeTimeDomainRms } from './voiceAudioMath';

/**
 * Lightweight browser barge-in: RMS energy + high-frequency ratio vs adaptive noise floor.
 * Phase 2 could swap in WASM VAD (e.g. Silero); emotion/pitch classification is out of scope here.
 */

export interface VoiceBargeInConfig {
  sustainMs: number;
  /** Trigger when rms exceeds max(noiseFloor * ratio, minAbsolute). */
  triggerRatio: number;
  minAbsolute: number;
  /** Minimum high-frequency energy share (0–1) to treat as speech-like vs low-frequency noise. */
  minHighFreqRatio: number;
}

export interface VoiceBargeInOptions extends Partial<VoiceBargeInConfig> {
  /**
   * Optional shared AudioContext. When provided the monitor will reuse it
   * and NOT close it on cleanup; the caller controls its lifecycle.
   */
  context?: AudioContext;
  /**
   * When true the monitor stops the stream's tracks on cleanup. Defaults to
   * true for backward compatibility, set false when using a shared
   * MediaStream owned by another consumer (e.g. the orb analyser).
   */
  ownsStream?: boolean;
}

const DEFAULT_CONFIG: VoiceBargeInConfig = {
  sustainMs: 200,
  triggerRatio: 4,
  minAbsolute: 0.038,
  minHighFreqRatio: 0.12,
};

/** Share of FFT energy above ~300 Hz (rough speech band emphasis). */
export function highFrequencyEnergyRatio(byteFreqData: Uint8Array, sampleRate: number): number {
  if (byteFreqData.length === 0) {
    return 0;
  }
  const binWidth = sampleRate / (byteFreqData.length * 2);
  const startBin = Math.min(byteFreqData.length - 1, Math.max(1, Math.floor(300 / binWidth)));
  let hi = 0;
  let total = 0;
  for (let i = 0; i < byteFreqData.length; i += 1) {
    const v = byteFreqData[i]!;
    total += v;
    if (i >= startBin) {
      hi += v;
    }
  }
  return total > 0 ? hi / total : 0;
}

/**
 * Monitors mic while assistant is thinking/speaking; calls onBargeIn once when sustained speech-like energy is detected.
 * Caller should stop TTS / abort processing when fired.
 */
export function startVoiceBargeInMonitor(
  stream: MediaStream,
  onBargeIn: () => void,
  options: VoiceBargeInOptions = {},
): () => void {
  const { context: providedContext, ownsStream = true, ...partialConfig } = options;
  const config = { ...DEFAULT_CONFIG, ...partialConfig };
  let cancelled = false;
  let fired = false;
  const audioContext = providedContext ?? new AudioContext();
  const ownsContext = !providedContext;
  const source = audioContext.createMediaStreamSource(stream);
  const analyser = audioContext.createAnalyser();
  analyser.fftSize = 1024;
  analyser.smoothingTimeConstant = 0.55;
  source.connect(analyser);

  const timeData = new Uint8Array(analyser.fftSize);
  const freqData = new Uint8Array(analyser.frequencyBinCount);
  let noiseFloor = 0.025;
  let aboveSince: number | null = null;

  const cleanup = () => {
    cancelled = true;
    try {
      source.disconnect();
    } catch {
      /* ignore */
    }
    if (ownsStream) {
      stream.getTracks().forEach(track => track.stop());
    }
    if (ownsContext) {
      void audioContext.close();
    }
  };

  const tick = () => {
    if (cancelled || fired) {
      return;
    }

    analyser.getByteTimeDomainData(timeData);
    analyser.getByteFrequencyData(freqData);
    const rms = computeTimeDomainRms(timeData);
    const hiRatio = highFrequencyEnergyRatio(freqData, audioContext.sampleRate);

    if (rms < noiseFloor * 0.55) {
      noiseFloor = noiseFloor * 0.992 + rms * 0.008;
    }

    const threshold = Math.max(noiseFloor * config.triggerRatio, config.minAbsolute);
    const speechLike = hiRatio >= config.minHighFreqRatio && rms > threshold;
    const now = typeof performance !== 'undefined' ? performance.now() : Date.now();

    if (speechLike) {
      if (aboveSince === null) {
        aboveSince = now;
      } else if (now - aboveSince >= config.sustainMs) {
        fired = true;
        onBargeIn();
        cleanup();
        return;
      }
    } else {
      aboveSince = null;
    }

    requestAnimationFrame(tick);
  };

  requestAnimationFrame(tick);

  return cleanup;
}
