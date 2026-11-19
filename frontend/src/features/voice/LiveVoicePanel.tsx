import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import type { LiveActivity, LiveVoiceError, LiveVoicePhase, LiveVoiceState } from './liveVoice';
import { suggestionsFor } from './liveVoice';
import type { PipecatVoiceSessionApi } from './usePipecatVoiceSession';
import './liveVoicePanel.css';

export type LiveVoicePanelLayout = 'docked' | 'page';

interface LiveVoicePanelProps {
  session: PipecatVoiceSessionApi;
  layout?: LiveVoicePanelLayout;
  /** Shown instead of the conversation when live voice can't start (e.g. no OpenAI key). */
  blocked?: LiveVoiceError | null;
  onClose?: () => void;
}

const PHASE_LABEL: Record<LiveVoicePhase, string> = {
  idle: 'Ready when you are',
  connecting: 'Connecting',
  listening: 'Listening',
  thinking: 'Thinking',
  speaking: 'Speaking',
  ended: 'See you soon',
  error: 'Needs attention',
};

const PHASE_HINT: Record<LiveVoicePhase, string> = {
  idle: 'Ask for anything you can do in Manifest.',
  connecting: 'Opening a private line…',
  listening: 'Go ahead, I’m all ears.',
  thinking: 'Working it out…',
  speaking: 'Interrupt me any time.',
  ended: 'Start again whenever you like.',
  error: '',
};

type Mood = LiveVoicePhase | 'muted';

function moodOf(state: LiveVoiceState): Mood {
  if (state.muted && (state.phase === 'listening' || state.phase === 'thinking')) return 'muted';
  return state.phase;
}

function headline(state: LiveVoiceState, blocked: boolean): { title: string; hint: string } {
  if (blocked) return { title: 'One step to talk', hint: 'Voice runs on your own OpenAI key.' };
  const mood = moodOf(state);
  if (mood === 'muted') return { title: 'Muted', hint: 'Unmute when you’re ready.' };
  const running = [...state.activity].reverse().find(item => item.status === 'running');
  if (running && (state.phase === 'thinking' || state.phase === 'listening')) {
    return { title: PHASE_LABEL.thinking, hint: `${running.label}…` };
  }
  const waiting = [...state.activity].reverse().find(item => item.status === 'confirm');
  if (waiting && state.phase === 'listening') {
    return { title: 'Your call', hint: `Say yes to ${waiting.label.toLowerCase()}, or no.` };
  }
  return { title: PHASE_LABEL[state.phase], hint: PHASE_HINT[state.phase] };
}

const isLivePhase = (phase: LiveVoicePhase) =>
  phase === 'listening' || phase === 'thinking' || phase === 'speaking';

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
}

/**
 * Feeds the live mic and Manifest levels into CSS (--lv-mic / --lv-bot on the panel), so the
 * orb, aurora and meter move with the conversation without re-rendering React.
 */
