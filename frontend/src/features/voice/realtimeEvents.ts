/**
 * Pure reducer for OpenAI Realtime *server* events arriving over the WebRTC
 * data channel. Keeping this side-effect free means the conversation/transcript
 * logic is unit-testable without a real peer connection.
 *
 * We intentionally tolerate both the older (`response.audio_transcript.*`) and
 * newer (`response.output_audio_transcript.*`) event names so the client keeps
 * working across Realtime API revisions.
 */

export type RealtimeVoicePhase = 'idle' | 'listening' | 'thinking' | 'speaking';

export interface RealtimeConversationTurn {
  role: 'user' | 'assistant';
  content: string;
}

export interface RealtimeTranscriptState {
  phase: RealtimeVoicePhase;
  /** Latest finalized user utterance (for interim display). */
  userText: string;
  /** Assistant text accumulating for the in-progress reply. */
  assistantText: string;
  messages: RealtimeConversationTurn[];
  error: string | null;
}

export function createRealtimeTranscriptState(): RealtimeTranscriptState {
  return { phase: 'idle', userText: '', assistantText: '', messages: [], error: null };
}

interface RealtimeServerEvent {
  type?: string;
  delta?: string;
  transcript?: string;
  error?: { message?: string } | string;
}

function readString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

export function reduceRealtimeEvent(
  state: RealtimeTranscriptState,
  event: RealtimeServerEvent,
): RealtimeTranscriptState {
  const type = event?.type ?? '';

  switch (type) {
    case 'input_audio_buffer.speech_started':
      // Native barge-in: the server stops assistant audio when the user speaks.
      return { ...state, phase: 'listening' };

    case 'conversation.item.input_audio_transcription.delta':
      return { ...state, userText: state.userText + readString(event.delta) };

    case 'conversation.item.input_audio_transcription.completed': {
      const finalUser = readString(event.transcript).trim();
      if (!finalUser) {
        return { ...state, userText: '', phase: 'thinking' };
      }
      return {
        ...state,
        userText: '',
        phase: 'thinking',
        messages: [...state.messages, { role: 'user', content: finalUser }],
      };
    }

    case 'response.created':
      return { ...state, phase: 'thinking', assistantText: '' };

    case 'output_audio_buffer.started':
    case 'response.output_audio.started':
      return { ...state, phase: 'speaking' };

    case 'response.audio_transcript.delta':
    case 'response.output_audio_transcript.delta':
      return {
        ...state,
        phase: 'speaking',
        assistantText: state.assistantText + readString(event.delta),
      };

    case 'response.audio_transcript.done':
    case 'response.output_audio_transcript.done': {
      const finalAssistant = (readString(event.transcript) || state.assistantText).trim();
      if (!finalAssistant) {
        return { ...state, assistantText: '' };
      }
      return {
        ...state,
        assistantText: '',
        messages: [...state.messages, { role: 'assistant', content: finalAssistant }],
      };
    }

    case 'output_audio_buffer.stopped':
    case 'response.done':
      return { ...state, phase: 'idle' };

    case 'error': {
      const message =
        typeof event.error === 'string'
          ? event.error
          : readString(event.error?.message) || 'Realtime voice error';
      return { ...state, error: message };
    }

    default:
      return state;
  }
}
