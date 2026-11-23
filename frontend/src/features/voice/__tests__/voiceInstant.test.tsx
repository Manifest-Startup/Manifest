import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { isBargeIn, isEcho, startRecognition, VOICE_SETUP_COMMAND } from '../localAgent';
import { isFatalVoiceError } from '../usePipecatVoiceSession';
import VoiceSetup from '../VoiceSetup';

describe('telling the person from the voice’s own echo', () => {
  const said = 'You have two ideas about solar panels and one about coffee.';
  it('ignores words it is saying itself', () => {
    expect(isBargeIn('two ideas about solar panels', said)).toBe(false);
    expect(isBargeIn('coffee', said)).toBe(false);
    expect(isBargeIn('', said)).toBe(false);
  });
  it('stops for "stop" / "wait" or two words of something else', () => {
    expect(isBargeIn('stop', said)).toBe(true);
    expect(isBargeIn('Wait', said)).toBe(true);
    expect(isBargeIn('open the coffee one', said)).toBe(true);
    expect(isBargeIn('hmm', said)).toBe(false); // one stray word isn't enough
  });
});

it('only a fatal Pipecat error ends the conversation (no red orb after a hiccup)', () => {
  expect(isFatalVoiceError({ message: 'TTS context completed with no audio', fatal: false })).toBe(false);
  expect(isFatalVoiceError({ message: 'Invalid API key', fatal: true })).toBe(true);
  expect(isFatalVoiceError({ message: 'old servers send no flag' })).toBe(true);
});

it('setup shows one command and connects by itself once the Mac answers', async () => {
  jest.useFakeTimers();
  let up = false;
  global.fetch = jest.fn(async () => {
    if (!up) throw new TypeError('Failed to fetch');
    return { ok: true, json: async () => ({ ok: true, agent: 'Codex', interrupt: true }) };
  }) as unknown as typeof fetch;
  const onReady = jest.fn();
  render(
    <MemoryRouter>
      <VoiceSetup onReady={onReady} />
    </MemoryRouter>,
  );
  expect(screen.getByText(VOICE_SETUP_COMMAND)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'add an OpenAI key' })).toHaveAttribute('href', '/account#ai-key');
  await act(async () => {
    await jest.advanceTimersByTimeAsync(2100);
  });
  expect(onReady).not.toHaveBeenCalled();
  up = true; // the person ran the command
  await act(async () => {
    await jest.advanceTimersByTimeAsync(2100);
  });
  expect(onReady).toHaveBeenCalledWith({ agent: 'Codex', voice: null, interrupt: true, speech: null });
  jest.useRealTimers();
});

it('the late tail of its own voice is echo; new words are not', () => {
  const said = 'A cap table lists who owns what in your company.';
  expect(isEcho('who owns what in your company', said)).toBe(true);
  expect(isEcho('and what about dilution', said)).toBe(false);
});

it('hears through the echo-cancelled mic when the browser can, and its own mic otherwise', () => {
  const calls: unknown[][] = [];
  let takesTrack = true;
  (window as unknown as { webkitSpeechRecognition: unknown }).webkitSpeechRecognition = class {
    start(...args: unknown[]) {
      if (args.length && !takesTrack) throw new TypeError('not a MediaStreamTrack');
      calls.push(args);
    }
    abort() {}
  };
  const track = { readyState: 'live' } as MediaStreamTrack;
  startRecognition({ onText: () => undefined, onError: () => undefined }, track);
  expect(calls[0]).toEqual([track]);
  takesTrack = false;
  startRecognition({ onText: () => undefined, onError: () => undefined }, track);
  expect(calls[1]).toEqual([]); // fell back to the browser's own mic
});
