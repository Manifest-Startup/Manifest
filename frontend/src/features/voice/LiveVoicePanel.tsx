import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import type { LiveActivity, LiveVoiceError, LiveVoicePhase, LiveVoiceState } from './liveVoice';
import { suggestionsFor } from './liveVoice';
import type { BridgeInfo } from './localAgent';
import type { PipecatVoiceSessionApi } from './usePipecatVoiceSession';
import VoiceSetup from './VoiceSetup';
import './liveVoicePanel.css';

export type LiveVoicePanelLayout = 'docked' | 'page';

interface LiveVoicePanelProps {
  session: PipecatVoiceSessionApi;
  layout?: LiveVoicePanelLayout;
  /** Shown instead of the conversation when live voice can't start (e.g. no OpenAI key). */
  blocked?: LiveVoiceError | null;
  onClose?: () => void;
  /** Voice was just set up on this computer (the bridge answered): connect to it. */
  onSetupReady?: (bridge: BridgeInfo) => void;
}

/** Errors that mean "nothing to talk to here yet": show the one-step setup instead. */
export const needsSetup = (error: LiveVoiceError | null | undefined) =>
  Boolean(error && (error.kind === 'setup' || error.kind === 'no_api_key' || error.kind === 'sign_in'));

type Mood = LiveVoicePhase | 'muted';

const STATUS: Record<Mood, string> = {
  idle: 'Manifest',
  connecting: 'Connecting',
  listening: 'Listening',
  thinking: 'Thinking',
  speaking: 'Manifest',
  muted: 'Muted',
  ended: 'Manifest',
  error: 'Manifest',
};

const isLivePhase = (phase: LiveVoicePhase) =>
  phase === 'listening' || phase === 'thinking' || phase === 'speaking';

function moodOf(state: LiveVoiceState, blocked: boolean): Mood {
  if (blocked) return 'idle';
  if (state.muted && isLivePhase(state.phase)) return 'muted';
  return state.phase;
}

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
}

/**
 * Moves the glow and the orb with the live audio. Only `opacity` and `transform` are written,
 * straight to two elements, so the browser composites on the GPU: no layout, no paint and no
 * React renders. The loop runs only while a conversation is live (and the tab is visible).
 */
function useLiveMotion(
  session: PipecatVoiceSessionApi,
  glowRef: React.RefObject<HTMLDivElement | null>,
  orbRef: React.RefObject<HTMLDivElement | null>,
) {
  const { phase, muted } = session.state;
  useEffect(() => {
    const glow = glowRef.current;
    const orb = orbRef.current;
    const reset = () => {
      if (glow) glow.style.opacity = '';
      if (orb) orb.style.transform = '';
    };
    if (!isLivePhase(phase) || prefersReducedMotion()) {
      reset();
      return undefined;
    }
    let frame = 0;
    let level = 0;
    const tick = () => {
      const { mic, bot } = session.levelsRef.current;
      const target = Math.min(1, Math.max(bot, muted ? 0 : mic * 0.85) * 2.6);
      level += (target - level) * (target > level ? 0.35 : 0.08); // fast attack, slow release
      if (glow) glow.style.opacity = (0.1 + level * 0.6).toFixed(3);
      if (orb) orb.style.transform = `scale(${(1 + level * 0.22).toFixed(3)})`;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      reset();
    };
  }, [phase, muted, session.levelsRef, glowRef, orbRef]);
}

const Glyph: React.FC<{ d: string; size?: number; width?: number }> = ({ d, size = 18, width = 2 }) => (
  <svg aria-hidden="true" fill="none" height={size} stroke="currentColor" viewBox="0 0 24 24" width={size}>
    <path d={d} strokeLinecap="round" strokeLinejoin="round" strokeWidth={width} />
  </svg>
);

const MIC = 'M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21';
const MIC_OFF = `${MIC}M4 4l16 16`;
const KEYS = 'M4 7h16v10H4zM7.5 10.5h.01M10.5 10.5h.01M13.5 10.5h.01M16.5 10.5h.01M8.5 14h7';
const CLOSE = 'M7 7l10 10M17 7L7 17';
const SEND = 'M12 19V5M6.5 10.5L12 5l5.5 5.5';

