import { computePeakAmplitude, computeTimeDomainRms, getFrequencyBandEnergy } from './voiceAudioMath';

export interface VoiceOrbRawFeatures {
  rms: number;
  peak: number;
  low: number;
  mid: number;
  high: number;
}

export interface VoiceOrbSmoothingConfig {
  attack: number;
  decay: number;
}

export interface VoiceOrbSmoothingSet {
  rms: VoiceOrbSmoothingConfig;
  peak: VoiceOrbSmoothingConfig;
  low: VoiceOrbSmoothingConfig;
  mid: VoiceOrbSmoothingConfig;
  high: VoiceOrbSmoothingConfig;
}

export type VoiceOrbSmoothedFeatures = VoiceOrbRawFeatures;

const DEFAULT_BAND_LIMITS = {
  lowMin: 80,
  lowMax: 320,
  midMin: 320,
  midMax: 2600,
  highMin: 2600,
};

export const DEFAULT_VOICE_ORB_SMOOTHING: VoiceOrbSmoothingSet = {
  rms: { attack: 0.26, decay: 0.13 },
  peak: { attack: 0.32, decay: 0.16 },
  low: { attack: 0.24, decay: 0.12 },
  mid: { attack: 0.22, decay: 0.11 },
  high: { attack: 0.18, decay: 0.08 },
};

export const EMPTY_VOICE_ORB_FEATURES: VoiceOrbSmoothedFeatures = {
  rms: 0,
  peak: 0,
  low: 0,
  mid: 0,
  high: 0,
};

export function extractVoiceOrbFeatures(
  byteTimeData: Uint8Array,
  byteFreqData: Uint8Array,
  sampleRate: number,
): VoiceOrbRawFeatures {
  if (byteTimeData.length === 0 || byteFreqData.length === 0 || sampleRate <= 0) {
    return { ...EMPTY_VOICE_ORB_FEATURES };
  }

  return {
    rms: computeTimeDomainRms(byteTimeData),
    peak: computePeakAmplitude(byteTimeData),
    low: getFrequencyBandEnergy(byteFreqData, sampleRate, DEFAULT_BAND_LIMITS.lowMin, DEFAULT_BAND_LIMITS.lowMax),
    mid: getFrequencyBandEnergy(byteFreqData, sampleRate, DEFAULT_BAND_LIMITS.midMin, DEFAULT_BAND_LIMITS.midMax),
    high: getFrequencyBandEnergy(byteFreqData, sampleRate, DEFAULT_BAND_LIMITS.highMin),
  };
}

export function smoothVoiceOrbValue(current: number, target: number, config: VoiceOrbSmoothingConfig): number {
  const factor = target >= current ? config.attack : config.decay;
  return current + (target - current) * factor;
}

export function smoothVoiceOrbFeatures(
  previous: VoiceOrbSmoothedFeatures,
  next: VoiceOrbRawFeatures,
  config: VoiceOrbSmoothingSet = DEFAULT_VOICE_ORB_SMOOTHING,
): VoiceOrbSmoothedFeatures {
  return {
    rms: smoothVoiceOrbValue(previous.rms, next.rms, config.rms),
    peak: smoothVoiceOrbValue(previous.peak, next.peak, config.peak),
    low: smoothVoiceOrbValue(previous.low, next.low, config.low),
    mid: smoothVoiceOrbValue(previous.mid, next.mid, config.mid),
    high: smoothVoiceOrbValue(previous.high, next.high, config.high),
  };
}

export function getVoiceOrbVisualTargets(features: VoiceOrbSmoothedFeatures) {
  return {
    scale: 1 + features.rms * 0.22 + features.low * 0.12,
    glow: 0.28 + features.peak * 0.72 + features.high * 0.14,
    outerRing: features.low,
    innerShape: features.mid,
    edgeDetail: features.high,
  };
}