function useAudioLevels(
  panelRef: React.RefObject<HTMLElement | null>,
  session: PipecatVoiceSessionApi,
): void {
  const { phase, muted } = session.state;
  useEffect(() => {
    const node = panelRef.current;
    if (!node) return undefined;
    if (prefersReducedMotion() || !isLivePhase(phase)) {
      node.style.setProperty('--lv-mic', '0');
      node.style.setProperty('--lv-bot', '0');
      return undefined;
    }
    let frame = 0;
    let mic = 0;
    let bot = 0;
    const tick = () => {
      const levels = session.levelsRef.current;
      // Ease toward the live level so everything glides instead of jittering.
      mic += ((muted ? 0 : Math.min(1, levels.mic * 2.4)) - mic) * 0.22;
      bot += (Math.min(1, levels.bot * 2.4) - bot) * 0.18;
      node.style.setProperty('--lv-mic', mic.toFixed(3));
      node.style.setProperty('--lv-bot', bot.toFixed(3));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [panelRef, phase, muted, session.levelsRef]);
}

/** A fluid, iridescent orb: a slowly turning colour field under glass, tinted by mood. */
const VoiceOrb: React.FC<{ size: 'sm' | 'lg' }> = ({ size }) => (
  <div aria-hidden="true" className={`lv-orb lv-orb--${size}`}>
    <span className="lv-orb__glow" />
    <span className="lv-orb__ripple" />
    <span className="lv-orb__body">
      <span className="lv-orb__swirl" />
      <span className="lv-orb__swirl lv-orb__swirl--counter" />
      <span className="lv-orb__gloss" />
    </span>
  </div>
);

/** Four bars in the header that follow whoever is talking. */
const LevelMeter: React.FC = () => (
  <span aria-hidden="true" className="lv-meter">
    <i />
    <i />
    <i />
    <i />
  </span>
);

const ActivityIcon: React.FC<{ status: LiveActivity['status'] }> = ({ status }) => {
  if (status === 'running') return <span aria-hidden="true" className="lv-step__spinner" />;
  const path =
    status === 'done' ? 'M6.5 12.5l3.5 3.5 7.5-8' : status === 'failed' ? 'M8 8l8 8M16 8l-8 8' : 'M12 7.5v5.5m0 3v.01';
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <path d={path} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.4" />
    </svg>
  );
};

const STATUS_TEXT: Record<LiveActivity['status'], string> = {
  running: 'Working',
  done: 'Done',
  failed: "Didn't work",
  confirm: 'Waiting for your yes',
};

const MicIcon: React.FC<{ off?: boolean }> = ({ off }) => (
  <svg aria-hidden="true" fill="none" height="20" stroke="currentColor" viewBox="0 0 24 24" width="20">
    <rect height="12" rx="3" strokeWidth="1.8" width="6" x="9" y="3" />
    <path d="M5 10.5v1.5a7 7 0 0 0 14 0v-1.5M12 19v2.5" strokeLinecap="round" strokeWidth="1.8" />
    {off ? <path d="M4.5 4.5l15 15" strokeLinecap="round" strokeWidth="2" /> : null}
  </svg>
);

const KeyboardIcon: React.FC = () => (
  <svg aria-hidden="true" fill="none" height="19" stroke="currentColor" viewBox="0 0 24 24" width="19">
    <rect height="12" rx="2.5" strokeWidth="1.7" width="18" x="3" y="6" />
    <path d="M7 10h.01M10 10h.01M13 10h.01M16 10h.01M8 14h8" strokeLinecap="round" strokeWidth="1.9" />
  </svg>
);

const ArrowIcon: React.FC = () => (
  <svg aria-hidden="true" fill="none" height="14" stroke="currentColor" viewBox="0 0 24 24" width="14">
    <path d="M7 17L17 7M9 7h8v8" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
  </svg>
);

function ErrorCard({ error, onRetry }: { error: LiveVoiceError; onRetry?: () => void }) {
  return (
    <div className={`lv-notice${error.kind === 'no_api_key' ? ' lv-notice--setup' : ''}`} role="alert">
      <p>{error.message}</p>
      {error.kind === 'no_api_key' ? (
        <Link className="lv-pill-button" to="/account#ai-key">
          Add your OpenAI key
        </Link>
      ) : error.kind === 'sign_in' ? (
        <Link className="lv-pill-button" to="/login">
          Sign in
        </Link>
      ) : onRetry ? (
        <button className="lv-pill-button" onClick={onRetry} type="button">
          Try again
        </button>
      ) : null}
    </div>
  );
}

const LiveVoicePanel: React.FC<LiveVoicePanelProps> = ({ session, layout = 'docked', blocked, onClose }) => {
  const { state, context, start, end, toggleMute, sendText } = session;
  const [expanded, setExpanded] = useState(layout === 'page');
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState('');
  const panelRef = useRef<HTMLElement>(null);
  const captionsRef = useRef<HTMLOListElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const live = isLivePhase(state.phase);
  const connecting = state.phase === 'connecting';
  useAudioLevels(panelRef, session);

  useEffect(() => {
    if (layout === 'docked') panelRef.current?.focus();
  }, [layout]);

  useEffect(() => {
    if (!onClose) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    const list = captionsRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [state.captions]);

  useEffect(() => {
    if (typing) inputRef.current?.focus();
  }, [typing]);

  const captions = expanded ? state.captions : state.captions.slice(-3);
  const activity = expanded ? state.activity : state.activity.slice(-3);
  const showSuggestions = !blocked && state.captions.length === 0 && state.phase !== 'error';
  const error = blocked ?? state.error;
  const { title, hint } = headline(state, Boolean(blocked));
  const latestAssistant = [...captions].reverse().find(caption => caption.role === 'assistant')?.id;

  const say = async (text: string) => {
    if (!live) await start();
    await sendText(text);
  };

  const submitDraft = async (event: React.FormEvent) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    await say(text);
  };

  return (
    <section
      aria-label="Talk to Manifest"
      className={`lv-panel lv-panel--${layout}${expanded ? ' lv-panel--expanded' : ''}`}
      data-mood={blocked ? 'idle' : moodOf(state)}
      data-phase={state.phase}
      data-testid="live-voice-panel"
      ref={panelRef}
      tabIndex={-1}
    >
      <div aria-hidden="true" className="lv-aurora">
        <span />
        <span />
      </div>

      <header className="lv-header">
        <div className="lv-brand">
          <LevelMeter />
          <span className="lv-brand__name">Manifest</span>
          <span className="lv-brand__badge">Voice</span>
        </div>
        <div className="lv-header__actions">
          {layout === 'docked' ? (
            <button
              aria-label={expanded ? 'Show less' : 'Show the whole conversation'}
              aria-pressed={expanded}
              className="lv-ghost"
              onClick={() => setExpanded(value => !value)}
              type="button"
            >
              <svg aria-hidden="true" fill="none" height="15" stroke="currentColor" viewBox="0 0 24 24" width="15">
                <path
                  d={expanded ? 'M9 15H4v5M15 9h5V4M4 20l6-6M20 4l-6 6' : 'M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7'}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.9"
                />
              </svg>
            </button>
          ) : null}
          {onClose ? (
            <button aria-label="Close voice" className="lv-ghost" onClick={onClose} type="button">
              <svg aria-hidden="true" fill="none" height="15" stroke="currentColor" viewBox="0 0 24 24" width="15">
                <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" strokeWidth="1.9" />
              </svg>
            </button>
          ) : null}
        </div>
      </header>

      <div className="lv-stage">
        <VoiceOrb size={expanded ? 'lg' : 'sm'} />
        <div className="lv-headline">
          <p aria-live="polite" className="lv-headline__title" data-testid="live-voice-status">
            {title}
          </p>
          {hint ? <p className="lv-headline__hint">{hint}</p> : null}
        </div>
        {!live && !connecting && !blocked ? (
          <button className="lv-start" data-testid="live-voice-start" onClick={() => void start()} type="button">
            <MicIcon />
            {state.phase === 'ended' || state.phase === 'error' ? 'Talk again' : 'Start talking'}
          </button>
        ) : null}
      </div>

      {error ? <ErrorCard error={error} onRetry={blocked ? undefined : () => void start()} /> : null}

      {captions.length ? (
        <ol aria-label="Conversation" aria-live="polite" className="lv-transcript" ref={captionsRef}>
          {captions.map(caption => (
            <li
              className={[
                'lv-line',
                `lv-line--${caption.role}`,
                caption.final ? '' : 'lv-line--live',
                caption.id === latestAssistant ? 'lv-line--latest' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              key={caption.id}
            >
              <span className="lv-sr">{caption.role === 'user' ? 'You: ' : 'Manifest: '}</span>
              {caption.text}
            </li>
          ))}
        </ol>
      ) : null}

      {activity.length ? (
        <ol aria-label="What Manifest did" className="lv-steps">
          {activity.map(item => (
            <li className={`lv-step lv-step--${item.status}`} key={item.id}>
              <span className="lv-step__dot">
                <ActivityIcon status={item.status} />
              </span>
              <span className="lv-step__label">{item.label}</span>
              <span className="lv-step__status">
                {item.status === 'failed' && item.summary ? item.summary : STATUS_TEXT[item.status]}
              </span>
            </li>
          ))}
        </ol>
      ) : null}

      {showSuggestions ? (
        <div aria-label="Try saying" className="lv-suggestions" role="group">
          {suggestionsFor(context).map((text, index) => (
            <button
              className="lv-suggestion"
              key={text}
              onClick={() => void say(text)}
              style={{ animationDelay: `${120 + index * 70}ms` }}
              type="button"
            >
              <span>{text}</span>
              <ArrowIcon />
            </button>
          ))}
        </div>
      ) : null}

      {!blocked ? (
        <footer className={`lv-dock${typing || !live ? ' lv-dock--typing' : ''}`}>
          {typing || !live ? (
            <form className="lv-type" onSubmit={event => void submitDraft(event)}>
              <label className="lv-sr" htmlFor="lv-type-input">
                Type to Manifest
              </label>
              <input
                autoComplete="off"
                id="lv-type-input"
                onChange={event => setDraft(event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Escape') {
                    event.stopPropagation();
                    setTyping(false);
                  }
                }}
                placeholder="Message Manifest…"
                ref={inputRef}
                value={draft}
              />
              <button aria-label="Send" className="lv-send" disabled={!draft.trim()} type="submit">
                <svg aria-hidden="true" fill="none" height="16" stroke="currentColor" viewBox="0 0 24 24" width="16">
                  <path d="M12 19V5M6 11l6-6 6 6" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" />
                </svg>
              </button>
            </form>
          ) : (
            <button aria-label="Type instead" className="lv-round" onClick={() => setTyping(true)} type="button">
              <KeyboardIcon />
            </button>
          )}
          {live ? (
            <>
              <button
                aria-label={state.muted ? 'Unmute microphone' : 'Mute microphone'}
                aria-pressed={state.muted}
                className={`lv-round lv-round--mic${state.muted ? ' is-muted' : ''}`}
                onClick={toggleMute}
                type="button"
              >
                <MicIcon off={state.muted} />
              </button>
              <button aria-label="End" className="lv-round lv-round--end" onClick={() => void end()} type="button">
                <svg aria-hidden="true" fill="none" height="18" stroke="currentColor" viewBox="0 0 24 24" width="18">
                  <path d="M7 7l10 10M17 7L7 17" strokeLinecap="round" strokeWidth="2.2" />
                </svg>
              </button>
            </>
          ) : null}
        </footer>
      ) : null}
    </section>
  );
};

export default LiveVoicePanel;
