import { getVoiceAgentToken, postVoiceAgentJson, streamVoiceAgentEvents } from '../voiceAgentApi';

describe('voiceAgentApi', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test('returns access_token when present', () => {
    localStorage.setItem('access_token', 'token-a');
    localStorage.setItem('sb-access-token', 'token-b');

    expect(getVoiceAgentToken()).toBe('token-a');
  });

  test('falls back to sb-access-token when access_token is missing', () => {
    localStorage.setItem('sb-access-token', 'legacy-token');

    expect(getVoiceAgentToken()).toBe('legacy-token');
  });

  test('disables network calls during tests', async () => {
    await expect(postVoiceAgentJson('/api/voice-agent/process', { user_message: 'hello' }))
      .rejects
      .toThrow('Voice agent network calls are disabled in tests');
  });

  test('disables stream calls during tests', async () => {
    await expect(
      streamVoiceAgentEvents('/api/voice-agent/process-stream', { user_message: 'hello' }, jest.fn()),
    ).rejects.toThrow('Voice agent network calls are disabled in tests');
  });
});

