import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { usePipecatVoiceSession } from '../usePipecatVoiceSession';

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => mockNavigate,
}));

const mockRefetch = jest.fn();
jest.mock('@apollo/client/react', () => ({
  ...jest.requireActual('@apollo/client/react'),
  useApolloClient: () => ({ refetchQueries: mockRefetch }),
}));

type Callbacks = Record<string, (...args: unknown[]) => void>;
const mockClients: Array<{
  callbacks: Callbacks;
  connect: jest.Mock;
  disconnect: jest.Mock;
  enableMic: jest.Mock;
  sendText: jest.Mock;
  sendClientMessage: jest.Mock;
}> = [];

jest.mock('@pipecat-ai/client-js', () => ({
  // A plain function (not jest.fn) so resetMocks between tests can't clear it.
  PipecatClient: function MockPipecatClient(options: { callbacks: Callbacks }) {
    const client = {
      callbacks: options.callbacks,
      connect: jest.fn(async () => {
        options.callbacks.onBotReady?.({});
        return {};
      }),
      disconnect: jest.fn(async () => undefined),
      enableMic: jest.fn(),
      sendText: jest.fn(async () => 'msg-1'),
      sendClientMessage: jest.fn(),
    };
    mockClients.push(client);
    return client;
  },
}));
jest.mock('@pipecat-ai/websocket-transport', () => ({
  WebSocketTransport: function MockTransport() {
    return {};
  },
  ProtobufFrameSerializer: function MockSerializer() {
    return {};
  },
}));

const wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <MemoryRouter initialEntries={['/ideas/idea-1/description']}>{children}</MemoryRouter>
);

beforeEach(() => {
  mockClients.length = 0;
  mockNavigate.mockClear();
  mockRefetch.mockReset();
  mockRefetch.mockResolvedValue([]);
  jest.useRealTimers();
});

async function connected() {
  const hook = renderHook(() => usePipecatVoiceSession(), { wrapper });
  await act(async () => {
    await hook.result.current.start();
  });
  const client = mockClients[0];
  return { hook, client };
}

test('connects to the live endpoint with the current idea and becomes ready', async () => {
  const { hook, client } = await connected();
  expect(client.connect).toHaveBeenCalledWith({
    wsUrl: expect.stringMatching(/\/api\/voice-agent\/live\?path=%2Fideas%2Fidea-1%2Fdescription&idea_id=idea-1$/),
  });
  expect(hook.result.current.state.phase).toBe('listening');
  expect(hook.result.current.context.ideaId).toBe('idea-1');
});

test('server messages navigate, refresh data and record activity', async () => {
  jest.useFakeTimers();
  const { hook, client } = await connected();
  act(() => {
    client.callbacks.onServerMessage({ type: 'manifest.navigate', path: '/ideas/x/pitch-deck' });
    client.callbacks.onServerMessage({ type: 'manifest.tool', phase: 'started', id: 'c1', label: 'Create idea' });
    client.callbacks.onServerMessage({ type: 'manifest.changed', tool: 'create_idea' });
    client.callbacks.onServerMessage({ type: 'manifest.changed', tool: 'update_idea' });
  });
  expect(mockNavigate).toHaveBeenCalledWith('/ideas/x/pitch-deck');
  expect(hook.result.current.state.activity).toEqual([
    expect.objectContaining({ id: 'c1', status: 'running' }),
  ]);
  act(() => {
    jest.advanceTimersByTime(700);
  });
  expect(mockRefetch).toHaveBeenCalledTimes(1);
  expect(mockRefetch).toHaveBeenCalledWith({ include: 'active' });
});

test('transcripts, speaking state, mute and typed text', async () => {
  const { hook, client } = await connected();
  act(() => {
    client.callbacks.onUserInput({ text: 'make a deck', final: true });
    client.callbacks.onBotStartedSpeaking();
    client.callbacks.onBotOutput({ text: 'On it.', output_type: 'sentence' });
  });
  expect(hook.result.current.state.phase).toBe('speaking');
  expect(hook.result.current.state.captions.map(c => c.text)).toEqual(['make a deck', 'On it.']);

  act(() => hook.result.current.toggleMute());
  expect(client.enableMic).toHaveBeenCalledWith(false);
  expect(hook.result.current.state.muted).toBe(true);

  await act(async () => {
    await hook.result.current.sendText('  what is in my inbox  ');
  });
  expect(client.sendText).toHaveBeenCalledWith('what is in my inbox', { run_immediately: true, audio_response: true });
});

test('manifest.end disconnects once the goodbye finishes', async () => {
  const { hook, client } = await connected();
  act(() => {
    client.callbacks.onBotStartedSpeaking();
    client.callbacks.onServerMessage({ type: 'manifest.end' });
  });
  expect(client.disconnect).not.toHaveBeenCalled();
  await act(async () => {
    client.callbacks.onBotStoppedSpeaking();
  });
  await waitFor(() => expect(client.disconnect).toHaveBeenCalled());
  expect(hook.result.current.state.phase).toBe('ended');
});

test('a closed socket with an app code becomes a clear error', async () => {
  const { hook, client } = await connected();
  act(() => {
    client.callbacks.onError({ data: { message: 'websocket connection closed. Code: 4402' } });
  });
  expect(hook.result.current.state.error?.kind).toBe('no_api_key');
});
