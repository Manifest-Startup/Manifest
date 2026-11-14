import { extractSpeakableChunks } from '../sentenceChunker';
import { coalesceSpeechSegments } from '../speechPlaybackMerge';

describe('coalesceSpeechSegments', () => {
  test('merges short fragments into fewer TTS units for smoother playback', () => {
    const fragments = [
      'Hello there.',
      'Welcome to Manifest.',
      'What brings you here today?',
    ];
    const merged = coalesceSpeechSegments(fragments, 400);
    expect(merged.length).toBe(1);
    expect(merged[0]).toContain('Manifest');
  });

  test('respects max length by splitting when concatenation would exceed cap', () => {
    const a = 'A'.repeat(250);
    const b = 'B'.repeat(250);
    const merged = coalesceSpeechSegments([a, b], 400);
    expect(merged.length).toBe(2);
  });

  test('passes through a single chunk unchanged', () => {
    expect(coalesceSpeechSegments(['Only one phrase here.'])).toEqual(['Only one phrase here.']);
  });

  test('chunk-then-coalesce keeps long greetings to a bounded segment count (smooth playback proxy)', () => {
    const text = 'First sentence here. Second sentence here. Third sentence here. '.repeat(20);
    const extracted = extractSpeakableChunks(text, { maxChunkLength: 400 });
    const merged = coalesceSpeechSegments(
      [...extracted.chunks, extracted.remainder].filter(Boolean),
    );
    expect(merged.length).toBeGreaterThan(0);
    expect(merged.length).toBeLessThanOrEqual(12);
  });
});
