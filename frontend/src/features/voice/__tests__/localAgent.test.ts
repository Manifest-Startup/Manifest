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

  it('finds a running bridge and quietly reports none otherwise', async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true, agent: 'Claude Code' }) }) as never;
    await expect(probeBridge()).resolves.toEqual({ agent: 'Claude Code', voice: null, interrupt: false });
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
