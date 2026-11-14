import React, { useEffect, useRef } from 'react';

import type { VoiceConversationMessage } from './voiceAgentApi';
import { buildTranscriptTurns } from './voiceConversationDisplay';

export interface VoiceLiveTranscriptProps {
  conversationMessages: VoiceConversationMessage[];
  interimTranscript: string;
  isListening: boolean;
  isSpeaking: boolean;
  isProcessing: boolean;
  /** Assistant reply still streaming (before structured history replaces it). */
  streamingAssistantText?: string;
}

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) {
    return false;
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

const VoiceLiveTranscript: React.FC<VoiceLiveTranscriptProps> = ({
  conversationMessages,
  interimTranscript,
  isListening,
  isSpeaking,
  isProcessing,
  streamingAssistantText = '',
}) => {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const turns = buildTranscriptTurns(conversationMessages);
  const showInterim = Boolean(isListening && interimTranscript.trim());
  const streamText = streamingAssistantText.trim();
  const lastTurn = turns.length ? turns[turns.length - 1] : null;
  const hideDuplicateAssistantRow =
    lastTurn?.role === 'assistant' && streamText.length > 0 && lastTurn.text === streamText;

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) {
      return;
    }

    if (prefersReducedMotion()) {
      el.scrollTop = el.scrollHeight;
      return;
    }

    if (typeof el.scrollTo === 'function') {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    } else {
      el.scrollTop = el.scrollHeight;
    }
  }, [turns.length, interimTranscript, showInterim, streamText, isProcessing]);

  const showThinkingOnly = isProcessing && !streamText && !turns.length && !showInterim;

  if (!turns.length && !showInterim && !streamText && !showThinkingOnly) {
    return null;
  }

  return (
    <div className="voice-transcript" data-testid="voice-live-transcript">
      {/* Transcript history is navigable; status line + optional region below cover screen-reader updates for live speech. */}
      <div className="voice-transcript__viewport" ref={viewportRef} role="log" aria-live="off">
        <div className="voice-transcript__inner">
          {turns.reduce<React.ReactNode[]>((nodes, turn, index) => {
            const isLast = index === turns.length - 1;
            const isPast = !isLast || showInterim || Boolean(streamText);
            const isLatestAssistant = turn.role === 'assistant' && isLast;
            const rowClass = [
              'voice-transcript__row',
              turn.role === 'user' ? 'voice-transcript__row--user' : 'voice-transcript__row--assistant',
              isPast ? 'voice-transcript__row--past' : 'voice-transcript__row--recent',
              isLatestAssistant && isSpeaking && !streamText ? 'voice-transcript__row--speaking' : '',
              isLatestAssistant && isProcessing && !streamText ? 'voice-transcript__row--thinking' : '',
            ]
              .filter(Boolean)
              .join(' ');

            if (hideDuplicateAssistantRow && isLatestAssistant) {
              return nodes;
            }

            nodes.push(
              <p key={`${turn.sourceIndex}-${turn.role}`} className={rowClass}>
                <span className="voice-transcript__label">{turn.role === 'user' ? 'You' : 'Manifest'}</span>
                <span className="voice-transcript__text">{turn.text}</span>
              </p>,
            );
            return nodes;
          }, [])}

          {streamText ? (
            <p
              className={`voice-transcript__row voice-transcript__row--assistant voice-transcript__row--recent voice-transcript__row--streaming ${
                isSpeaking ? 'voice-transcript__row--speaking' : ''
              } ${isProcessing ? 'voice-transcript__row--thinking' : ''}`}
            >
              <span className="voice-transcript__label">Manifest</span>
              <span className="voice-transcript__text">{streamText}</span>
            </p>
          ) : null}

          {showThinkingOnly ? (
            <p className="voice-transcript__row voice-transcript__row--assistant voice-transcript__row--recent voice-transcript__row--thinking">
              <span className="voice-transcript__label">Manifest</span>
              <span className="voice-transcript__text voice-transcript__text--placeholder">Thinking…</span>
            </p>
          ) : null}

          {showInterim ? (
            <p className="voice-transcript__row voice-transcript__row--user voice-transcript__row--interim voice-transcript__row--recent">
              <span className="voice-transcript__label">You</span>
              <span className="voice-transcript__text">{interimTranscript.trim()}</span>
            </p>
          ) : null}
        </div>
      </div>

      {showInterim ? (
        <p className="voice-transcript__sr-live" aria-live="polite">
          {interimTranscript.trim()}
        </p>
      ) : null}
    </div>
  );
};

export default VoiceLiveTranscript;
