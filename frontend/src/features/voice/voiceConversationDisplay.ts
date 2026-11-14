import type { VoiceConversationMessage } from './voiceAgentApi';

export interface VoiceTranscriptTurn {
  role: 'user' | 'assistant';
  text: string;
  /** Index in the original conversationMessages array (for keys). */
  sourceIndex: number;
}

/**
 * Assistant history entries from the API are JSON with a human-readable `message` field.
 */
export function displayTextForConversationMessage(message: VoiceConversationMessage): string {
  if (message.role === 'user') {
    return message.content.trim();
  }

  if (message.role === 'assistant') {
    return parseAssistantHistoryContent(message.content);
  }

  return '';
}

function parseAssistantHistoryContent(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) {
    return '';
  }

  if (trimmed.startsWith('{')) {
    try {
      const parsed = JSON.parse(trimmed) as { message?: unknown };
      if (typeof parsed.message === 'string') {
        return parsed.message.trim();
      }
    } catch {
      // fall through
    }
  }

  return trimmed;
}

/** User and assistant turns only; skips empty lines and unknown roles. */
export function buildTranscriptTurns(messages: VoiceConversationMessage[]): VoiceTranscriptTurn[] {
  const turns: VoiceTranscriptTurn[] = [];

  messages.forEach((message, sourceIndex) => {
    if (message.role !== 'user' && message.role !== 'assistant') {
      return;
    }

    const text = displayTextForConversationMessage(message);
    if (!text) {
      return;
    }

    turns.push({
      role: message.role,
      text,
      sourceIndex,
    });
  });

  return turns;
}
