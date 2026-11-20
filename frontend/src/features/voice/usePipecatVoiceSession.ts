import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import { useApolloClient } from '@apollo/client/react';
import { useLocation, useNavigate } from 'react-router-dom';
import type { PipecatClient } from '@pipecat-ai/client-js';

import { createLogger } from '../core/logError';
import {
  buildLiveVoiceUrl,
  classifyConnectionError,
  INITIAL_LIVE_VOICE_STATE,
  interpretServerMessage,
  liveVoiceReducer,
  loadPipecat,
  LiveVoiceContext,
  LiveVoiceState,
} from './liveVoice';

const log = createLogger('usePipecatVoiceSession');

/** Mic and bot loudness (0–1), updated many times a second; read in rAF, not React state. */
export interface LiveVoiceLevels {
  mic: number;
  bot: number;
}

export interface PipecatVoiceSessionApi {
  state: LiveVoiceState;
  levelsRef: React.MutableRefObject<LiveVoiceLevels>;
  context: LiveVoiceContext;
  start: () => Promise<void>;
  end: () => Promise<void>;
  toggleMute: () => void;
  sendText: (text: string) => Promise<void>;
}

const REFRESH_DEBOUNCE_MS = 600;

function contextFromPath(pathname: string): LiveVoiceContext {
  const ideaId = pathname.match(/^\/ideas\/([A-Za-z0-9_-]+)(?:\/|$)/)?.[1];
  return { path: pathname, ideaId: ideaId && ideaId !== 'qualify' ? ideaId : null };
}

/**
 * Live voice backed by Manifest's Pipecat agent (STT → LLM with every Manifest tool →
 * TTS) over one WebSocket. The agent can drive the app: it navigates, and when it changes
 * data the active Apollo queries refetch so the screen stays in sync.
 */
