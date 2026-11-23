import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MockedProvider } from '@apollo/client/testing/react';

import { FORGET_MEMORY, GET_MEMORIES, SAVE_VOICE_CONVERSATION } from 'features/core/apollo/queries';
import RememberedToast from '../RememberedToast';
import { MemorySection } from '../MemorySection';
import { ConversationRecorder, finishConversation, MEMORIES_SAVED_EVENT } from 'features/voice/voiceMemory';

// jest.setup.js stubs useMutation; these tests check the real mutations.
jest.mock('@apollo/client/react', () => jest.requireActual('@apollo/client/react'));

const memory = (id: string, text: string, ideaTitle: string | null = 'TideLine') => ({
  __typename: 'Memory',
  id,
  text,
  kind: 'decision',
  ideaId: ideaTitle ? 'idea-tide' : null,
  ideaTitle,
  source: 'voice',
  conversation: null,
  createdAt: '2026-11-22T21:05:00+00:00',
  updatedAt: '2026-11-22T21:05:00+00:00',
  path: `Memory/${ideaTitle ?? 'General'}/${text}.md`,
});

test('the recorder keeps every caption of the conversation, latest text wins', () => {
  const recorder = new ConversationRecorder();
  recorder.record([{ id: 1, role: 'user', text: 'Sell to', final: false }], 'idea-tide');
  recorder.record([
    { id: 1, role: 'user', text: 'Sell to insurers first', final: true },
    { id: 2, role: 'assistant', text: 'Insurers it is.', final: true },
  ]);
  recorder.record([{ id: 3, role: 'assistant', text: '  ', final: true }]); // the panel dropped 1 and 2
  expect(recorder.turns()).toEqual([
    { role: 'user', text: 'Sell to insurers first' },
    { role: 'assistant', text: 'Insurers it is.' },
  ]);
  expect(recorder.ideaId).toBe('idea-tide');
  expect(recorder.startedAt).not.toBeNull();
  expect(new ConversationRecorder().heardSomeone).toBe(false);
});

test('local voice: the agent wraps up first, then the transcript is saved and the app is told', async () => {
  const recorder = new ConversationRecorder();
  recorder.record([{ id: 1, role: 'user', text: 'Insurers first', final: true }], 'idea-tide');
  const order: string[] = [];
  const wrapUp = jest.fn(async () => {
    order.push('wrap-up');
    return 1;
  });
  const saved = memory('mem_1', 'Sells to insurers first.');
  const apollo = {
    mutate: jest.fn(async (options: { mutation: unknown; variables: Record<string, unknown> }) => {
      order.push('save');
      expect(options.mutation).toBe(SAVE_VOICE_CONVERSATION);
      expect(options.variables).toMatchObject({ ideaId: 'idea-tide', agent: 'Claude Code', extract: false });
      return { data: { saveVoiceConversation: { path: 'Conversations/x.md', turns: 1, memories: [saved] } } };
    }),
  };
  const heard = jest.fn();
  window.addEventListener(MEMORIES_SAVED_EVENT, heard);
  const result = await finishConversation({ apollo: apollo as never, recorder, localAgent: 'Claude Code', wrapUp });
  window.removeEventListener(MEMORIES_SAVED_EVENT, heard);
  expect(order).toEqual(['wrap-up', 'save']);
  expect(result?.memories).toEqual([saved]);
  expect(heard).toHaveBeenCalledTimes(1);
});

test('nothing is saved when the person never spoke', async () => {
  const apollo = { mutate: jest.fn() };
  expect(await finishConversation({ apollo: apollo as never, recorder: new ConversationRecorder() })).toBeNull();
  expect(apollo.mutate).not.toHaveBeenCalled();
});

test('after a conversation it shows what was remembered, with an undo for each', async () => {
  const forget = jest.fn(() => ({ data: { forgetMemory: { __typename: 'Memory', id: 'mem_2' } } }));
  render(
    <MockedProvider mocks={[{ request: { query: FORGET_MEMORY, variables: { memoryId: 'mem_2' } }, result: forget }]}>
      <RememberedToast />
    </MockedProvider>,
  );
  expect(screen.queryByTestId('remembered-toast')).toBeNull();
  act(() => {
    window.dispatchEvent(
      new CustomEvent(MEMORIES_SAVED_EVENT, {
        detail: { path: 'Conversations/x.md', memories: [memory('mem_1', 'Insurers first.'), memory('mem_2', 'Pilot in Mumbai.')] },
      }),
    );
  });
  expect(screen.getByText('Remembered 2 things')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Forget: Pilot in Mumbai.' }));
  expect(screen.queryByText('Pilot in Mumbai.')).toBeNull();
  await waitFor(() => expect(forget).toHaveBeenCalled());
});

test('account memory lists memories by idea and forgets one', async () => {
  const forget = jest.fn(() => ({ data: { forgetMemory: { __typename: 'Memory', id: 'mem_1' } } }));
  const list = [memory('mem_1', 'Insurers first.'), memory('mem_g', 'Prefers short answers.', null)];
  render(
    <MockedProvider
      mocks={[
        { request: { query: GET_MEMORIES }, result: { data: { memories: list } } },
        { request: { query: FORGET_MEMORY, variables: { memoryId: 'mem_1' } }, result: forget },
        { request: { query: GET_MEMORIES }, result: { data: { memories: [list[1]] } } },
      ]}
    >
      <MemorySection />
    </MockedProvider>,
  );
  expect(await screen.findByText('Insurers first.')).toBeTruthy();
  expect(screen.getByText('TideLine')).toBeTruthy();
  expect(screen.getByText('About you')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Forget: Insurers first.' }));
  await waitFor(() => expect(forget).toHaveBeenCalled());
  await waitFor(() => expect(screen.queryByText('Insurers first.')).toBeNull());
});
