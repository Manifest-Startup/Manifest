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
import { ariaShortcut, hasMod, shortcutLabel } from 'features/ideas/utils/noteFocus';
import './noteDictationOrb.css';

const log = createLogger('NoteDictationOrb');

type Phase = 'idle' | 'connecting' | 'listening' | 'error';

interface Problem {
  message: string;
  link?: { to: string; label: string };
}

/**
 * The note's voice orb: tap, talk, and the words appear in the note at the cursor as
 * they are spoken (Pipecat dictation mode). Tap again or press Esc to stop; ⌥⌘D toggles it.
 * The blue orb beside it opens the Manifest voice agent instead (⌥⌘V).
 */
const NoteDictationOrb: React.FC<{ ideaId: string }> = ({ ideaId }) => {
  const [phase, setPhase] = useState<Phase>('idle');
  const [problem, setProblem] = useState<Problem | null>(null);
  const [hasNote, setHasNote] = useState(false);
  const clientRef = useRef<PipecatClient | null>(null);
  const browserRef = useRef<ReturnType<typeof startRecognition>>(null);
  const writerRef = useRef<DictationWriter | null>(null);
  const heardRef = useRef('');
  const dockRef = useRef<HTMLDivElement>(null);

  useEffect(() => onDictationTargetChange(setHasNote), []);

  const stop = useCallback(async () => {
    const client = clientRef.current;
    clientRef.current = null;
    browserRef.current?.stop();
    browserRef.current = null;
    writerRef.current?.end();
    writerRef.current = null;
    heardRef.current = '';
    dockRef.current?.style.setProperty('--level', '0');
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
            dockRef.current?.style.setProperty('--level', Math.min(1, level * 3).toFixed(2));
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

  // Esc stops; ⌥⌘D (Ctrl+Alt+D) starts or stops dictation from anywhere on the note.
  useEffect(() => {
    if (!hasNote && !active) return;
    const onKey = (event: KeyboardEvent) => {
      if (active && event.key === 'Escape') {
        event.preventDefault();
        void stop();
        return;
      }
      if (hasMod(event) && event.altKey && !event.shiftKey && event.code === 'KeyD') {
        event.preventDefault();
        void (active ? stop() : start());
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [active, hasNote, start, stop]);

  // A different note, or leaving it: stop writing into it.
  useEffect(() => () => void stop(), [ideaId, stop]);

  if (!hasNote && !active) return null;

  const dictateKeys = shortcutLabel('D');
  const label =
    phase === 'listening' ? 'Stop dictation' : phase === 'connecting' ? 'Connecting…' : 'Dictate into the note';

  return (
    <div className="manifest-dictation" data-phase={phase}>
      {phase === 'error' && problem ? (
        <span className="manifest-dictation__problem" role="alert">
          {problem.message}
          {problem.link ? (
            <>
              {' '}
              <Link to={problem.link.to}>{problem.link.label}</Link>
            </>
          ) : null}
        </span>
      ) : null}
      <div ref={dockRef} aria-label="Voice" className="manifest-dictation__dock" role="group">
        {phase === 'listening' ? (
          <span className="manifest-dictation__status" role="status">
            <span aria-hidden="true" className="manifest-dictation__live" />
            Listening
            <kbd aria-hidden="true">esc</kbd>
          </span>
        ) : null}
        <button
          aria-keyshortcuts={ariaShortcut('D')}
          aria-label={label}
          aria-pressed={active}
          className="manifest-dictation__orb"
          data-testid="note-dictation-orb"
          onClick={() => void (active ? stop() : start())}
          onFocus={warmLiveVoice}
          onMouseDown={event => event.preventDefault()} // keep the note's cursor where it is
          onPointerEnter={warmLiveVoice}
          title={phase === 'listening' ? 'Stop dictation (Esc)' : `Dictate into the note (${dictateKeys})`}
          type="button"
        >
          {phase === 'listening' ? (
            <svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16">
              <rect x="6" y="6" width="12" height="12" rx="3" fill="currentColor" />
            </svg>
          ) : (
            <svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20">
              <rect x="9" y="2.5" width="6" height="12" rx="3" fill="currentColor" />
              <path
                d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"
                fill="none"
                stroke="currentColor"
                strokeLinecap="round"
                strokeWidth="1.8"
              />
            </svg>
          )}
        </button>
        {!active ? (
          <>
            <span aria-hidden="true" className="manifest-dictation__divider" />
            <button
              aria-keyshortcuts={ariaShortcut('V')}
              aria-label="Talk to Manifest"
              className="manifest-dictation__agent"
              data-testid="note-voice-agent"
              onClick={() => voiceOpenRequestVar(voiceOpenRequestVar() + 1)}
              onFocus={warmLiveVoice}
              onPointerEnter={warmLiveVoice}
              title={`Talk to Manifest (${shortcutLabel('V')})`}
              type="button"
            >
              <span aria-hidden="true" className="manifest-voice-launcher__orb" />
            </button>
          </>
        ) : null}
      </div>
    </div>
  );
};

export default NoteDictationOrb;
