import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import type { PipecatClient } from '@pipecat-ai/client-js';

import { voiceOpenRequestVar } from '../core/apollo/localState';
import { createLogger } from '../core/logError';
import {
  onDictationTargetChange,
  startDictation,
  type DictationWriter,
} from 'features/ideas/utils/noteDictation';
import { buildLiveVoiceUrl, classifyConnectionError, liveVoiceStatus, loadPipecat, warmLiveVoice } from './liveVoice';
import { startRecognition } from './localAgent';
import './noteDictationOrb.css';

const log = createLogger('NoteDictationOrb');

type Phase = 'idle' | 'connecting' | 'listening' | 'error';

interface Problem {
  message: string;
  link?: { to: string; label: string };
}

/**
 * The note's voice orb: tap, talk, and the words appear in the note at the cursor as
 * they are spoken (Pipecat dictation mode). Tap again or press Esc to stop. The small
 * button beside it opens the Manifest voice agent instead.
 */
const NoteDictationOrb: React.FC<{ ideaId: string }> = ({ ideaId }) => {
  const [phase, setPhase] = useState<Phase>('idle');
  const [problem, setProblem] = useState<Problem | null>(null);
  const [hasNote, setHasNote] = useState(false);
  const clientRef = useRef<PipecatClient | null>(null);
  const browserRef = useRef<ReturnType<typeof startRecognition>>(null);
  const writerRef = useRef<DictationWriter | null>(null);
  const heardRef = useRef('');
  const orbRef = useRef<HTMLButtonElement>(null);

  useEffect(() => onDictationTargetChange(setHasNote), []);

  const stop = useCallback(async () => {
    const client = clientRef.current;
    clientRef.current = null;
    browserRef.current?.stop();
    browserRef.current = null;
    writerRef.current?.end();
    writerRef.current = null;
    heardRef.current = '';
    orbRef.current?.style.setProperty('--level', '0');
    setPhase(current => (current === 'error' ? current : 'idle'));
    if (client) {
      try {
        await client.disconnect();
      } catch (error) {
        log.warn('disconnect failed', error);
      }
    }
  }, []);

  const fail = useCallback(
    (next: Problem) => {
      void stop();
      setProblem(next);
      setPhase('error');
    },
    [stop],
  );

  const start = useCallback(async () => {
    if (clientRef.current || browserRef.current) return;
    setProblem(null);
    // The note may still be opening; give it a moment before giving up.
    let writer = startDictation();
    for (let tries = 0; !writer && tries < 6; tries++) {
      await new Promise(resolve => window.setTimeout(resolve, 250));
      writer = startDictation();
    }
    if (!writer) {
      fail({ message: "This note can't be edited right now." });
      return;
    }
    writerRef.current = writer;
    setPhase('connecting');
    const status = await liveVoiceStatus();
    if (!status.available) {
      // No key or no account: the browser's own speech recognition writes instead.
      const browser = startRecognition({
        onText: (text, final) => {
          const current = writerRef.current;
          if (!current) return;
          if (final) current.commit(text);
          else current.interim(text);
        },
        onError: message => fail({ message }),
      });
      if (browser) {
        browserRef.current = browser;
        setPhase('listening');
        return;
      }
      fail(
        status.reason === 'no_api_key'
          ? { message: 'Dictation runs on your own OpenAI key.', link: { to: '/account#ai-key', label: 'Add key' } }
          : status.reason === 'sign_in'
            ? { message: 'Dictation runs through your Manifest account.', link: { to: '/login', label: 'Sign in' } }
            : { message: status.message || 'Voice is not available right now.' },
      );
      return;
    }
    try {
      const [{ PipecatClient }, { WebSocketTransport, ProtobufFrameSerializer }] = await loadPipecat();
      if (writerRef.current !== writer) return; // stopped while loading
      const client = new PipecatClient({
        transport: new WebSocketTransport({
          serializer: new ProtobufFrameSerializer(),
          recorderSampleRate: 16000,
          playerSampleRate: 24000,
        }),
        enableMic: true,
        enableCam: false,
        callbacks: {
          onBotReady: () => setPhase('listening'),
          onDisconnected: () => {
            if (clientRef.current === client) void stop();
          },
          onError: message => {
            const text = (message?.data as { message?: string } | undefined)?.message;
            fail({ message: classifyConnectionError(text).message });
          },
          onDeviceError: () => fail({ message: 'Allow microphone access to dictate.' }),
          // Interim pieces are new words to append; the final one is the whole sentence.
          onUserInput: data => {
            const current = writerRef.current;
            if (!current) return;
            if (data.final) {
              current.commit(data.text);
              heardRef.current = '';
            } else {
              heardRef.current += data.text;
              current.interim(heardRef.current);
            }
          },
          onLocalAudioLevel: level => {
            orbRef.current?.style.setProperty('--level', Math.min(1, level * 3).toFixed(2));
          },
        },
      });
      clientRef.current = client;
      await client.connect({
        wsUrl: buildLiveVoiceUrl(window.location, { path: `/ideas/${ideaId}`, ideaId }, 'dictate'),
      });
    } catch (error) {
      log.warn('connect failed', error);
      fail({
        message: classifyConnectionError(error instanceof Error ? `${error.name} ${error.message}` : String(error))
          .message,
      });
    }
  }, [fail, ideaId, stop]);

  const active = phase === 'connecting' || phase === 'listening';

  useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        void stop();
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [active, stop]);

  // A different note, or leaving it: stop writing into it.
  useEffect(() => () => void stop(), [ideaId, stop]);

  if (!hasNote && !active) return null;

  const label = phase === 'listening' ? 'Stop dictation' : phase === 'connecting' ? 'Connecting…' : 'Dictate into the note';

  return (
    <div className="manifest-dictation" data-phase={phase}>
      <button
        ref={orbRef}
        aria-label={label}
        aria-pressed={active}
        className="manifest-dictation__orb"
        data-testid="note-dictation-orb"
        onClick={() => void (active ? stop() : start())}
        onFocus={warmLiveVoice}
        onMouseDown={event => event.preventDefault()} // keep the note's cursor where it is
        onPointerEnter={warmLiveVoice}
        title={phase === 'listening' ? 'Listening — tap or Esc to stop' : 'Dictate into the note'}
        type="button"
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20">
          <rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor" />
          <path d="M6 11a6 6 0 0 0 12 0M12 17v4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
      {!active ? (
        <button
          aria-label="Talk to Manifest"
          className="manifest-dictation__agent"
          data-testid="note-voice-agent"
          onClick={() => voiceOpenRequestVar(voiceOpenRequestVar() + 1)}
          onFocus={warmLiveVoice}
          onPointerEnter={warmLiveVoice}
          title="Talk to Manifest"
          type="button"
        >
          <span aria-hidden="true" className="manifest-voice-launcher__orb" />
        </button>
      ) : null}
      {phase === 'listening' ? (
        <span className="manifest-dictation__hint" role="status">
          Listening
        </span>
      ) : null}
      {phase === 'error' && problem ? (
        <span className="manifest-dictation__hint manifest-dictation__hint--problem" role="alert">
          {problem.message}
          {problem.link ? (
            <>
              {' '}
              <Link to={problem.link.to}>{problem.link.label}</Link>
            </>
          ) : null}
        </span>
      ) : null}
    </div>
  );
};

export default NoteDictationOrb;
