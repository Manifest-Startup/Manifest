import { createBridgeSpeaker, createSpeaker, isBargeIn } from '../localAgent';

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

  it('asks for every sentence at once and plays them in order, the browser covering a failed one', async () => {
    const speaking: boolean[] = [];
    const speaker = createBridgeSpeaker(s => speaking.push(s));
    speaker.say('First.');
    speaker.say('this will fail');
    speaker.say('Third one.');
    expect(global.fetch).toHaveBeenCalledTimes(3); // all requested up front
    await flush();
    expect(played).toEqual(['First.'.length]);
    sources[0].onended?.();
    await flush();
    await flush();
    expect(browserSaid).toEqual(['this will fail']);
    await flush();
    expect(played).toEqual(['First.'.length, 'Third one.'.length]);
    sources[1].onended?.();
    await flush();
    expect(speaking).toEqual([true, false]);
    expect(speaker.speaking).toBe(false);
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

  // The log behind this: Claude queued five sentences while the second was still playing,
  // `recent` held only the last three queued, and the second's echo ("so I need two
  // things") was taken for the person talking over it.
  const answer = [
    "I've loaded the feedback tool, but I haven't filed anything yet.",
    "It posts a public GitHub issue on Manifest's repository, so I need two things from you first.",
    'What is the feedback about, in your words?',
    'And should it be a bug, an enhancement, an improvement, or general feedback?',
    "Once you tell me, I'll file it and let you know whether it matched an existing issue.",
  ];

  it("knows its own words while they're still queued, so their echo isn't a barge-in", async () => {
    const speaker = createBridgeSpeaker(() => undefined);
    for (const sentence of answer) speaker.say(sentence);
    await flush();
    sources[0].onended?.(); // the second sentence is playing; three more are queued
    await flush();
    expect(isBargeIn('so I need two things', speaker.recent)).toBe(false);
    expect(isBargeIn('actually open my pitch deck', speaker.recent)).toBe(true);
  });

  it('the browser voice does the same', () => {
    const speaker = createSpeaker(() => undefined);
    for (const sentence of answer) speaker.say(sentence);
    expect(isBargeIn('so I need two things', speaker.recent)).toBe(false);
    expect(isBargeIn("I've loaded the feedback tool", speaker.recent)).toBe(false);
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
