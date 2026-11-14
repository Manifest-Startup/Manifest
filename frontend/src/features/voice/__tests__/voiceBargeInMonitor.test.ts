import { computeTimeDomainRms, highFrequencyEnergyRatio } from '../voiceBargeInMonitor';

describe('voiceBargeInMonitor', () => {
  test('computeTimeDomainRms is near zero for silence', () => {
    const buf = new Uint8Array(512).fill(128);
    expect(computeTimeDomainRms(buf)).toBeLessThan(0.001);
  });

  test('computeTimeDomainRms rises with signal', () => {
    const buf = new Uint8Array(512).fill(128);
    for (let i = 0; i < buf.length; i += 1) {
      buf[i] = i % 2 === 0 ? 200 : 56;
    }
    expect(computeTimeDomainRms(buf)).toBeGreaterThan(0.15);
  });

  test('highFrequencyEnergyRatio returns fraction in 0-1', () => {
    const bins = 512;
    const freq = new Uint8Array(bins);
    for (let i = 0; i < bins; i += 1) {
      freq[i] = i > 100 ? 10 : 1;
    }
    const ratio = highFrequencyEnergyRatio(freq, 48000);
    expect(ratio).toBeGreaterThan(0);
    expect(ratio).toBeLessThanOrEqual(1);
  });
});
