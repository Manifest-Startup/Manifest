import {
  buildLiveVoiceUrl,
  classifyConnectionError,
  fetchLiveVoiceStatus,
  INITIAL_LIVE_VOICE_STATE,
  interpretServerMessage,
  liveVoiceReducer,
  LiveVoiceEvent,
  LiveVoiceState,
  resolveVoicePath,
  suggestionsFor,
} from '../liveVoice';

const run = (events: LiveVoiceEvent[], from: LiveVoiceState = INITIAL_LIVE_VOICE_STATE) =>
  events.reduce(liveVoiceReducer, from);

describe('liveVoiceReducer', () => {
  test('moves through a spoken turn', () => {
    let state = run([{ type: 'connecting' }, { type: 'ready' }]);
    expect(state.phase).toBe('listening');
    state = run([{ type: 'userStarted' }, { type: 'userInput', text: 'list my', final: false }], state);
    expect(state.captions).toEqual([expect.objectContaining({ role: 'user', text: 'list my', final: false })]);
    state = run([{ type: 'userInput', text: 'list my ideas', final: true }, { type: 'userStopped' }], state);
    expect(state.captions).toHaveLength(1);
    expect(state.captions[0]).toMatchObject({ text: 'list my ideas', final: true });
    expect(state.phase).toBe('thinking');
    state = run(
      [
        { type: 'botStarted' },
        { type: 'botOutput', text: 'You have two ideas.' },
        { type: 'botOutput', text: 'Want the newest?' },
      ],
      state,
    );
    expect(state.phase).toBe('speaking');
    expect(state.captions[1]).toMatchObject({ role: 'assistant', text: 'You have two ideas. Want the newest?' });
    state = run([{ type: 'botStopped' }], state);
    expect(state.phase).toBe('listening');
    expect(state.captions[1].final).toBe(true);
  });

  test('a new bot turn after the user speaks starts a new caption', () => {
    const state = run([
      { type: 'connecting' },
      { type: 'ready' },
      { type: 'botOutput', text: 'Hi.' },
      { type: 'userInput', text: 'hello', final: true },
      { type: 'botOutput', text: 'What now?' },
    ]);
    expect(state.captions.map(c => [c.role, c.text])).toEqual([
      ['assistant', 'Hi.'],
      ['user', 'hello'],
      ['assistant', 'What now?'],
    ]);
  });

  test('updates tool activity in place and keeps errors sticky on disconnect', () => {
    let state = run([
      { type: 'tool', activity: { id: 'c1', label: 'Create idea', status: 'running' } },
      { type: 'tool', activity: { id: 'c1', label: 'Create idea', status: 'done', summary: 'Done' } },
    ]);
    expect(state.activity).toEqual([{ id: 'c1', label: 'Create idea', status: 'done', summary: 'Done' }]);
    state = run([{ type: 'error', error: { kind: 'connection', message: 'x' } }, { type: 'disconnected' }], state);
    expect(state.phase).toBe('error');
  });
});

describe('interpretServerMessage', () => {
  test('maps the Manifest message types', () => {
    expect(interpretServerMessage({ type: 'manifest.navigate', path: '/ideas/abc/business-model-canvas' })).toEqual({
      kind: 'navigate',
      path: '/ideas/abc/business-model-canvas',
    });
    expect(interpretServerMessage({ type: 'manifest.changed', tool: 'create_idea' })).toEqual({ kind: 'refresh' });
    expect(interpretServerMessage({ type: 'manifest.end' })).toEqual({ kind: 'end' });
    expect(
      interpretServerMessage({ type: 'manifest.tool', phase: 'started', id: 't1', name: 'idea', label: 'Idea' }),
    ).toEqual({ kind: 'activity', activity: { id: 't1', label: 'Idea', status: 'running', summary: undefined } });
    expect(
      interpretServerMessage({
        type: 'manifest.tool',
        phase: 'finished',
        id: 't2',
        label: 'Delete idea',
        ok: true,
        summary: 'Waiting for your yes',
      }),
    ).toMatchObject({ activity: { status: 'confirm' } });
    expect(
      interpretServerMessage({ type: 'manifest.tool', phase: 'finished', id: 't3', label: 'X', ok: false }),
    ).toMatchObject({ activity: { status: 'failed' } });
  });

  test('ignores unknown or unsafe messages', () => {
    expect(interpretServerMessage(null)).toBeNull();
    expect(interpretServerMessage({ type: 'other' })).toBeNull();
    expect(interpretServerMessage({ type: 'manifest.navigate', path: 'https://evil.example' })).toBeNull();
    expect(interpretServerMessage({ type: 'manifest.navigate', path: '//evil.example' })).toBeNull();
    expect(interpretServerMessage({ type: 'manifest.tool', phase: 'started' })).toBeNull();
  });
});

describe('paths and urls', () => {
  test('accepts only same-origin app routes', () => {
    expect(resolveVoicePath('/account#ai-key')).toBe('/account#ai-key');
    expect(resolveVoicePath('/ideas/i-1/pitch-deck')).toBe('/ideas/i-1/pitch-deck');
    expect(resolveVoicePath('//evil.example/x')).toBeNull();
    expect(resolveVoicePath('/messages')).toBe('/messages');
    expect(resolveVoicePath('javascript:alert(1)')).toBeNull();
  });

  test('builds the WebSocket url without credentials', () => {
    expect(
      buildLiveVoiceUrl({ protocol: 'https:', host: 'manifeststartup.com' }, { path: '/ideas/a/description', ideaId: 'a' }),
    ).toBe('wss://manifeststartup.com/api/voice-agent/live?path=%2Fideas%2Fa%2Fdescription&idea_id=a');
    expect(buildLiveVoiceUrl({ protocol: 'http:', host: 'localhost:5173' }, { path: '/ideas' })).toBe(
      'ws://localhost:5173/api/voice-agent/live?path=%2Fideas',
    );
  });

  test('classifies close codes and microphone errors', () => {
    expect(classifyConnectionError('websocket connection closed. Code: 4402').kind).toBe('no_api_key');
    expect(classifyConnectionError('WebSocket connection error (4401): x').kind).toBe('sign_in');
    expect(classifyConnectionError('NotAllowedError Permission denied').kind).toBe('microphone');
    expect(classifyConnectionError(undefined).kind).toBe('connection');
  });

  test('suggests things for the current page', () => {
    expect(suggestionsFor({ path: '/ideas/a/description', ideaId: 'a' })[1]).toMatch(/pitch deck/);
    expect(suggestionsFor({ path: '/ideas' })).toContain('Start a new idea');
  });
});

describe('fetchLiveVoiceStatus', () => {
  const realFetch = global.fetch;
  afterEach(() => {
    global.fetch = realFetch;
  });

  test('reads the probe and never throws', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ available: false, reason: 'no_api_key', message: 'Add a key' }),
    }) as unknown as typeof fetch;
    await expect(fetchLiveVoiceStatus()).resolves.toEqual({
      available: false,
      reason: 'no_api_key',
      message: 'Add a key',
    });
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 401 }) as unknown as typeof fetch;
    await expect(fetchLiveVoiceStatus()).resolves.toMatchObject({ reason: 'sign_in' });
    global.fetch = jest.fn().mockRejectedValue(new Error('offline')) as unknown as typeof fetch;
    await expect(fetchLiveVoiceStatus()).resolves.toMatchObject({ available: false, reason: 'offline' });
  });
});
