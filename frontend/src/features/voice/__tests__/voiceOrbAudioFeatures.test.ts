import {
  EMPTY_VOICE_ORB_FEATURES,
  extractVoiceOrbFeatures,
  getVoiceOrbVisualTargets,
  smoothVoiceOrbFeatures,
  smoothVoiceOrbValue,
} from '../voiceOrbAudioFeatures';

describe('voiceOrbAudioFeatures', () => {
  test('returns empty features for invalid inputs', () => {
    expect(extractVoiceOrbFeatures(new Uint8Array(), new Uint8Array(), 48_000)).toEqual(EMPTY_VOICE_ORB_FEATURES);
    expect(extractVoiceOrbFeatures(new Uint8Array([128]), new Uint8Array([0]), 0)).toEqual(EMPTY_VOICE_ORB_FEATURES);
  });

  test('extracts peak, rms, and band energies', () => {
    const timeData = new Uint8Array(256).fill(128);
    for (let i = 0; i < timeData.length; i += 4) {
      timeData[i] = 200;
      timeData[i + 1] = 56;
    }

    const freqData = new Uint8Array(512);
    freqData[2] = 255;
    freqData[3] = 240;
    freqData[30] = 220;
    freqData[31] = 210;
    freqData[120] = 200;
    freqData[121] = 180;

    const features = extractVoiceOrbFeatures(timeData, freqData, 48_000);

    expect(features.rms).toBeGreaterThan(0.1);
    expect(features.peak).toBeGreaterThan(0.4);
    expect(features.low).toBeGreaterThan(0);
    expect(features.mid).toBeGreaterThan(0);
    expect(features.high).toBeGreaterThan(0);
  });

  test('uses faster attack than decay', () => {
    const attackValue = smoothVoiceOrbValue(0.1, 0.9, { attack: 0.5, decay: 0.1 });
    const decayValue = smoothVoiceOrbValue(0.9, 0.1, { attack: 0.5, decay: 0.1 });

    expect(attackValue).toBeCloseTo(0.5);
    expect(decayValue).toBeCloseTo(0.82);
  });

  test('smooths the full feature set', () => {
    const smoothed = smoothVoiceOrbFeatures(
      EMPTY_VOICE_ORB_FEATURES,
      { rms: 1, peak: 0.8, low: 0.7, mid: 0.5, high: 0.4 },
      {
        rms: { attack: 0.5, decay: 0.25 },
        peak: { attack: 0.5, decay: 0.25 },
        low: { attack: 0.5, decay: 0.25 },
        mid: { attack: 0.5, decay: 0.25 },
        high: { attack: 0.5, decay: 0.25 },
      },
    );

    expect(smoothed).toEqual({
      rms: 0.5,
      peak: 0.4,
      low: 0.35,
      mid: 0.25,
      high: 0.2,
    });
  });

  test('maps audio features to visual targets', () => {
    const visualTargets = getVoiceOrbVisualTargets({
      rms: 0.5,
      peak: 0.75,
      low: 0.4,
      mid: 0.3,
      high: 0.2,
    });

    expect(visualTargets.scale).toBeGreaterThan(1);
    expect(visualTargets.glow).toBeGreaterThan(0.5);
    expect(visualTargets.outerRing).toBeCloseTo(0.4);
    expect(visualTargets.innerShape).toBeCloseTo(0.3);
    expect(visualTargets.edgeDetail).toBeCloseTo(0.2);
  });
});