export function usePipecatVoiceSession(): PipecatVoiceSessionApi {
  const location = useLocation();
  const navigate = useNavigate();
  const apollo = useApolloClient();
  const [state, dispatch] = useReducer(liveVoiceReducer, INITIAL_LIVE_VOICE_STATE);

  const clientRef = useRef<PipecatClient | null>(null);
  const levelsRef = useRef<LiveVoiceLevels>({ mic: 0, bot: 0 });
  const refreshTimerRef = useRef<number | null>(null);
  const endAfterSpeechRef = useRef(false);
  const botSpeakingRef = useRef(false);
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;

  const context = useMemo(() => contextFromPath(location.pathname), [location.pathname]);
  const contextRef = useRef(context);
  contextRef.current = context;

  const scheduleRefresh = useCallback(() => {
    if (refreshTimerRef.current !== null) window.clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = window.setTimeout(() => {
      refreshTimerRef.current = null;
      // A vault (local folder) gets the agent's account changes through cloud sync.
      window.dispatchEvent(new Event('manifest:vault-sync-now'));
      void apollo.refetchQueries({ include: 'active' }).catch(error => log.warn('refetch failed', error));
    }, REFRESH_DEBOUNCE_MS);
  }, [apollo]);

  const disconnect = useCallback(async () => {
    const client = clientRef.current;
    clientRef.current = null;
    endAfterSpeechRef.current = false;
    levelsRef.current = { mic: 0, bot: 0 };
    if (client) {
      try {
        await client.disconnect();
      } catch (error) {
        log.warn('disconnect failed', error);
      }
    }
  }, []);

  const end = useCallback(async () => {
    await disconnect();
    dispatch({ type: 'disconnected' });
  }, [disconnect]);

  const start = useCallback(async () => {
    if (clientRef.current) return;
    dispatch({ type: 'connecting' });
    try {
      // Loaded on first use (or warmed on hover) so it never weighs on the app's boot chunks.
      const [{ PipecatClient }, { WebSocketTransport, ProtobufFrameSerializer }] = await loadPipecat();
      const client = new PipecatClient({
        transport: new WebSocketTransport({
          serializer: new ProtobufFrameSerializer(),
          recorderSampleRate: 16000,
          playerSampleRate: 24000,
        }),
        enableMic: true,
        enableCam: false,
        callbacks: {
          onBotReady: () => dispatch({ type: 'ready' }),
          onDisconnected: () => {
            if (clientRef.current === client) clientRef.current = null;
            levelsRef.current = { mic: 0, bot: 0 };
            dispatch({ type: 'disconnected' });
          },
          onError: message => {
            const text = (message?.data as { message?: string } | undefined)?.message;
            log.warn('voice error', text);
            dispatch({ type: 'error', error: classifyConnectionError(text) });
          },
          onDeviceError: () =>
            dispatch({
              type: 'error',
              error: { kind: 'microphone', message: 'Allow microphone access to talk, or type instead.' },
            }),
          onUserStartedSpeaking: () => dispatch({ type: 'userStarted' }),
          onUserStoppedSpeaking: () => dispatch({ type: 'userStopped' }),
          onBotStartedSpeaking: () => {
            botSpeakingRef.current = true;
            dispatch({ type: 'botStarted' });
          },
          onBotStoppedSpeaking: () => {
            botSpeakingRef.current = false;
            dispatch({ type: 'botStopped' });
            if (endAfterSpeechRef.current) void end();
          },
          onUserInput: data => dispatch({ type: 'userInput', text: data.text, final: data.final }),
          onBotOutput: data =>
            dispatch({ type: 'botOutput', text: data.text, outputType: data.output_type ?? undefined }),
          onLocalAudioLevel: level => {
            levelsRef.current.mic = level;
          },
          onRemoteAudioLevel: level => {
            levelsRef.current.bot = level;
          },
          onServerMessage: data => {
            const action = interpretServerMessage(data);
            if (!action) return;
            if (action.kind === 'navigate') navigateRef.current(action.path);
            else if (action.kind === 'refresh') scheduleRefresh();
            else if (action.kind === 'activity') dispatch({ type: 'tool', activity: action.activity });
            else if (action.kind === 'end') {
              endAfterSpeechRef.current = true;
              if (!botSpeakingRef.current) window.setTimeout(() => void end(), 1500);
            }
          },
        },
      });
      clientRef.current = client;
      await client.connect({ wsUrl: buildLiveVoiceUrl(window.location, contextRef.current) });
    } catch (error) {
      log.warn('connect failed', error);
      await disconnect();
      dispatch({
        type: 'error',
        error: classifyConnectionError(error instanceof Error ? `${error.name} ${error.message}` : String(error)),
      });
    }
  }, [disconnect, end, scheduleRefresh]);

  const toggleMute = useCallback(() => {
    const client = clientRef.current;
    const muted = !state.muted;
    if (client) client.enableMic(!muted);
    if (muted) levelsRef.current.mic = 0;
    dispatch({ type: 'muted', muted });
  }, [state.muted]);

  const sendText = useCallback(async (text: string) => {
    const trimmed = text.trim();
    const client = clientRef.current;
    if (!trimmed || !client) return;
    dispatch({ type: 'userInput', text: trimmed, final: true });
    try {
      await client.sendText(trimmed, { run_immediately: true, audio_response: true });
    } catch (error) {
      log.warn('sendText failed', error);
    }
  }, []);

  // Tell the agent what the person is looking at whenever the route changes.
  useEffect(() => {
    const client = clientRef.current;
    if (!client || state.phase === 'connecting' || state.phase === 'idle') return;
    try {
      client.sendClientMessage('manifest.context', {
        path: context.path,
        idea_id: context.ideaId ?? null,
        idea_title: context.ideaTitle ?? null,
      });
    } catch (error) {
      log.warn('context update failed', error);
    }
    // Only the route matters here; phase changes don't move the person.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [context.path]);

  useEffect(
    () => () => {
      if (refreshTimerRef.current !== null) window.clearTimeout(refreshTimerRef.current);
      void disconnect();
    },
    [disconnect],
  );

  return { state, levelsRef, context, start, end, toggleMute, sendText };
}
