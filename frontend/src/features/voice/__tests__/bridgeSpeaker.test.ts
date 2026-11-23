import { createBridgeSpeaker } from '../localAgent';

describe('the natural voice player', () => {
  const played: number[] = [];
  const sources: { onended: (() => void) | null; stop: jest.Mock }[] = [];
  const browserSaid: string[] = [];

  beforeEach(() => {
    played.length = 0;
    sources.length = 0;
    browserSaid.length = 0;
    class FakeContext {
      state = 'running';
      destination = {};
      createAnalyser = () => ({ fftSize: 0, connect: jest.fn(), getFloatTimeDomainData: jest.fn() });
      createBuffer = (_c: number, length: number) => ({ length, getChannelData: () => new Float32Array(length) });
      createBufferSource = () => {
        const source = {
          buffer: null as { length: number } | null,
          onended: null as (() => void) | null,
          connect: jest.fn(),
          start: () => played.push(source.buffer?.length ?? -1),
          stop: jest.fn(),
        };
        sources.push(source);
        return source;
      };
      resume = jest.fn();
    }
    (window as unknown as { AudioContext: unknown }).AudioContext = FakeContext;
    (global as unknown as { SpeechSynthesisUtterance: unknown }).SpeechSynthesisUtterance = class {
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(public text: string) {}
    };
    Object.defineProperty(window, 'speechSynthesis', {
      configurable: true,
      value: {
        getVoices: () => [],
        cancel: jest.fn(),
        speak: (u: { text: string; onend: () => void }) => {
          browserSaid.push(u.text);
          setTimeout(() => u.onend(), 0);
        },
      },
    });
    // Each sentence becomes as many samples as it has characters; "fail" can't be made.
    global.fetch = jest.fn(async (_url: string, init: { body: string }) => {
      const { text } = JSON.parse(init.body);
      if (text.includes('fail')) return { ok: false, headers: new Headers() };
      return {
        ok: true,
        headers: new Headers({ 'x-sample-rate': '24000' }),
        arrayBuffer: async () => new Int16Array(text.length).buffer,
      };
    }) as unknown as typeof fetch;
  });

  const flush = () => new Promise(resolve => setTimeout(resolve, 0));

  it('asks for every sentence at once and plays them in order; one it cannot make is skipped, never read by the browser', async () => {
    jest.useFakeTimers();
    try {
      const speaking: boolean[] = [];
      const speaker = createBridgeSpeaker(s => speaking.push(s));
      speaker.say('First.');
      speaker.say('this will fail');
      speaker.say('Third one.');
      expect(global.fetch).toHaveBeenCalledTimes(3); // all requested up front
      await jest.advanceTimersByTimeAsync(0);
      expect(played).toEqual(['First.'.length]);
      sources[0].onended?.();
      // It keeps asking for the failing one for a while, then moves on.
      for (let i = 0; i < 20; i++) await jest.advanceTimersByTimeAsync(2000);
      expect(browserSaid).toEqual([]);
      expect(played).toEqual(['First.'.length, 'Third one.'.length]);
      sources[1].onended?.();
      await jest.advanceTimersByTimeAsync(0);
      expect(speaking).toEqual([true, false]);
      expect(speaker.speaking).toBe(false);
    } finally {
      jest.useRealTimers();
    }
  });

  it('stops at once when interrupted', async () => {
    const speaker = createBridgeSpeaker(() => undefined);
    speaker.say('A long first sentence.');
    speaker.say('And more.');
    await flush();
    speaker.cancel();
    expect(sources[0].stop).toHaveBeenCalled();
    expect(speaker.speaking).toBe(false);
    sources[0].onended?.();
    await flush();
    expect(played).toHaveLength(1); // the second sentence never plays
  });
});

it('splits a long sentence at its pauses so the voice can start on the first piece', async () => {
  const { speechPieces } = await import('../localAgent');
  expect(speechPieces('A cap table is a record of who owns what share of a company, listing each founder, investor, and option holder.')).toEqual([
    'A cap table is a record of who owns what share of a company,',
    'listing each founder, investor, and option holder.',
  ]);
  expect(speechPieces('Yes, it is.')).toEqual(['Yes, it is.']);
  expect(speechPieces('No pauses in this one at all')).toEqual(['No pauses in this one at all']);
});
