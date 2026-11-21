import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import { useApolloClient } from '@apollo/client/react';
import { useLocation } from 'react-router-dom';

import { createLogger } from '../core/logError';
import { INITIAL_LIVE_VOICE_STATE, liveVoiceReducer } from './liveVoice';
import {
  browserSpeechAvailable,
  createBridgeSpeaker,
  createSpeaker,
  isBargeIn,
  isEcho,
  probeBridge,
  runBridgeTurn,
  startRecognition,
  VOICE_SETUP_COMMAND,
  voiceAudioContext,
  warmBridgeSpeech,
  type RecognitionHandle,
  type Speaker,
} from './localAgent';
import { contextFromPath, type LiveVoiceLevels, type PipecatVoiceSessionApi } from './usePipecatVoiceSession';

const log = createLogger('useLocalAgentVoiceSession');

/** Send the question this long after the last final words (the person may go on). */
export const FINAL_SETTLE_MS = 350;
/** …or after the words in progress stop changing this long (faster than waiting for final). */
export const INTERIM_SETTLE_MS = 700;
const NUDGE_AFTER_MS = 3000;
/** For this long after it stops talking, words that repeat what it said are its own echo. */
export const ECHO_TAIL_MS = 1500;

/** The mic with the browser's echo cancellation, so the voice playing here isn't heard. */
async function echoCancelledMic(): Promise<MediaStream | null> {
  try {
    return await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch {
    return null; // recognition opens the mic itself; the word filter still drops echo
  }
}

/**
 * Voice with no OpenAI key, built to feel instant: the browser hears (streaming recognition)
 * and speaks (its own voice starts in milliseconds), and the person's own agent (Claude
 * Code, Codex, via `manifest bridge`) answers sentence by sentence.
 *
 * - The question goes out as soon as the person pauses, not after the browser's slower
 *   "final" result.
 * - The mic stays open while it talks, so the person can talk over it: their words stop
 *   the voice and the agent's answer (the bridge interrupts it) and become the next
 *   question. Its own voice coming back through the speakers is told apart and ignored.
 * - Tapping the orb (or Space) also stops it mid-sentence.
 */
export function useLocalAgentVoiceSession(): PipecatVoiceSessionApi {
  const location = useLocation();
  const apollo = useApolloClient();
  const [state, dispatch] = useReducer(liveVoiceReducer, INITIAL_LIVE_VOICE_STATE);
  const levelsRef = useRef<LiveVoiceLevels>({ mic: 0, bot: 0 });
  const context = useMemo(() => contextFromPath(location.pathname), [location.pathname]);
  const contextRef = useRef(context);
  contextRef.current = context;

  const recognitionRef = useRef<RecognitionHandle | null>(null);
  const speakerRef = useRef<Speaker | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const mutedRef = useRef(false);
  const activeRef = useRef(false);
  const turnRef = useRef(0); // the current turn; answers of older ones are dropped
  const heardRef = useRef({ final: '', interim: '' });
  const settleRef = useRef<number | null>(null);
  const decayRef = useRef<number | null>(null);
  const naturalRef = useRef(false); // the bridge speaks in the natural voice
  const micRef = useRef<MediaStream | null>(null);
  const quietSinceRef = useRef(0); // when it last stopped talking
  const warmedRef = useRef(false); // woke the voice for this question already

  const clearSettle = () => {
    if (settleRef.current !== null) window.clearTimeout(settleRef.current);
    settleRef.current = null;
  };

  /** Stop talking and stop the agent's answer in progress. */
  const interrupt = useCallback(() => {
    turnRef.current += 1;
    abortRef.current?.abort(); // the bridge interrupts the agent when the turn hangs up
    abortRef.current = null;
    speakerRef.current?.cancel();
  }, []);

  const turn = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || !activeRef.current) return;
      interrupt(); // a new question replaces an answer still coming
      const id = turnRef.current;
      const controller = new AbortController();
      abortRef.current = controller;
      dispatch({ type: 'userInput', text: trimmed, final: true });
      dispatch({ type: 'userStopped' });
      let usedTools = false;
      let spoke = false;
      let step = 0;
      const current = () => id === turnRef.current && activeRef.current;
      const nudge = window.setTimeout(() => {
        if (!spoke && current()) speakerRef.current?.say('One moment.');
      }, NUDGE_AFTER_MS);
      try {
        await runBridgeTurn(
          trimmed,
          contextRef.current,
          event => {
            if (!current()) return;
            if (event.kind === 'say' || event.kind === 'error') {
              spoke = true;
              const said = event.kind === 'error' ? 'Something went wrong. The details are in the bridge log.' : event.text;
              dispatch({ type: 'botOutput', text: event.kind === 'error' ? event.text : said });
              speakerRef.current?.say(said);
            } else if (event.kind === 'tool') {
              usedTools = true;
              step += 1;
              dispatch({ type: 'tool', activity: { id: `local-${id}-${step}`, label: event.text, status: 'done' } });
            }
          },
          controller.signal,
        );
      } catch (error) {
        if (!controller.signal.aborted && current()) {
          log.warn('bridge turn failed', error);
          dispatch({
            type: 'error',
            error: {
              kind: 'unavailable',
              message: `Lost the connection to your agent on this Mac. Set it up again: ${VOICE_SETUP_COMMAND}`,
            },
          });
        }
      } finally {
        window.clearTimeout(nudge);
        if (abortRef.current === controller) abortRef.current = null;
      }
      if (current() && !speakerRef.current?.speaking) dispatch({ type: 'botStopped' });
      if (usedTools) {
        window.dispatchEvent(new Event('manifest:vault-sync-now'));
        void apollo.refetchQueries({ include: 'active' }).catch(() => undefined);
      }
    },
    [apollo, interrupt],
  );

  /** The person paused: send what they said (and let the browser forget its pending copy). */
  const commit = useCallback(() => {
    clearSettle();
    const { final, interim } = heardRef.current;
    heardRef.current = { final: '', interim: '' };
    const text = `${final} ${interim}`.trim();
    warmedRef.current = false;
    if (interim) recognitionRef.current?.restart(); // its "final" for these words would repeat them
    if (text) void turn(text);
  }, [turn]);

  const onHeard = useCallback(
    (text: string, final: boolean) => {
      if (!activeRef.current || mutedRef.current) return;
      const speaker = speakerRef.current;
      if (speaker?.speaking) {
        if (!isBargeIn(text, speaker.recent)) return; // its own voice through the speakers
        interrupt();
      } else if (speaker && Date.now() - quietSinceRef.current < ECHO_TAIL_MS && isEcho(text, speaker.recent)) {
        return; // the late tail of its own voice
      }
      if (naturalRef.current && !warmedRef.current) {
        warmedRef.current = true;
        warmBridgeSpeech(); // page the voice in while they're still talking
      }
      const heard = heardRef.current;
      if (final) heardRef.current = { final: `${heard.final} ${text}`.trim(), interim: '' };
      else heardRef.current = { ...heard, interim: text };
      levelsRef.current.mic = 0.7;
      dispatch({ type: 'userStarted' });
      dispatch({ type: 'userInput', text: `${heardRef.current.final} ${heardRef.current.interim}`.trim(), final: false });
      clearSettle();
      settleRef.current = window.setTimeout(commit, final ? FINAL_SETTLE_MS : INTERIM_SETTLE_MS);
    },
    [commit, interrupt],
  );

  const end = useCallback(async () => {
    activeRef.current = false;
    clearSettle();
    interrupt();
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    micRef.current?.getTracks().forEach(track => track.stop());
    micRef.current = null;
    speakerRef.current = null;
    if (decayRef.current !== null) window.clearInterval(decayRef.current);
    decayRef.current = null;
    levelsRef.current = { mic: 0, bot: 0 };
    dispatch({ type: 'disconnected' });
  }, [interrupt]);

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
        error: { kind: 'setup', message: `Connect Claude Code or Codex on this Mac once: ${VOICE_SETUP_COMMAND}` },
      });
      return;
    }
    activeRef.current = true;
    const onSpeaking = (speaking: boolean) => {
      if (!speaking) quietSinceRef.current = Date.now();
      levelsRef.current.bot = speaking ? 0.6 : 0;
      dispatch({ type: speaking ? 'botStarted' : 'botStopped' });
    };
    // The natural voice (Kokoro on this Mac's GPU) when the bridge has it; else the browser's.
    naturalRef.current = Boolean(bridge.speech) && voiceAudioContext() !== null;
    speakerRef.current = naturalRef.current
      ? createBridgeSpeaker(onSpeaking)
      : createSpeaker(onSpeaking, () => {
          levelsRef.current.bot = 0.95; // a pulse on each spoken word; decays below
        });
    decayRef.current = window.setInterval(() => {
      const levels = levelsRef.current;
      const speaker = speakerRef.current;
      const loud = speaker?.level?.();
      levels.bot = !speaker?.speaking ? 0 : loud !== undefined ? loud : Math.max(0.3, levels.bot * 0.85);
      levels.mic = mutedRef.current ? 0 : Math.max(0.12, levels.mic * 0.85);
    }, 50);
    micRef.current = await echoCancelledMic();
    recognitionRef.current = startRecognition(
      {
        onText: onHeard,
        onError: message => dispatch({ type: 'error', error: { kind: 'microphone', message } }),
      },
      micRef.current?.getAudioTracks()[0] ?? null,
    );
    if (!recognitionRef.current) {
      void end();
      dispatch({ type: 'error', error: { kind: 'microphone', message: 'Allow microphone access to talk.' } });
      return;
    }
    // No spoken greeting: it listens at once, like a phone call that's already connected.
    dispatch({ type: 'ready' });
  }, [end, onHeard]);

  const toggleMute = useCallback(() => {
    const muted = !mutedRef.current;
    mutedRef.current = muted;
    if (muted) {
      clearSettle();
      heardRef.current = { final: '', interim: '' };
      recognitionRef.current?.pause();
      levelsRef.current.mic = 0;
    } else recognitionRef.current?.resume();
    dispatch({ type: 'muted', muted });
  }, []);

  const sendText = useCallback((text: string) => turn(text), [turn]);

  useEffect(() => () => void end(), [end]);

  return { state, levelsRef, context, start, end, toggleMute, sendText, interrupt };
}
