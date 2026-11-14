import React, { useState } from 'react';
import { MockedProvider } from '@apollo/client/testing/react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import { accountVar, sidebarVar, userVar } from '../../core/apollo/localState';
import {
  GENERATE_PITCH_DECK,
  GET_IDEA,
  GET_IDEAS,
  TOGGLE_PUBLISH_IDEA,
} from '../../core/apollo/queries';
import {
  VOICE_COLLABORATION_EVENT,
  VOICE_SEARCH_EVENT,
  VOICE_WORKSPACE_LAYOUT_EVENT,
} from '../voiceCommandEvents';
import { useVoiceAppCommands } from '../useVoiceAppCommands';
import { safeNavigate } from 'utils/safeNavigate';
import * as voiceAgentApi from '../voiceAgentApi';

jest.mock('../voiceAgentApi', () => {
  const actual = jest.requireActual('../voiceAgentApi');
  return { ...actual, postVoiceAgentJson: jest.fn() };
});

jest.mock('../../notifications/context/MessageContext', () => ({
  useMessage: () => ({
    setMessage: jest.fn(),
  }),
}));

jest.mock('utils/safeNavigate', () => ({
  safeNavigate: jest.fn((navigate: (path: string) => void, _setMessage: unknown, path: string) => navigate(path)),
}));

const VoiceCommandHarness: React.FC<{ command: string; ideaHtml?: string | null }> = ({
  command,
  ideaHtml,
}) => {
  const { executeCommand } = useVoiceAppCommands();
  const location = useLocation();
  const [response, setResponse] = useState('');

  return (
    <div>
      <button
        type="button"
        onClick={async () => {
          const result = await executeCommand(command, { ideaDescriptionHtml: ideaHtml ?? undefined });
          setResponse(result?.response || '');
        }}
      >
        Run command
      </button>
      <div data-testid="voice-command-response">{response}</div>
      <div data-testid="voice-command-pathname">{location.pathname}</div>
    </div>
  );
};

const renderHarness = (
  command: string,
  mocks: any[] = [],
  initialEntry = '/ideas/idea-1/description',
  ideaHtml?: string | null,
) =>
  render(
    <MockedProvider addTypename={false} mocks={mocks}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="*" element={<VoiceCommandHarness command={command} ideaHtml={ideaHtml} />} />
        </Routes>
      </MemoryRouter>
    </MockedProvider>,
  );

