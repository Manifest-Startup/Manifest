import { buildTranscriptTurns, displayTextForConversationMessage } from '../voiceConversationDisplay';

describe('voiceConversationDisplay', () => {
  test('parses assistant JSON history to the spoken message field', () => {
    const text = displayTextForConversationMessage({
      role: 'assistant',
      content: JSON.stringify({
        message: 'Hello from the advisor.',
        is_qualified: false,
      }),
    });
    expect(text).toBe('Hello from the advisor.');
  });

  test('returns empty string for assistant JSON with empty message', () => {
    expect(
      displayTextForConversationMessage({
        role: 'assistant',
        content: JSON.stringify({ message: '', is_qualified: false }),
      }),
    ).toBe('');
  });

  test('falls back to raw assistant string when JSON is invalid', () => {
    expect(
      displayTextForConversationMessage({
        role: 'assistant',
        content: 'Plain fallback line',
      }),
    ).toBe('Plain fallback line');
  });

  test('buildTranscriptTurns skips empty and keeps user lines', () => {
    const turns = buildTranscriptTurns([
      { role: 'assistant', content: JSON.stringify({ message: 'Hi', is_qualified: false }) },
      { role: 'user', content: '  ' },
      { role: 'user', content: 'My idea is X' },
    ]);
    expect(turns.map(t => t.text)).toEqual(['Hi', 'My idea is X']);
  });
});
