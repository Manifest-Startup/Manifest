import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { MockedProvider } from '@apollo/client/testing/react';
import { MemoryRouter } from 'react-router-dom';

import { useLocalAgentVoiceSession } from '../useLocalAgentVoiceSession';

type Rec = { onresult: (e: unknown) => void; onend: () => void; start: jest.Mock; abort: jest.Mock };

describe('useLocalAgentVoiceSession', () => {
  const recognitions: Rec[] = [];
  const spoken: string[] = [];
  let finishTurn: () => void = () => undefined;

  beforeEach(() => {
    recognitions.length = 0;
    spoken.length = 0;
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
    Object.defineProperty(window, 'speechSynthesis', {
      configurable: true,
      value: {
        getVoices: () => [],
        cancel: jest.fn(),
        speak: (u: { text: string; onend: () => void }) => {
          spoken.push(u.text);
          setTimeout(() => u.onend(), 0);
        },
      },
    });
    const encoder = new TextEncoder();
    global.fetch = jest.fn(async (url: string) => {
      if (url.endsWith('/health')) return { ok: true, json: async () => ({ ok: true, agent: 'Claude Code' }) };
      // The answer streams at once; "done" only comes later (Claude Code's Stop hooks).
      let step = 0;
      const late = new Promise<void>(resolve => (finishTurn = resolve));
      return {
        ok: true,
        body: {
          getReader: () => ({
            read: async () => {
              step += 1;
              if (step === 1) return { done: false, value: encoder.encode('{"kind":"say","text":"Two ideas."}\n') };
              await late;
              return { done: true, value: undefined };
            },
          }),
        },
      };
    }) as unknown as typeof fetch;
  });

  it('greets, sends a spoken turn to the agent, speaks the answer and listens again before the agent is done', async () => {
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <MockedProvider>
        <MemoryRouter initialEntries={['/ideas/abc/description']}>{children}</MemoryRouter>
      </MockedProvider>
    );
    const { result } = renderHook(() => useLocalAgentVoiceSession(), { wrapper });
    await act(async () => {
      await result.current.start();
    });
    expect(spoken).toEqual(['Claude Code is listening.']);
    await waitFor(() => expect(result.current.state.phase).toBe('listening'));
    const rec = recognitions[0];
    const startsBefore = rec.start.mock.calls.length;

    await act(async () => {
      rec.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: 'What ideas do I have?' }], { isFinal: true })] });
    });
    await waitFor(() => expect(spoken).toContain('Two ideas.'));
    const body = JSON.parse((global.fetch as jest.Mock).mock.calls[1][1].body);
    expect(body).toMatchObject({ text: 'What ideas do I have?', context: { idea_id: 'abc' } });
    // Listening again while the agent's turn is still open.
    await waitFor(() => expect(rec.start.mock.calls.length).toBeGreaterThan(startsBefore));
    await act(async () => {
      finishTurn();
      await result.current.end();
    });
    expect(result.current.state.captions.map(c => c.text)).toEqual(['What ideas do I have?', 'Two ideas.']);
  });
});
