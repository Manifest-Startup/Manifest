export function computeTimeDomainRms(byteTimeData: Uint8Array): number {
  if (byteTimeData.length === 0) {
    return 0;
  }

  let sum = 0;
  for (let i = 0; i < byteTimeData.length; i += 1) {
    const v = (byteTimeData[i]! - 128) / 128;
    sum += v * v;
  }
  return Math.sqrt(sum / byteTimeData.length);
}

export function computePeakAmplitude(byteTimeData: Uint8Array): number {
  let peak = 0;
  for (let i = 0; i < byteTimeData.length; i += 1) {
    const amplitude = Math.abs((byteTimeData[i]! - 128) / 128);
    if (amplitude > peak) {
      peak = amplitude;
    }
  }
  return peak;
}

export function getFrequencyBinWidth(byteFreqData: Uint8Array, sampleRate: number): number {
  if (byteFreqData.length === 0 || sampleRate <= 0) {
    return 0;
  }
  return sampleRate / (byteFreqData.length * 2);
}

export function getFrequencyBandEnergy(
  byteFreqData: Uint8Array,
  sampleRate: number,
  minHz: number,
  maxHz?: number,
): number {
  if (byteFreqData.length === 0) {
    return 0;
  }

  const binWidth = getFrequencyBinWidth(byteFreqData, sampleRate);
  if (binWidth <= 0) {
    return 0;
  }

  const maxFrequency = sampleRate / 2;
  const clampedMin = Math.max(0, minHz);
  const clampedMax = maxHz == null ? maxFrequency : Math.min(maxFrequency, maxHz);
  if (clampedMax <= clampedMin) {
    return 0;
  }

  const startBin = Math.min(byteFreqData.length - 1, Math.max(0, Math.floor(clampedMin / binWidth)));
  const endBin = Math.min(byteFreqData.length - 1, Math.max(startBin, Math.ceil(clampedMax / binWidth)));

  let total = 0;
  for (let i = startBin; i <= endBin; i += 1) {
    total += byteFreqData[i]!;
  }

  const binCount = endBin - startBin + 1;
  return binCount > 0 ? total / (binCount * 255) : 0;
}