function statusLine(mood: Mood, action: LiveActivity | undefined): { text: string; kind: string } {
  if (action?.status === 'confirm' && mood !== 'thinking') return { text: 'Say “yes” to confirm', kind: 'confirm' };
  if (action?.status === 'running') return { text: action.label, kind: 'running' };
  return { text: STATUS[mood], kind: mood };
}

/** A small cloud of light: two soft gradients turning inside a sphere (transform-only). */
const Orb: React.FC<{ size: 'sm' | 'lg'; orbRef?: React.RefObject<HTMLDivElement | null> }> = ({ size, orbRef }) => (
  <div aria-hidden="true" className={`lv-orb lv-orb--${size}`} ref={orbRef}>
    <span className="lv-orb__cloud lv-orb__cloud--a" />
    <span className="lv-orb__cloud lv-orb__cloud--b" />
  </div>
);

const LiveVoicePanel: React.FC<LiveVoicePanelProps> = ({ session, layout = 'docked', blocked, onClose, onSetupReady }) => {
  const { state, context, start, end, toggleMute, sendText, interrupt } = session;
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState('');
  const glowRef = useRef<HTMLDivElement>(null);
  const orbRef = useRef<HTMLDivElement>(null);
  const islandRef = useRef<HTMLElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const live = isLivePhase(state.phase);
  const connecting = state.phase === 'connecting';
  const error = blocked ?? state.error;
  const mood = moodOf(state, Boolean(blocked));
  useLiveMotion(session, glowRef, orbRef);

  useEffect(() => {
    if (layout === 'docked') islandRef.current?.focus();
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
    if (typing) inputRef.current?.focus();
  }, [typing]);

  const canInterrupt = Boolean(interrupt) && state.phase === 'speaking';
  useEffect(() => {
    if (!canInterrupt || !interrupt) return undefined;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (event.code !== 'Space' || target?.closest('input, textarea, button, [contenteditable="true"]')) return;
      event.preventDefault();
      interrupt();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [canInterrupt, interrupt]);

  const lastAssistant = [...state.captions].reverse().find(caption => caption.role === 'assistant');
  const lastUser = [...state.captions].reverse().find(caption => caption.role === 'user');
  const userIsNewer = Boolean(lastUser && (!lastAssistant || lastUser.id > lastAssistant.id));
  const action = state.activity[state.activity.length - 1];
  const status = canInterrupt && action?.status !== 'running' ? { text: 'Talk or tap to interrupt', kind: 'speaking' } : statusLine(mood, action);
  const setup = needsSetup(error);
  const showSuggestions = !error && state.captions.length === 0 && !connecting && !typing;

  const say = async (text: string) => {
    if (!live) await start();
    await sendText(text);
  };

  const submitDraft = async (event: React.FormEvent) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    setTyping(false);
    await say(text);
  };

  let words: React.ReactNode;
  if (setup && error) {
    words = onSetupReady ? (
      <VoiceSetup onReady={onSetupReady} signIn={error.kind === 'sign_in'} />
    ) : (
      <span className="lv-line">{error.message}</span>
    );
  } else if (error) {
    words = <span className="lv-line">{error.message}</span>;
  } else if (typing) {
    words = (
      <form className="lv-type" onSubmit={event => void submitDraft(event)}>
        <label className="lv-sr" htmlFor="lv-type-input">
          Message Manifest
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
          placeholder="Message"
          ref={inputRef}
          value={draft}
        />
        <button aria-label="Send" className="lv-send" disabled={!draft.trim()} type="submit">
          <Glyph d={SEND} size={14} width={2.5} />
        </button>
      </form>
    );
  } else if (userIsNewer && lastUser) {
    words = (
      <span className={`lv-line lv-line--heard${lastUser.final ? '' : ' lv-line--live'}`}>
        <span className="lv-sr">You: </span>
        {lastUser.text}
      </span>
    );
  } else if (lastAssistant) {
    words = (
      <span className="lv-line" data-testid="live-voice-reply" key={lastAssistant.id}>
        <span className="lv-sr">Manifest: </span>
        {lastAssistant.text}
      </span>
    );
  } else {
    words = (
      <span className="lv-line lv-line--quiet">{state.phase === 'ended' ? 'Talk again any time.' : 'How can I help?'}</span>
    );
  }

  return (
    <div className={`lv lv--${layout}`} data-mood={mood} data-phase={state.phase} data-testid="live-voice-panel">
      {layout === 'docked' ? (
        <div aria-hidden="true" className="lv-edge">
          <div className="lv-edge__ring lv-edge__ring--base" />
          <div className="lv-edge__ring lv-edge__ring--hot" ref={glowRef} />
        </div>
      ) : (
        <div aria-hidden="true" className="lv-hero">
          <div className="lv-hero__glow" ref={glowRef} />
          {canInterrupt ? (
            <button aria-label="Stop speaking" className="lv-orb-btn" onClick={interrupt} type="button">
              <Orb orbRef={orbRef} size="lg" />
            </button>
          ) : (
            <Orb orbRef={orbRef} size="lg" />
          )}
        </div>
      )}

      {showSuggestions ? (
        <div aria-label="Try" className="lv-chips" role="group">
          {suggestionsFor(context).map(text => (
            <button className="lv-chip" key={text} onClick={() => void say(text)} type="button">
              {text}
            </button>
          ))}
        </div>
      ) : null}

      <section aria-label="Talk to Manifest" className="lv-island" ref={islandRef} tabIndex={-1}>
        {layout === 'docked' ? (
          canInterrupt ? (
            <button aria-label="Stop speaking" className="lv-orb-btn" onClick={interrupt} type="button">
              <Orb orbRef={orbRef} size="sm" />
            </button>
          ) : (
            <Orb orbRef={orbRef} size="sm" />
          )
        ) : null}
        <div aria-live="polite" className="lv-text">
          <span
            className={`lv-status lv-status--${status.kind}${status.text === 'Manifest' ? ' lv-sr' : ''}`}
            data-testid="live-voice-status"
          >
            {status.kind === 'running' ? <span aria-hidden="true" className="lv-spin" /> : null}
            {status.text}
          </span>
          {words}
        </div>

        <div className="lv-controls">
          {setup && onSetupReady ? null : error?.kind === 'no_api_key' ? (
            <Link className="lv-pill" to="/account#ai-key">
              Add key
            </Link>
          ) : error?.kind === 'sign_in' ? (
            <Link className="lv-pill" to="/login">
              Sign in
            </Link>
          ) : error && !blocked ? (
            <button className="lv-pill" onClick={() => void start()} type="button">
              Retry
            </button>
          ) : null}
          {!blocked && !typing && !error ? (
            <button aria-label="Type instead" className="lv-btn lv-btn--type" onClick={() => setTyping(true)} type="button">
              <Glyph d={KEYS} size={17} width={1.8} />
            </button>
          ) : null}
          {live ? (
            <button
              aria-label={state.muted ? 'Unmute microphone' : 'Mute microphone'}
              aria-pressed={state.muted}
              className={`lv-btn${state.muted ? ' is-on' : ''}`}
              onClick={toggleMute}
              type="button"
            >
              <Glyph d={state.muted ? MIC_OFF : MIC} size={17} />
            </button>
          ) : !blocked && !connecting && !error ? (
            <button className="lv-pill" data-testid="live-voice-start" onClick={() => void start()} type="button">
              <Glyph d={MIC} size={15} width={2.2} />
              Talk
            </button>
          ) : null}
          {live ? (
            <button aria-label="End" className="lv-btn lv-btn--end" onClick={onClose ?? (() => void end())} type="button">
              <Glyph d={CLOSE} size={15} width={2.4} />
            </button>
          ) : onClose ? (
            <button aria-label="Close voice" className="lv-btn" onClick={onClose} type="button">
              <Glyph d={CLOSE} size={15} width={2.4} />
            </button>
          ) : null}
        </div>
      </section>
    </div>
  );
};

export default LiveVoicePanel;
