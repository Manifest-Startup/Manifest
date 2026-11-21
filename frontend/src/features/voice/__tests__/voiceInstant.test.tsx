import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { isBargeIn, pickVoice, VOICE_SETUP_COMMAND } from '../localAgent';
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

it('prefers a natural local voice and never a remote one first', () => {
  const v = (name: string, localService = true, lang = 'en-US') => ({ name, lang, localService, default: false }) as SpeechSynthesisVoice;
  expect(pickVoice([v('Google US English', false), v('Albert'), v('Samantha')], 'en-US')?.name).toBe('Samantha');
  expect(pickVoice([v('Samantha'), v('Ava (Premium)')], 'en-GB')?.name).toBe('Ava (Premium)');
  expect(pickVoice([v('Thomas', true, 'fr-FR')], 'en-US')).toBeNull();
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
  expect(onReady).toHaveBeenCalledWith({ agent: 'Codex', voice: null, interrupt: true });
  jest.useRealTimers();
});