describe('useVoiceAppCommands', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    sidebarVar({ currentIdeaId: 'idea-1', currentIdeaAspect: 'description', allIdeaIds: ['idea-1'] });
    userVar({ isLoggedIn: true, userData: { userId: 'user-1', email: 'hello@manifeststartup.com' } });
    accountVar({ accountData: null, loading: false, error: null });
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test('opens account navigation commands directly', async () => {
    renderHarness('Open account');

    fireEvent.click(screen.getByRole('button', { name: /run command/i }));

    await waitFor(() => {
      expect(screen.getByTestId('voice-command-response')).toHaveTextContent(
        'Opening account.',
      );
    });

    expect(safeNavigate).toHaveBeenCalledWith(expect.any(Function), expect.any(Function), '/account');
  });

  test('dispatches search commands into the universal search event bus', async () => {
    const listener = jest.fn();
    window.addEventListener(VOICE_SEARCH_EVENT, listener as EventListener);

    renderHarness('Search for climate fintech');
    fireEvent.click(screen.getByRole('button', { name: /run command/i }));

    await waitFor(() => {
      expect(screen.getByTestId('voice-command-response')).toHaveTextContent('Searching Manifest for climate fintech.');
    });

    expect(listener).toHaveBeenCalledTimes(1);
    const event = listener.mock.calls[0][0] as CustomEvent<{ query: string }>;
    expect(event.detail).toEqual({ query: 'climate fintech' });

    window.removeEventListener(VOICE_SEARCH_EVENT, listener as EventListener);
  });

  test('dispatches workspace layout commands after opening the current idea workspace', async () => {
    jest.useFakeTimers();
    const listener = jest.fn();
    window.addEventListener(VOICE_WORKSPACE_LAYOUT_EVENT, listener as EventListener);

    renderHarness('Turn on focus mode');
    fireEvent.click(screen.getByRole('button', { name: /run command/i }));

    await waitFor(() => {
      expect(screen.getByTestId('voice-command-response')).toHaveTextContent('Turning on focus mode.');
    });

    expect(screen.getByTestId('voice-command-pathname')).toHaveTextContent('/ideas/idea-1/description');

    jest.advanceTimersByTime(100);

    expect(listener).toHaveBeenCalledTimes(1);
    const event = listener.mock.calls[0][0] as CustomEvent<{ action: string }>;
    expect(event.detail).toEqual({ action: 'enable_focus_mode' });

    window.removeEventListener(VOICE_WORKSPACE_LAYOUT_EVENT, listener as EventListener);
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  test('opens collaboration controls through the shared event bus', async () => {
    jest.useFakeTimers();
    const listener = jest.fn();
    window.addEventListener(VOICE_COLLABORATION_EVENT, listener as EventListener);

    renderHarness('Open share');
    fireEvent.click(screen.getByRole('button', { name: /run command/i }));

    await waitFor(() => {
      expect(screen.getByTestId('voice-command-response')).toHaveTextContent('Opening sharing.');
    });

    jest.advanceTimersByTime(100);

    expect(listener).toHaveBeenCalledTimes(1);
    const event = listener.mock.calls[0][0] as CustomEvent<{ ideaId: string; target: string }>;
    expect(event.detail).toEqual({ ideaId: 'idea-1', target: 'share' });

    window.removeEventListener(VOICE_COLLABORATION_EVENT, listener as EventListener);
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  test('opens account integrations', async () => {
    renderHarness('Open integrations');
    fireEvent.click(screen.getByRole('button', { name: /run command/i }));
    await waitFor(() => {
      expect(screen.getByTestId('voice-command-response')).toHaveTextContent('Opening account integrations.');
    });
    expect(safeNavigate).toHaveBeenCalledWith(expect.any(Function), expect.any(Function), '/account');
  });

  test('generates pitch deck when the idea note has content', async () => {
    renderHarness(
      'Generate pitch deck',
      [
        {
          maxUsageCount: 10,
          request: {
            query: GENERATE_PITCH_DECK,
            variables: { ideaId: 'idea-1', description: 'Hello world' },
          },
          result: { data: { generatePitchDeck: { pitchDeck: '# Deck' } } },
        },
        {
          maxUsageCount: 10,
          request: { query: GET_IDEA, variables: { ideaId: 'idea-1' } },
          result: {
            data: {
              idea: {
                ideaId: 'idea-1',
                title: 'T',
                description: '<p>x</p>',
                pitchDeck: null,
                productRequirementsDocument: null,
                provisionalPatent: null,
                businessModelCanvas: null,
                similarIdeas: null,
                isPublished: false,
                requiredSkills: [],
              },
            },
          },
        },
        {
          maxUsageCount: 10,
          request: { query: GET_IDEAS },
          result: { data: { ideas: [] } },
        },
      ],
      '/ideas/idea-1/description',
      '<p>Hello world</p>',
    );

    fireEvent.click(screen.getByRole('button', { name: /run command/i }));

    await waitFor(() => {
      expect(screen.getByTestId('voice-command-response')).toHaveTextContent(
        'Started generating your pitch deck',
      );
    });
    expect(safeNavigate).toHaveBeenCalledWith(
      expect.any(Function),
      expect.any(Function),
      '/ideas/idea-1/pitch-deck',
    );
  });

  test('bootstraps a GitHub repo when the API succeeds', async () => {
    (voiceAgentApi.postVoiceAgentJson as jest.Mock).mockResolvedValue({
      html_url: 'https://github.com/acme/idea-repo',
    });

    renderHarness('Bootstrap GitHub repo idea-repo confirm bootstrap');
    fireEvent.click(screen.getByRole('button', { name: /run command/i }));

    await waitFor(() => {
      expect(screen.getByTestId('voice-command-response')).toHaveTextContent(
        'https://github.com/acme/idea-repo',
      );
    });

    expect(voiceAgentApi.postVoiceAgentJson).toHaveBeenCalledWith('/api/integrations/github/bootstrap', {
      idea_id: 'idea-1',
      repo_name: 'idea-repo',
    });
  });

  test('publishes the current idea through the shared mutation surface', async () => {
    renderHarness('Publish this idea', [
      {
        request: {
          query: TOGGLE_PUBLISH_IDEA,
          variables: { ideaId: 'idea-1' },
        },
        result: {
          data: {
            togglePublishIdea: {
              ideaId: 'idea-1',
              isPublished: true,
            },
          },
        },
      },
      {
        request: {
          query: GET_IDEAS,
        },
        result: {
          data: {
            ideas: [
              {
                ideaId: 'idea-1',
                title: 'Existing Idea',
                description: null,
                pitchDeck: null,
                productRequirementsDocument: null,
                provisionalPatent: null,
                businessModelCanvas: null,
                similarIdeas: null,
                isPublished: true,
              },
            ],
          },
        },
      },
    ]);

    fireEvent.click(screen.getByRole('button', { name: /run command/i }));

    await waitFor(() => {
      expect(screen.getByTestId('voice-command-response')).toHaveTextContent(
        'Published the current idea to discovery.',
      );
    });
  });
});
