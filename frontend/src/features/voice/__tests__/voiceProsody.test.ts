import { detectPitch, frameRms, summarizeTurn, toCue, toEmotionML, ToneBaseline, type ProsodyFrame } from '../voiceProsody';

const RATE = 48000;

function tone(hz: number, amplitude = 0.2, length = 2048): Float32Array {
  const frame = new Float32Array(length);
  for (let i = 0; i < length; i += 1) frame[i] = amplitude * Math.sin((2 * Math.PI * hz * i) / RATE);
  return frame;
}

function frames(count: number, rms: number, pitchHz: number | null, wobble = 0): ProsodyFrame[] {
  return Array.from({ length: count }, (_, i) => ({ rms, pitchHz: pitchHz === null ? null : pitchHz + (i % 2 ? wobble : -wobble) }));
}

describe('tone of voice, read on this device', () => {
  it('finds the pitch of a voice-like tone and none in silence', () => {
    for (const hz of [110, 196, 300]) {
      const found = detectPitch(tone(hz), RATE);
      expect(found).not.toBeNull();
      expect(Math.abs((found as number) - hz)).toBeLessThan(hz * 0.02);
    }
    expect(detectPitch(new Float32Array(2048), RATE)).toBeNull();
    expect(frameRms(tone(200, 0.2))).toBeCloseTo(0.2 / Math.SQRT2, 2);
  });

  it('summarizes a turn from voiced frames only', () => {
    const turn = summarizeTurn([...frames(20, 0.05, 180, 20), ...frames(20, 0.001, null)], 0.05, 6);
    expect(turn.voicedSeconds).toBeCloseTo(1);
    expect(turn.pitchHz).toBeGreaterThan(150);
    expect(turn.pitchRangeSt).toBeGreaterThan(1);
    expect(turn.wordsPerSecond).toBeCloseTo(6);
  });

  it('says nothing until it knows how this person usually sounds', () => {
    const baseline = new ToneBaseline();
    const usual = summarizeTurn(frames(40, 0.03, 150, 5), 0.05, 5);
    expect(baseline.next(usual)).toBeNull();
    expect(baseline.next({ ...usual, wordsPerSecond: 2.6 })).toBeNull();
    expect(baseline.next(summarizeTurn(frames(4, 0.03, 150), 0.05, 1))).toBeNull(); // too short to read
  });

  it('hears energized and subdued turns against the person’s own baseline', () => {
    const baseline = new ToneBaseline();
    for (const pace of [2.4, 2.6, 2.5, 2.5]) baseline.next(summarizeTurn(frames(40, 0.03, 150, 5), 0.05, pace * 2));
    const excited = baseline.next(summarizeTurn(frames(40, 0.09, 190, 30), 0.05, 4.2 * 2));
    expect(excited?.label).toBe('energized');
    expect(excited?.signs).toContain('faster than usual');
    expect(excited?.signs.length).toBeLessThanOrEqual(3);
    const low = baseline.next(summarizeTurn(frames(40, 0.008 + 0.006, 135, 1), 0.05, 1.4 * 2));
    expect(['subdued', 'calm']).toContain(low?.label);
    expect(low?.signs).toContain('slower than usual');
  });

  it('keeps confidence modest: prosody is a hint, never a diagnosis', () => {
    const strongest = toCue(3, 3, 3, 3);
    expect(strongest.confidence).toBeLessThanOrEqual(0.8);
    expect(toCue(0, 0, 0, 0)).toMatchObject({ label: 'steady', signs: [] });
  });

  it('exports W3C EmotionML with the PAD arousal dimension', () => {
    const xml = toEmotionML({ label: 'energized', arousal: 0.82, confidence: 0.6, signs: [] });
    expect(xml).toContain('xmlns="http://www.w3.org/2009/10/emotionml"');
    expect(xml).toContain('dimension-set="http://www.w3.org/TR/emotion-voc/xml#pad-dimensions"');
    expect(xml).toContain('<dimension name="arousal" value="0.82" confidence="0.6"/>');
  });
});
