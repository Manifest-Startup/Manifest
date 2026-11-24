import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import LiveVoicePanel from '../LiveVoicePanel';
import { INITIAL_LIVE_VOICE_STATE, LiveVoiceState } from '../liveVoice';

function renderPanel(state: Partial<LiveVoiceState>, extra: Record<string, unknown> = {}) {
  const session = {
    state: { ...INITIAL_LIVE_VOICE_STATE, ...state },
    levelsRef: { current: { mic: 0, bot: 0 } },
    context: { path: '/ideas' },
    start: jest.fn(),
    end: jest.fn(),
    toggleMute: jest.fn(),
    sendText: jest.fn(),
    ...extra,
  };
  render(
    <MemoryRouter>
      <LiveVoicePanel session={session as never} />
    </MemoryRouter>,
  );
}

test('before talking: one question, short suggestions and a Talk button', () => {
  renderPanel({});
  expect(screen.getByText('How can I help?')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'New idea' })).toBeInTheDocument();
  expect(screen.getByTestId('live-voice-start')).toHaveTextContent('Talk');
});

test('in conversation: only the latest reply and the latest action, with a confirm prompt', () => {
  renderPanel({
    phase: 'listening',
    captions: [
      { id: 1, role: 'assistant', text: 'Earlier line', final: true },
      { id: 2, role: 'user', text: 'Delete it', final: true },
      { id: 3, role: 'assistant', text: 'That deletes it for good. Should I?', final: true },
    ],
    activity: [{ id: 'a', label: 'Deleting the idea', status: 'confirm' }],
  });
  expect(screen.getByTestId('live-voice-reply')).toHaveTextContent('That deletes it for good. Should I?');
  expect(screen.queryByText('Earlier line')).not.toBeInTheDocument();
  expect(screen.getByText('Say “yes” to confirm')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'New idea' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'End' })).toBeInTheDocument();
});

test('tone reading is an explicit switch that says what it does and that no audio leaves', () => {
  const toggle = jest.fn();
  renderPanel({ phase: 'listening' }, { toneReading: { on: false, toggle } });
  const button = screen.getByRole('button', { name: 'Read my tone of voice' });
  expect(button).toHaveAttribute('aria-pressed', 'false');
  expect(button.getAttribute('title')).toContain('No audio leaves this device');
  button.click();
  expect(toggle).toHaveBeenCalled();
});

test('no tone switch where the session cannot read tone', () => {
  renderPanel({ phase: 'listening' });
  expect(screen.queryByRole('button', { name: /tone of voice/ })).not.toBeInTheDocument();
});
