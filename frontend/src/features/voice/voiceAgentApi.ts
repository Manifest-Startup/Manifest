import { buildSessionHeaders } from 'features/auth/session';

export interface VoiceConversationMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface VoiceAgentStructuredContext {
  problem?: string | null;
  target_customer?: string | null;
  solution?: string | null;
  current_alternative?: string | null;
  differentiation?: string | null;
  business_model?: string | null;
  go_to_market?: string | null;
  product_scope?: string | null;
  founder_advantage?: string | null;
  risks?: string[];
  open_questions?: string[];
  next_step?: string | null;
}

export interface VoiceAgentResponse {
  message: string;
  is_qualified: boolean;
  summary: string | null;
  suggested_title: string | null;
  transcript: string | null;
  voice_note_html: string | null;
  covered_topics: string[];
  missing_topics: string[];
  qualification_confidence: number;
  context: VoiceAgentStructuredContext;
  landing_onboarding_step?: number | null;
  landing_complete?: boolean;
}

export interface VoiceAgentProcessResponse<TResponse> {
  response: TResponse;
  messages: VoiceConversationMessage[];
}

export type VoiceAgentStreamEvent =
  | { type: 'delta'; text: string }
  | { type: 'structured'; payload: VoiceAgentProcessResponse<VoiceAgentResponse> }
  | { type: 'done' }
  | { type: 'error'; error: string };

export interface VoiceAgentStartResponse {
  conversation_id: string;
  response: VoiceAgentResponse;
  messages: VoiceConversationMessage[];
}

export interface VoiceAgentTtsResponse {
  audio_base64: string | null;
  success: boolean;
  fallback_to_browser: boolean;
}

export interface VoiceAgentTranscribeResponse {
  success: boolean;
  transcript: string | null;
  error?: string | null;
}

interface PostVoiceAgentJsonOptions {
  signal?: AbortSignal;
}

const TOKEN_KEYS = ['access_token', 'sb-access-token'] as const;

export function getVoiceAgentToken(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  for (const key of TOKEN_KEYS) {
    const token = localStorage.getItem(key);
    if (token) {
      return token;
    }
  }
  return null;
}

function buildVoiceAgentHeaders(): Record<string, string> {
  const legacyToken = getVoiceAgentToken();
  return buildSessionHeaders({
    'Content-Type': 'application/json',
    ...(legacyToken ? { Authorization: `Bearer ${legacyToken}` } : {}),
  });
}

function parseSseEvent(eventName: string, data: string): VoiceAgentStreamEvent | null {
  if (!data) {
    return null;
  }

  const parsed = JSON.parse(data) as Record<string, unknown>;

  switch (eventName) {
    case 'delta':
      return { type: 'delta', text: typeof parsed.text === 'string' ? parsed.text : '' };
    case 'structured':
      return {
        type: 'structured',
        payload: parsed as unknown as VoiceAgentProcessResponse<VoiceAgentResponse>,
      };
    case 'done':
      return { type: 'done' };
    case 'error':
      return {
        type: 'error',
        error: typeof parsed.error === 'string' ? parsed.error : 'Voice mode could not process that turn. Try again.',
      };
    default:
      return null;
  }
}

export async function streamVoiceAgentEvents(
  path: string,
  payload: Record<string, unknown>,
  onEvent: (event: VoiceAgentStreamEvent) => void,
  options: PostVoiceAgentJsonOptions = {},
): Promise<void> {
  if (process.env.NODE_ENV === 'test') {
    throw new Error('Voice agent network calls are disabled in tests');
  }

  const response = await fetch(path, {
    method: 'POST',
    headers: {
      ...buildVoiceAgentHeaders(),
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(payload),
    credentials: 'include',
    signal: options.signal,
  });

  if (!response.ok) {
    throw new Error(`Voice agent request failed: ${response.status}`);
  }

  if (!response.body) {
    throw new Error('Voice agent stream did not return a body.');
  }

  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split(/\n\n/);
    buffer = frames.pop() || '';

    for (const frame of frames) {
      if (!frame.trim()) {
        continue;
      }

      let eventName = 'message';
      const dataLines: string[] = [];

      for (const line of frame.split(/\n/)) {
        if (line.startsWith('event:')) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).trim());
        }
      }

      const event = parseSseEvent(eventName, dataLines.join('\n'));
      if (event) {
        onEvent(event);
      }
    }
  }
}

export async function postVoiceAgentJson<TResponse>(
  path: string,
  payload: Record<string, unknown>,
  options: PostVoiceAgentJsonOptions = {},
): Promise<TResponse> {
  if (process.env.NODE_ENV === 'test') {
    throw new Error('Voice agent network calls are disabled in tests');
  }

  const response = await fetch(path, {
    method: 'POST',
    headers: buildVoiceAgentHeaders(),
    body: JSON.stringify(payload),
    credentials: 'include',
    signal: options.signal,
  });

  if (!response.ok) {
    throw new Error(`Voice agent request failed: ${response.status}`);
  }

  return response.json() as Promise<TResponse>;
}
