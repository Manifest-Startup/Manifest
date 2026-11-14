import { extractSpeakableChunks } from '../sentenceChunker';

describe('extractSpeakableChunks', () => {
  test('returns complete sentences and leaves the trailing partial sentence', () => {
    expect(
      extractSpeakableChunks('You have a strong wedge. What customer switches first because of it'),
    ).toEqual({
      chunks: ['You have a strong wedge.'],
      remainder: 'What customer switches first because of it',
    });
  });

  test('does not split decimal numbers', () => {
    expect(
      extractSpeakableChunks('Charge 19.99 per month. Then expand upmarket'),
    ).toEqual({
      chunks: ['Charge 19.99 per month.'],
      remainder: 'Then expand upmarket',
    });
  });

  test('does not split known abbreviations', () => {
    expect(
      extractSpeakableChunks('Talk to Dr. Patel before expanding. Then ask about the sales motion'),
    ).toEqual({
      chunks: ['Talk to Dr. Patel before expanding.'],
      remainder: 'Then ask about the sales motion',
    });
  });

  test('cuts oversized chunks at safe breaks', () => {
    const result = extractSpeakableChunks(
      'This is a deliberately long streaming thought that should pause near a safe break before it gets too large for one chunk of generated speech',
      { maxChunkLength: 70 },
    );

    expect(result.chunks[0]).toContain('deliberately long streaming thought');
    expect(result.remainder.length).toBeGreaterThan(0);
  });

  test('emits earlier chunks at clause boundaries when max length reached', () => {
    // Streaming partial buffer (no trailing period) so remainder stays non-empty.
    const text =
      'First clause here, second clause follows with enough characters to exceed the limit soon after the comma';
    const result = extractSpeakableChunks(text, { maxChunkLength: 55 });

    expect(result.chunks.length).toBeGreaterThanOrEqual(1);
    expect(result.chunks[0]).toContain('First clause here');
    expect(result.remainder.length).toBeGreaterThan(0);
  });

  describe('firstChunkMaxLength (fast time-to-first-audio)', () => {
    test('caps only the first chunk; later chunks use the larger window', () => {
      const text =
        'This opening clause is intentionally long enough to exceed the tight first cap, then the rest of the answer keeps streaming on with plenty of additional words before any sentence ends here.';
      const result = extractSpeakableChunks(text, {
        maxChunkLength: 400,
        firstChunkMaxLength: 60,
      });

      // First chunk is small so the opening clause synthesizes and plays fast.
      expect(result.chunks[0].length).toBeLessThanOrEqual(60);
      // Subsequent content is allowed to grow well past the first cap.
      const rest = [...result.chunks.slice(1), result.remainder].join(' ').trim();
      expect(rest.length).toBeGreaterThan(60);
    });

    test('a short first sentence still emits immediately without padding', () => {
      const result = extractSpeakableChunks('Got it. Now tell me about the customer', {
        maxChunkLength: 400,
        firstChunkMaxLength: 140,
      });

      expect(result.chunks[0]).toBe('Got it.');
      expect(result.remainder).toBe('Now tell me about the customer');
    });

    test('matches default behavior when first cap is not smaller than max', () => {
      const text = 'You have a strong wedge. What customer switches first because of it';
      expect(extractSpeakableChunks(text, { maxChunkLength: 280, firstChunkMaxLength: 280 })).toEqual(
        extractSpeakableChunks(text, { maxChunkLength: 280 }),
      );
    });
  });
});
