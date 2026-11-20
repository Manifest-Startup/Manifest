import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import { useApolloClient } from '@apollo/client/react';
import { useLocation } from 'react-router-dom';

import { createLogger } from '../core/logError';
import { INITIAL_LIVE_VOICE_STATE, liveVoiceReducer } from './liveVoice';
import {
  BRIDGE_INSTALL_COMMAND,
  browserSpeechAvailable,
  createSpeaker,
  probeBridge,
  runBridgeTurn,
  startRecognition,
} from './localAgent';
import { contextFromPath, type LiveVoiceLevels, type PipecatVoiceSessionApi } from './usePipecatVoiceSession';

const log = createLogger('useLocalAgentVoiceSession');

/**
 * Voice with no OpenAI key: the browser hears and speaks, the person's own agent (Claude
 * Code, Codex, via `manifest bridge`) answers. Same shape as the Pipecat session, so the
 * same panel shows it. The mic pauses while the agent speaks, so it never hears itself.
 */
export function useLocalAgentVoiceSession(): PipecatVoiceSessionApi {
  const location = useLocation();
  const apollo = useApolloClient();
  const [state, dispatch] = useReducer(liveVoiceReducer, INITIAL_LIVE_VOICE_STATE);
  const levelsRef = useRef<LiveVoiceLevels>({ mic: 0, bot: 0 });
  const context = useMemo(() => contextFromPath(location.pathname), [location.pathname]);
  const contextRef = useRef(context);
  contextRef.current = context;

  const recognitionRef = useRef<ReturnType<typeof startRecognition>>(null);
  const speakerRef = useRef<ReturnType<typeof createSpeaker> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const mutedRef = useRef(false);
  const activeRef = useRef(false);

  // Claude Code only reports a turn as finished after the person's Stop hooks, which can
  // take many seconds; so the mic opens again once the answer has been spoken, and later
  // turns queue up behind it.
  const chainRef = useRef<Promise<void>>(Promise.resolve());
  const answeredRef = useRef(true);

  const listenAgain = useCallback(() => {
    if (!activeRef.current || !answeredRef.current || speakerRef.current?.speaking) return;
    levelsRef.current = { mic: mutedRef.current ? 0 : 0.15, bot: 0 };
    if (!mutedRef.current) recognitionRef.current?.resume();
  }, []);

  const turn = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || !activeRef.current) return;
      recognitionRef.current?.pause();
      answeredRef.current = false;
      dispatch({ type: 'userInput', text: trimmed, final: true });
      dispatch({ type: 'userStopped' });
      const previous = chainRef.current;
      let release: () => void = () => undefined;
      chainRef.current = new Promise<void>(resolve => (release = resolve));
      await previous;
      if (!activeRef.current) return release();
      const controller = new AbortController();
      abortRef.current = controller;
      let usedTools = false;
      let step = 0;
      let spoke = false;
      const nudge = window.setTimeout(() => {
        if (!spoke && activeRef.current) speakerRef.current?.say('Working on it.');
      }, 3000);
      try {
        await runBridgeTurn(
          trimmed,
          contextRef.current,
          event => {
            if (event.kind === 'say' || event.kind === 'error') {
              spoke = true;
              answeredRef.current = true; // the mic opens once this has been spoken
              dispatch({ type: 'botOutput', text: event.text });
              speakerRef.current?.say(event.kind === 'error' ? 'Something went wrong. Details are in the terminal.' : event.text);
            } else if (event.kind === 'tool') {
              usedTools = true;
              step += 1;
              dispatch({ type: 'tool', activity: { id: `local-${Date.now()}-${step}`, label: event.text, status: 'done' } });
            }
          },
          controller.signal,
        );
      } catch (error) {
        if (!controller.signal.aborted) {
          log.warn('bridge turn failed', error);
          dispatch({
            type: 'error',
            error: { kind: 'unavailable', message: `Lost the connection to your agent. Is the Manifest bridge still running (\`${BRIDGE_INSTALL_COMMAND}\`)?` },
          });
        }
      } finally {
        window.clearTimeout(nudge);
        abortRef.current = null;
        answeredRef.current = true;
        release();
      }
      if (usedTools) {
        window.dispatchEvent(new Event('manifest:vault-sync-now'));
        void apollo.refetchQueries({ include: 'active' }).catch(() => undefined);
      }
      listenAgain();
    },
    [apollo, listenAgain],
  );

  const end = useCallback(async () => {
    activeRef.current = false;
    abortRef.current?.abort();
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    speakerRef.current?.cancel();
    speakerRef.current = null;
    levelsRef.current = { mic: 0, bot: 0 };
    dispatch({ type: 'disconnected' });
  }, []);

  const start = useCallback(async () => {
    if (activeRef.current) return;
    dispatch({ type: 'connecting' });
    if (!browserSpeechAvailable()) {
      dispatch({
        type: 'error',
        error: { kind: 'unavailable', message: "This browser can't listen. Use Chrome, Edge or Safari, or type instead." },
      });
      return;
    }
    const bridge = await probeBridge();
    if (!bridge) {
      dispatch({
        type: 'error',
        error: { kind: 'unavailable', message: `Connect Claude Code on this Mac once: ${BRIDGE_INSTALL_COMMAND}` },
      });
      return;
    }
    activeRef.current = true;
    speakerRef.current = createSpeaker(speaking => {
      levelsRef.current.bot = speaking ? 0.5 : 0;
      dispatch({ type: speaking ? 'botStarted' : 'botStopped' });
      if (!speaking) listenAgain();
    });
    recognitionRef.current = startRecognition({
      onText: (text, final) => {
        if (speakerRef.current?.speaking) return;
        if (final) void turn(text);
        else {
          dispatch({ type: 'userStarted' });
          dispatch({ type: 'userInput', text, final: false });
        }
      },
      onError: message => dispatch({ type: 'error', error: { kind: 'microphone', message } }),
    });
    if (!recognitionRef.current) {
      activeRef.current = false;
      dispatch({ type: 'error', error: { kind: 'microphone', message: 'Allow microphone access to talk.' } });
      return;
    }
    recognitionRef.current.pause(); // hold the mic while the greeting plays
    dispatch({ type: 'ready' });
    speakerRef.current.say(`${bridge.agent} is listening.`);
  }, [listenAgain, turn]);

  const toggleMute = useCallback(() => {
    const muted = !mutedRef.current;
    mutedRef.current = muted;
    if (muted) {
      recognitionRef.current?.pause();
      levelsRef.current.mic = 0;
    } else listenAgain();
    dispatch({ type: 'muted', muted });
  }, [listenAgain]);

  const sendText = useCallback((text: string) => turn(text), [turn]);

  useEffect(() => () => void end(), [end]);

  return { state, levelsRef, context, start, end, toggleMute, sendText };
}
