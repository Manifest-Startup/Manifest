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
  connecting: 'Connecting…',
  listening: 'Listening',
  thinking: 'Thinking…',
  speaking: 'Speaking',
  ended: 'Conversation ended',
  error: 'Needs attention',
};

function phaseLabel(state: LiveVoiceState): string {
  if (state.muted && (state.phase === 'listening' || state.phase === 'thinking')) return 'Muted';
  return PHASE_LABEL[state.phase];
}

const isLivePhase = (phase: LiveVoicePhase) =>
  phase === 'listening' || phase === 'thinking' || phase === 'speaking';

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
}

/** The orb: two layers that breathe with the mic (inner) and Manifest's voice (outer). */
const VoiceOrb: React.FC<{ session: PipecatVoiceSessionApi; size: 'sm' | 'lg' }> = ({ session, size }) => {
  const orbRef = useRef<HTMLDivElement>(null);
  const { phase, muted } = session.state;

  useEffect(() => {
    const node = orbRef.current;
    if (!node || prefersReducedMotion() || !isLivePhase(phase)) {
      node?.style.setProperty('--lv-mic', '0');
      node?.style.setProperty('--lv-bot', '0');
      return undefined;
    }
    let frame = 0;
    let mic = 0;
    let bot = 0;
    const tick = () => {
      const levels = session.levelsRef.current;
      // Ease toward the live level so the orb moves smoothly, never jitters.
      mic += ((muted ? 0 : Math.min(1, levels.mic * 2.2)) - mic) * 0.25;
      bot += (Math.min(1, levels.bot * 2.2) - bot) * 0.2;
      node.style.setProperty('--lv-mic', mic.toFixed(3));
      node.style.setProperty('--lv-bot', bot.toFixed(3));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [phase, muted, session.levelsRef]);

  return (
    <div
      aria-hidden="true"
      className={`lv-orb lv-orb--${size} lv-orb--${phase}${muted ? ' lv-orb--muted' : ''}`}
      ref={orbRef}
    >
      <span className="lv-orb__halo" />
      <span className="lv-orb__ring" />
      <span className="lv-orb__core" />
    </div>
  );
};

const ActivityIcon: React.FC<{ status: LiveActivity['status'] }> = ({ status }) => {
  if (status === 'running') return <span aria-hidden="true" className="lv-activity__spinner" />;
  const path =
    status === 'done'
      ? 'M5 12.5l4.5 4.5L19 7.5'
      : status === 'failed'
        ? 'M7 7l10 10M17 7L7 17'
        : 'M12 7v6m0 3.5v.5';
  return (
    <svg aria-hidden="true" className="lv-activity__icon" fill="none" viewBox="0 0 24 24">
      <path d={path} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" />
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
  <svg aria-hidden="true" fill="none" height="18" stroke="currentColor" viewBox="0 0 24 24" width="18">
    <rect height="12" rx="3" strokeWidth="1.7" width="6" x="9" y="3" />
    <path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3" strokeLinecap="round" strokeWidth="1.7" />
    {off ? <path d="M4 4l16 16" strokeLinecap="round" strokeWidth="1.9" /> : null}
  </svg>
);

function ErrorCard({ error, onRetry }: { error: LiveVoiceError; onRetry?: () => void }) {
  return (
    <div className={`lv-error${error.kind === 'no_api_key' ? ' lv-error--setup' : ''}`} role="alert">
      <p>{error.message}</p>
      {error.kind === 'no_api_key' ? (
        <Link className="lv-button lv-button--primary" to="/account#ai-key">
          Add your OpenAI key
        </Link>
      ) : error.kind === 'sign_in' ? (
        <Link className="lv-button lv-button--primary" to="/login">
          Sign in
        </Link>
      ) : onRetry ? (
        <button className="lv-button lv-button--primary" onClick={onRetry} type="button">
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

  const submitDraft = async (event: React.FormEvent) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    if (!live) {
      await start();
    }
    await sendText(text);
  };

  const sayOrStart = async (text: string) => {
    if (!live) {
      await start();
    }
    await sendText(text);
  };

  return (
    <section
      aria-label="Talk to Manifest"
      className={`lv-panel lv-panel--${layout}${expanded ? ' lv-panel--expanded' : ''}`}
      data-phase={state.phase}
      data-testid="live-voice-panel"
      ref={panelRef}
      tabIndex={-1}
    >
      <header className="lv-header">
        <div className="lv-title">
          <span className={`lv-dot lv-dot--${state.muted && live ? 'muted' : state.phase}`} aria-hidden="true" />
          <div>
            <h2>Manifest</h2>
            <p aria-live="polite" data-testid="live-voice-status">
              {blocked ? 'Set up voice' : phaseLabel(state)}
            </p>
          </div>
        </div>
        <div className="lv-header__actions">
          {layout === 'docked' ? (
            <button
              aria-label={expanded ? 'Show less' : 'Show the whole conversation'}
              aria-pressed={expanded}
              className="lv-icon-button"
              onClick={() => setExpanded(value => !value)}
              type="button"
            >
              <svg aria-hidden="true" fill="none" height="16" stroke="currentColor" viewBox="0 0 24 24" width="16">
                <path
                  d={expanded ? 'M9 15H4v5M15 9h5V4M4 20l6-6M20 4l-6 6' : 'M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7'}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.8"
                />
              </svg>
            </button>
          ) : null}
          {onClose ? (
            <button aria-label="Close voice" className="lv-icon-button" onClick={onClose} type="button">
              <svg aria-hidden="true" fill="none" height="16" stroke="currentColor" viewBox="0 0 24 24" width="16">
                <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" strokeWidth="1.8" />
              </svg>
            </button>
          ) : null}
        </div>
      </header>

      <div className="lv-stage">
        <VoiceOrb session={session} size={expanded ? 'lg' : 'sm'} />
        {!live && !connecting && !blocked ? (
          <button
            className="lv-button lv-button--primary lv-start"
            data-testid="live-voice-start"
            onClick={() => void start()}
            type="button"
          >
            <MicIcon />
            {state.phase === 'ended' || state.phase === 'error' ? 'Talk again' : 'Start talking'}
          </button>
        ) : null}
      </div>

      {error ? <ErrorCard error={error} onRetry={blocked ? undefined : () => void start()} /> : null}

      {captions.length ? (
        <ol aria-label="Conversation" aria-live="polite" className="lv-captions" ref={captionsRef}>
          {captions.map(caption => (
            <li
              className={`lv-caption lv-caption--${caption.role}${caption.final ? '' : ' lv-caption--live'}`}
              key={caption.id}
            >
              <span className="lv-sr">{caption.role === 'user' ? 'You: ' : 'Manifest: '}</span>
              {caption.text}
            </li>
          ))}
        </ol>
      ) : null}

      {activity.length ? (
        <ul aria-label="What Manifest did" className="lv-activity">
          {activity.map(item => (
            <li className={`lv-activity__item lv-activity__item--${item.status}`} key={item.id}>
              <ActivityIcon status={item.status} />
              <span className="lv-activity__label">{item.label}</span>
              <span className="lv-activity__status">
                {item.status === 'failed' && item.summary ? item.summary : STATUS_TEXT[item.status]}
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      {showSuggestions ? (
        <div aria-label="Try saying" className="lv-suggestions" role="group">
          {suggestionsFor(context).map(text => (
            <button className="lv-chip" key={text} onClick={() => void sayOrStart(text)} type="button">
              {text}
            </button>
          ))}
        </div>
      ) : null}

      {!blocked ? (
        <footer className="lv-footer">
          {typing ? (
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
                placeholder="Type instead…"
                ref={inputRef}
                value={draft}
              />
              <button aria-label="Send" className="lv-icon-button lv-icon-button--accent" disabled={!draft.trim()} type="submit">
                <svg aria-hidden="true" fill="none" height="16" stroke="currentColor" viewBox="0 0 24 24" width="16">
                  <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                </svg>
              </button>
            </form>
          ) : (
            <button className="lv-link" onClick={() => setTyping(true)} type="button">
              Type instead
            </button>
          )}
          {live ? (
            <div className="lv-controls">
              <button
                aria-label={state.muted ? 'Unmute microphone' : 'Mute microphone'}
                aria-pressed={state.muted}
                className={`lv-icon-button lv-icon-button--round${state.muted ? ' is-on' : ''}`}
                onClick={toggleMute}
                type="button"
              >
                <MicIcon off={state.muted} />
              </button>
              <button className="lv-button lv-button--end" onClick={() => void end()} type="button">
                End
              </button>
            </div>
          ) : null}
        </footer>
      ) : null}
    </section>
  );
};

export default LiveVoicePanel;
