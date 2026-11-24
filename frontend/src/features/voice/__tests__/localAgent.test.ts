import { probeBridge, runBridgeTurn, startRecognition } from '../localAgent';

function streamed(chunks: string[]) {
  const encoder = new TextEncoder();
  let i = 0;
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: async () =>
          i < chunks.length ? { done: false, value: encoder.encode(chunks[i++]) } : { done: true, value: undefined },
      }),
    },
  };
}

describe('local agent bridge', () => {
  afterEach(() => jest.restoreAllMocks());

  it('reads sentences and actions as the agent streams them, across chunk boundaries', async () => {
    const fetchMock = jest.fn().mockResolvedValue(
      streamed(['{"kind":"tool","text":"Read"}\n{"kind":"say","te', 'xt":"You have two ideas."}\n', '{"kind":"done","text":""}\n']),
    );
    global.fetch = fetchMock as unknown as typeof fetch;
    const events: unknown[] = [];
    await runBridgeTurn('what ideas do I have', { path: '/ideas/a1', ideaId: 'a1' }, e => events.push(e));
    expect(events).toEqual([
      { kind: 'tool', text: 'Read' },
      { kind: 'say', text: 'You have two ideas.' },
      { kind: 'done', text: '' },
    ]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://127.0.0.1:47821/turn');
    expect(JSON.parse(init.body)).toMatchObject({ text: 'what ideas do I have', context: { idea_id: 'a1' } });
  });

  it('sends the opt-in tone cue with a turn, and nothing when it is off', async () => {
    const fetchMock = jest.fn().mockResolvedValue(streamed(['{"kind":"done","text":""}\n']));
    global.fetch = fetchMock as unknown as typeof fetch;
    const tone = { label: 'energized' as const, arousal: 0.8, confidence: 0.6, signs: ['faster than usual' as const] };
    await runBridgeTurn('let us go', { path: '/' }, () => undefined, undefined, tone);
    await runBridgeTurn('let us go', { path: '/' }, () => undefined);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).tone).toEqual(tone);
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).not.toHaveProperty('tone');
  });

  it('finds a running bridge and quietly reports none otherwise', async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true, agent: 'Claude Code' }) }) as never;
    await expect(probeBridge()).resolves.toEqual({ agent: 'Claude Code', voice: null, interrupt: false, speech: null, ready: true, problem: null, warning: null, agents: [] });
    global.fetch = jest.fn().mockRejectedValue(new TypeError('Failed to fetch')) as never;
    await expect(probeBridge()).resolves.toBeNull();
  });

  it("keeps the browser's recognition going and reports interim then final text", () => {
    const instances: Record<string, unknown>[] = [];
    class FakeRecognition {
      start = jest.fn();
      abort = jest.fn();
      constructor() {
        instances.push(this as unknown as Record<string, unknown>);
      }
    }
    (window as unknown as { webkitSpeechRecognition: unknown }).webkitSpeechRecognition = FakeRecognition;
    const heard: [string, boolean][] = [];
    const control = startRecognition({ onText: (t, f) => heard.push([t, f]), onError: jest.fn() })!;
    const rec = instances[0] as unknown as {
      onresult: (e: unknown) => void;
      onend: () => void;
      start: jest.Mock;
      continuous: boolean;
    };
    expect(rec.continuous).toBe(true);
    const result = (text: string, isFinal: boolean) => Object.assign([{ transcript: text }], { isFinal });
    rec.onresult({ resultIndex: 0, results: [result('solar cold', false)] });
    rec.onresult({ resultIndex: 0, results: [result('Solar cold chain.', true)] });
    expect(heard).toEqual([['solar cold', false], ['Solar cold chain.', true]]);
    rec.onend(); // the browser stopped after a pause: keep listening
    expect(rec.start).toHaveBeenCalledTimes(2);
    control.stop();
    rec.onend();
    expect(rec.start).toHaveBeenCalledTimes(2);
  });
});

it('prefers the HTTPS bridge (all Safari allows) and uses it for every call', async () => {
  const { probeBridge, bridgeUrl, BRIDGE_HTTPS_URL, BRIDGE_URL } = await import('../localAgent');
  const up = new Set<string>();
  global.fetch = jest.fn(async (url: string) => {
    if (![...up].some(base => url.startsWith(base))) throw new TypeError('Load failed');
    return { ok: true, json: async () => ({ ok: true, agent: 'Claude Code' }) };
  }) as never;
  up.add(BRIDGE_URL);
  expect(await probeBridge()).toMatchObject({ agent: 'Claude Code' });
  expect(bridgeUrl()).toBe(BRIDGE_URL); // Chrome, before HTTPS is set up
  up.add(BRIDGE_HTTPS_URL);
  await probeBridge();
  expect(bridgeUrl()).toBe(BRIDGE_HTTPS_URL);
  up.delete(BRIDGE_URL); // Safari: plain HTTP to this computer is blocked
  expect(await probeBridge()).toMatchObject({ agent: 'Claude Code' });
});
