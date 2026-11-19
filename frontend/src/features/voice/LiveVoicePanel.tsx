import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import type { LiveActivity, LiveVoiceError, LiveVoicePhase, LiveVoiceState } from './liveVoice';
import { suggestionsFor } from './liveVoice';
import type { PipecatVoiceSessionApi } from './usePipecatVoiceSession';
import VoiceRibbon, { RibbonMood } from './VoiceRibbon';
import './liveVoicePanel.css';

export type LiveVoicePanelLayout = 'docked' | 'page';

interface LiveVoicePanelProps {
  session: PipecatVoiceSessionApi;
  layout?: LiveVoicePanelLayout;
  /** Shown instead of the conversation when live voice can't start (e.g. no OpenAI key). */
  blocked?: LiveVoiceError | null;
  onClose?: () => void;
}

const STATUS: Record<LiveVoicePhase, string> = {
  idle: 'Manifest',
  connecting: 'Connecting',
  listening: 'Listening',
  thinking: 'Thinking',
  speaking: 'Speaking',
  ended: 'Manifest',
  error: 'Manifest',
};

const isLivePhase = (phase: LiveVoicePhase) =>
  phase === 'listening' || phase === 'thinking' || phase === 'speaking';

function moodOf(state: LiveVoiceState, blocked: boolean): RibbonMood {
  if (blocked) return 'idle';
  if (state.muted && isLivePhase(state.phase)) return 'muted';
  return state.phase;
}

const ACTION_MARK: Record<LiveActivity['status'], string> = {
  running: '',
  done: '✓',
  failed: '!',
  confirm: '',
};

const Glyph: React.FC<{ d: string; size?: number; width?: number }> = ({ d, size = 18, width = 1.9 }) => (
  <svg aria-hidden="true" fill="none" height={size} stroke="currentColor" viewBox="0 0 24 24" width={size}>
    <path d={d} strokeLinecap="round" strokeLinejoin="round" strokeWidth={width} />
  </svg>
);

const MIC = 'M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21';
const MIC_OFF = `${MIC}M4 4l16 16`;
const KEYS = 'M4 7h16v10H4zM7.5 10.5h.01M10.5 10.5h.01M13.5 10.5h.01M16.5 10.5h.01M8.5 14h7';
const CLOSE = 'M7 7l10 10M17 7L7 17';
const SEND = 'M12 19V5M6.5 10.5L12 5l5.5 5.5';

const LiveVoicePanel: React.FC<LiveVoicePanelProps> = ({ session, layout = 'docked', blocked, onClose }) => {
  const { state, context, start, end, toggleMute, sendText, levelsRef } = session;
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState('');
  const panelRef = useRef<HTMLElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const live = isLivePhase(state.phase);
  const connecting = state.phase === 'connecting';
  const error = blocked ?? state.error;
  const mood = moodOf(state, Boolean(blocked));

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
    if (typing) inputRef.current?.focus();
  }, [typing]);

  const lastAssistant = [...state.captions].reverse().find(caption => caption.role === 'assistant');
  const lastUser = [...state.captions].reverse().find(caption => caption.role === 'user');
  const userIsNewer = Boolean(lastUser && (!lastAssistant || lastUser.id > lastAssistant.id));
  const action = state.activity[state.activity.length - 1];
  const showSuggestions = !error && state.captions.length === 0 && !connecting;

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
      className={`lv-panel lv-panel--${layout}`}
      data-mood={mood}
      data-phase={state.phase}
      data-testid="live-voice-panel"
      ref={panelRef}
      tabIndex={-1}
    >
      <p aria-live="polite" className="lv-status" data-testid="live-voice-status">
        {state.muted && live ? 'Muted' : STATUS[state.phase]}
      </p>
      {onClose ? (
        <button aria-label="Close voice" className="lv-close" onClick={onClose} type="button">
          <Glyph d={CLOSE} size={14} width={2.2} />
        </button>
      ) : null}

      <VoiceRibbon levelsRef={levelsRef} mood={mood} />

      <div aria-live="polite" className="lv-words">
        {error ? (
          <>
            <p className="lv-say">{error.kind === 'no_api_key' ? 'Add your OpenAI key to talk.' : error.message}</p>
            {error.kind === 'no_api_key' ? (
              <Link className="lv-cta" to="/account#ai-key">
                Add key
              </Link>
            ) : error.kind === 'sign_in' ? (
              <Link className="lv-cta" to="/login">
                Sign in
              </Link>
            ) : blocked ? null : (
              <button className="lv-cta" onClick={() => void start()} type="button">
                Try again
              </button>
            )}
          </>
        ) : userIsNewer && lastUser ? (
          <p className={`lv-heard${lastUser.final ? '' : ' lv-heard--live'}`}>
            <span className="lv-sr">You: </span>
            {lastUser.text}
          </p>
        ) : lastAssistant ? (
          <p className="lv-say" data-testid="live-voice-reply">
            <span className="lv-sr">Manifest: </span>
            {lastAssistant.text}
          </p>
        ) : !live && !connecting ? (
          <p className="lv-say lv-say--quiet">{state.phase === 'ended' ? 'Talk again any time.' : 'How can I help?'}</p>
        ) : null}
      </div>

      {action && !error ? (
        <p className={`lv-action lv-action--${action.status}`} key={action.id}>
          {action.status === 'running' ? <span aria-hidden="true" className="lv-action__spin" /> : null}
          {ACTION_MARK[action.status] ? <span aria-hidden="true">{ACTION_MARK[action.status]}</span> : null}
          {action.status === 'confirm' ? 'Say “yes” to confirm' : action.label}
        </p>
      ) : null}

      {showSuggestions ? (
        <div aria-label="Try" className="lv-chips" role="group">
          {suggestionsFor(context).map(text => (
            <button className="lv-chip" key={text} onClick={() => void say(text)} type="button">
              {text}
            </button>
          ))}
        </div>
      ) : null}

      {!blocked ? (
        <div className="lv-bar">
          {typing ? (
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
                <Glyph d={SEND} size={15} width={2.4} />
              </button>
            </form>
          ) : (
            <button aria-label="Type instead" className="lv-round" onClick={() => setTyping(true)} type="button">
              <Glyph d={KEYS} />
            </button>
          )}
          {live ? (
            <>
              <button
                aria-label={state.muted ? 'Unmute microphone' : 'Mute microphone'}
                aria-pressed={state.muted}
                className={`lv-round${state.muted ? ' is-muted' : ''}`}
                onClick={toggleMute}
                type="button"
              >
                <Glyph d={state.muted ? MIC_OFF : MIC} />
              </button>
              <button aria-label="End" className="lv-round lv-round--end" onClick={() => void end()} type="button">
                <Glyph d={CLOSE} size={16} width={2.3} />
              </button>
            </>
          ) : !connecting && !typing && !error ? (
            <button className="lv-talk" data-testid="live-voice-start" onClick={() => void start()} type="button">
              <Glyph d={MIC} size={16} width={2.1} />
              Talk
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
};

export default LiveVoicePanel;
