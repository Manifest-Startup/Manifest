import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { MockedProvider } from '@apollo/client/testing/react';
import { MemoryRouter } from 'react-router-dom';

import { useLocalAgentVoiceSession } from '../useLocalAgentVoiceSession';

type Rec = { onresult: (e: unknown) => void; onend: () => void; start: jest.Mock; abort: jest.Mock };
type Utterance = { text: string; onend: (() => void) | null };

const result = (transcript: string, isFinal: boolean) => ({
  resultIndex: 0,
  results: [Object.assign([{ transcript }], { isFinal })],
});

describe('useLocalAgentVoiceSession', () => {
  const recognitions: Rec[] = [];
  const speaking: Utterance[] = [];
  const cancel = jest.fn();
  const signals: AbortSignal[] = [];
  let answer = 'Two ideas.';
  let keepOpen = false;

  beforeEach(() => {
    recognitions.length = 0;
    speaking.length = 0;
    signals.length = 0;
    cancel.mockReset();
    answer = 'Two ideas.';
    keepOpen = false;
    (window as unknown as { webkitSpeechRecognition: unknown }).webkitSpeechRecognition = class {
      start = jest.fn();
      abort = jest.fn();
      constructor() {
        recognitions.push(this as unknown as Rec);
      }
    };
    (global as unknown as { SpeechSynthesisUtterance: unknown }).SpeechSynthesisUtterance = class {
      onend: (() => void) | null = null;
      constructor(public text: string) {}
    };
    // Speech stays "in progress" until a test finishes it, so barge-in can be tried.
    Object.defineProperty(window, 'speechSynthesis', {
      configurable: true,
      value: { getVoices: () => [], cancel, speak: (u: Utterance) => speaking.push(u) },
    });
    const encoder = new TextEncoder();
    global.fetch = jest.fn(async (url: string, init?: { signal?: AbortSignal }) => {
      if (url.endsWith('/health')) return { ok: true, json: async () => ({ ok: true, agent: 'Claude Code', interrupt: true }) };
      if (init?.signal) signals.push(init.signal);
      let step = 0;
      return {
        ok: true,
        body: {
          getReader: () => ({
            read: async () => {
              step += 1;
              if (step === 1) return { done: false, value: encoder.encode(JSON.stringify({ kind: 'say', text: answer }) + '\n') };
              if (keepOpen && init?.signal) {
                // Still answering (more sentences to come) until the person talks over it.
                const signal = init.signal;
                await new Promise(resolve => signal.addEventListener('abort', resolve));
                throw new DOMException('aborted', 'AbortError');
              }
              return { done: true, value: undefined };
            },
          }),
        },
      };
    }) as unknown as typeof fetch;
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <MockedProvider>
      <MemoryRouter initialEntries={['/ideas/abc/description']}>{children}</MemoryRouter>
    </MockedProvider>
  );
  const turns = () =>
    (global.fetch as jest.Mock).mock.calls.filter(([url]) => String(url).endsWith('/turn')).map(([, init]) => JSON.parse(init.body).text);

  async function started() {
    const hook = renderHook(() => useLocalAgentVoiceSession(), { wrapper });
    await act(async () => {
      await hook.result.current.start();
    });
    return hook;
  }

  it('listens at once, sends the question when the person pauses and speaks the answer', async () => {
    const { result: session } = await started();
    expect(speaking).toHaveLength(0); // no greeting to sit through
    expect(session.current.state.phase).toBe('listening');
    const rec = recognitions[0];
    act(() => rec.onresult(result('What ideas do I have?', true)));
    await waitFor(() => expect(speaking.map(u => u.text)).toEqual(['Two ideas.']));
    expect(turns()).toEqual(['What ideas do I have?']);
    const turnCall = (global.fetch as jest.Mock).mock.calls.find(([url]) => String(url).endsWith('/turn'));
    expect(JSON.parse(turnCall[1].body)).toMatchObject({ context: { idea_id: 'abc' } });
    expect(rec.abort).not.toHaveBeenCalled(); // the mic stays open while it talks
    await act(async () => {
      speaking[0].onend?.();
    });
    expect(session.current.state.phase).toBe('listening');
  });

  it("doesn't wait for the browser's final result once the words stop changing", async () => {
    await started();
    const rec = recognitions[0];
    act(() => rec.onresult(result('summarise my pitch', false)));
    await waitFor(() => expect(turns()).toEqual(['summarise my pitch']), { timeout: 2000 });
    expect(rec.abort).toHaveBeenCalled(); // forget its late "final" copy of the same words
  });

  it('ignores its own voice coming back, but stops when the person talks over it', async () => {
    answer = 'You have two ideas about solar panels and one about coffee.';
    keepOpen = true;
    await started();
    const rec = recognitions[0];
    act(() => rec.onresult(result('What ideas do I have?', true)));
    await waitFor(() => expect(speaking).toHaveLength(1));
    const firstTurn = signals[0];
    cancel.mockClear(); // starting the turn cleared any old speech

    act(() => rec.onresult(result('two ideas about solar panels', false))); // echo through the speakers
    expect(cancel).not.toHaveBeenCalled();

    act(() => rec.onresult(result('wait, open the coffee one', false)));
    expect(cancel).toHaveBeenCalled();
    expect(firstTurn.aborted).toBe(true); // the bridge stops the agent's answer
    await waitFor(() => expect(turns()).toEqual(['What ideas do I have?', 'wait, open the coffee one']), { timeout: 2000 });
  });

  it('stops speaking when tapped', async () => {
    const { result: session } = await started();
    act(() => recognitions[0].onresult(result('hello', true)));
    await waitFor(() => expect(session.current.state.phase).toBe('speaking'));
    act(() => session.current.interrupt?.());
    expect(cancel).toHaveBeenCalled();
    expect(session.current.state.phase).toBe('listening');
  });

  it("doesn't answer the late echo of its own voice after it stops", async () => {
    answer = 'A cap table lists who owns what in your company.';
    await started();
    const rec = recognitions[0];
    act(() => rec.onresult(result('what is a cap table', true)));
    await waitFor(() => expect(speaking).toHaveLength(1));
    await act(async () => {
      speaking[0].onend?.(); // it finished speaking…
    });
    act(() => rec.onresult(result('a cap table lists who owns what', true))); // …and its echo arrives late
    await new Promise(resolve => setTimeout(resolve, 600));
    expect(turns()).toEqual(['what is a cap table']); // it didn't answer itself
    act(() => rec.onresult(result('great, and dilution?', true))); // the person can still talk
    await waitFor(() => expect(turns()).toEqual(['what is a cap table', 'great, and dilution?']), { timeout: 2000 });
  });

  it('says so, with the fix, when the natural voice is missing from the install (#108)', async () => {
    const answerOnce = global.fetch as jest.Mock;
    global.fetch = jest.fn(async (url: string, init?: unknown) => {
      if (url.endsWith('/health')) {
        return {
          ok: true,
          json: async () => ({
            ok: true,
            agent: 'Claude Code',
            speech: null,
            speech_status: "natural voice not installed: install it with: pip install 'manifest-mcp[natural-voice]'",
          }),
        };
      }
      return answerOnce(url, init);
    }) as unknown as typeof fetch;
    const { result: session } = await started();
    const note = session.current.state.activity.find(item => item.id === 'natural-voice-missing');
    expect(note?.label).toContain('voice.sh');
    expect(session.current.state.phase).toBe('listening'); // the conversation still works
  });

  it('switches to the natural voice as soon as it finishes loading, mid-conversation', async () => {
    let voiceReady = false;
    const speakCalls: string[] = [];
    class FakeContext {
      state = 'running';
      destination = {};
      createAnalyser = () => ({ fftSize: 0, connect: jest.fn(), getFloatTimeDomainData: jest.fn() });
      createBuffer = (_c: number, length: number) => ({ length, getChannelData: () => new Float32Array(length) });
      createBufferSource = () => ({ connect: jest.fn(), start: jest.fn(), stop: jest.fn(), onended: null });
      resume = jest.fn();
    }
    (window as unknown as { AudioContext: unknown }).AudioContext = FakeContext;
    const answerOnce = global.fetch as jest.Mock;
    global.fetch = jest.fn(async (url: string, init?: { body?: string; signal?: AbortSignal }) => {
      if (url.endsWith('/health')) {
        return {
          ok: true,
          json: async () => ({
            ok: true,
            agent: 'Claude Code',
            speech: voiceReady ? 'af_heart' : null,
            speech_status: voiceReady ? 'ready' : 'loading',
          }),
        };
      }
      if (url.endsWith('/speak')) {
        speakCalls.push(JSON.parse(init?.body ?? '{}').text);
        return { ok: true, headers: new Headers(), arrayBuffer: async () => new Int16Array(8).buffer };
      }
      return answerOnce(url, init);
    }) as unknown as typeof fetch;

    jest.useFakeTimers();
    try {
      const hook = renderHook(() => useLocalAgentVoiceSession(), { wrapper });
      await act(async () => {
        await hook.result.current.start();
      });
      voiceReady = true; // the bridge finished loading Kokoro
      await act(async () => {
        await jest.advanceTimersByTimeAsync(4100);
      });
      act(() => recognitions[0].onresult(result('hello there', true)));
      await act(async () => {
        await jest.advanceTimersByTimeAsync(400);
      });
      await act(async () => {
        await jest.advanceTimersByTimeAsync(50);
      });
      expect(speakCalls).toEqual(['Two ideas.']); // the natural voice, not the browser's
      expect(speaking).toHaveLength(0);
    } finally {
      jest.useRealTimers();
      delete (window as unknown as { AudioContext?: unknown }).AudioContext;
    }
  });
});
