/**
 * Live voice (Pipecat) — the pure parts: state, reducer, server-message handling,
 * URLs and the status probe. The hook in usePipecatVoiceSession.ts wires these to
 * the Pipecat client; keeping them pure makes the protocol easy to test.
 *
 * Protocol: backend/app/services/voice/live/bot.py (RTVI over a WebSocket).
 */

export type LiveVoicePhase =
  | 'idle'
  | 'connecting'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'ended'
  | 'error';

export type LiveVoiceErrorKind =
  | 'setup' // nothing to talk to on this computer yet: show the one-step setup
  | 'sign_in'
  | 'no_api_key'
  | 'unavailable'
  | 'origin'
  | 'microphone'
  | 'connection';

export interface LiveVoiceError {
  kind: LiveVoiceErrorKind;
  message: string;
}

export interface LiveCaption {
  id: number;
  role: 'user' | 'assistant';
  text: string;
  final: boolean;
}

export type LiveActivityStatus = 'running' | 'done' | 'failed' | 'confirm';

export interface LiveActivity {
  id: string;
  label: string;
  status: LiveActivityStatus;
  summary?: string;
}

export interface LiveVoiceState {
  phase: LiveVoicePhase;
  muted: boolean;
  userSpeaking: boolean;
  captions: LiveCaption[];
  activity: LiveActivity[];
  error: LiveVoiceError | null;
}

export const INITIAL_LIVE_VOICE_STATE: LiveVoiceState = {
  phase: 'idle',
  muted: false,
  userSpeaking: false,
  captions: [],
  activity: [],
  error: null,
};

const MAX_CAPTIONS = 40;
const MAX_ACTIVITY = 12;
export const CONFIRMATION_SUMMARY = 'Waiting for your yes';

export type LiveVoiceEvent =
  | { type: 'connecting' }
  | { type: 'ready' }
  | { type: 'disconnected' }
  | { type: 'reset' }
  | { type: 'userStarted' }
  | { type: 'userStopped' }
  | { type: 'botStarted' }
  | { type: 'botStopped' }
  | { type: 'userInput'; text: string; final: boolean }
  | { type: 'botOutput'; text: string; outputType?: string }
  | { type: 'tool'; activity: LiveActivity }
  | { type: 'muted'; muted: boolean }
  | { type: 'error'; error: LiveVoiceError };

let captionSeq = 0;
const nextCaptionId = () => {
  captionSeq += 1;
  return captionSeq;
};

function isLive(phase: LiveVoicePhase): boolean {
  return phase === 'listening' || phase === 'thinking' || phase === 'speaking';
}

function upsertUserCaption(captions: LiveCaption[], text: string, final: boolean): LiveCaption[] {
  const last = captions[captions.length - 1];
  if (last && last.role === 'user' && !last.final) {
    return [...captions.slice(0, -1), { ...last, text, final }];
  }
  return [...captions, { id: nextCaptionId(), role: 'user' as const, text, final }].slice(-MAX_CAPTIONS);
}

/**
 * Bot text arrives as sentences (before they are spoken) and, with TTS services that
 * report timing, as words (while spoken). Within one assistant turn we keep whichever
 * granularity shows up, so a caption never repeats itself.
 */
function appendAssistantText(captions: LiveCaption[], text: string, outputType?: string): LiveCaption[] {
  const clean = text.trim();
  if (!clean) return captions;
  const last = captions[captions.length - 1];
  if (last && last.role === 'assistant' && !last.final) {
    const joined = last.text ? `${last.text} ${clean}` : clean;
    return [...captions.slice(0, -1), { ...last, text: joined }];
  }
  void outputType;
  return [...captions, { id: nextCaptionId(), role: 'assistant' as const, text: clean, final: false }].slice(
    -MAX_CAPTIONS,
  );
}

function closeAssistantTurn(captions: LiveCaption[]): LiveCaption[] {
  const last = captions[captions.length - 1];
  if (last && last.role === 'assistant' && !last.final) {
    return [...captions.slice(0, -1), { ...last, final: true }];
  }
  return captions;
}

function upsertActivity(activity: LiveActivity[], next: LiveActivity): LiveActivity[] {
  const index = activity.findIndex(item => item.id === next.id);
  if (index === -1) return [...activity, next].slice(-MAX_ACTIVITY);
  const copy = activity.slice();
  copy[index] = { ...copy[index], ...next };
  return copy;
}

export function liveVoiceReducer(state: LiveVoiceState, event: LiveVoiceEvent): LiveVoiceState {
  switch (event.type) {
    case 'reset':
      return INITIAL_LIVE_VOICE_STATE;
    case 'connecting':
      return { ...INITIAL_LIVE_VOICE_STATE, muted: state.muted, phase: 'connecting' };
    case 'ready':
      return { ...state, phase: 'listening', error: null };
    case 'disconnected':
      return state.phase === 'error' ? state : { ...state, phase: 'ended', userSpeaking: false };
    case 'userStarted':
      return {
        ...state,
        userSpeaking: true,
        phase: isLive(state.phase) ? 'listening' : state.phase,
        captions: closeAssistantTurn(state.captions),
      };
    case 'userStopped':
      return {
        ...state,
        userSpeaking: false,
        phase: isLive(state.phase) && state.phase !== 'speaking' ? 'thinking' : state.phase,
      };
    case 'botStarted':
      return { ...state, phase: isLive(state.phase) ? 'speaking' : state.phase };
    case 'botStopped':
      return {
        ...state,
        phase: isLive(state.phase) ? 'listening' : state.phase,
        captions: closeAssistantTurn(state.captions),
      };
    case 'userInput': {
      const text = event.text.trim();
      if (!text) return state;
      return {
        ...state,
        captions: upsertUserCaption(closeAssistantTurn(state.captions), text, event.final),
        phase: event.final && isLive(state.phase) && state.phase !== 'speaking' ? 'thinking' : state.phase,
      };
    }
    case 'botOutput':
      return { ...state, captions: appendAssistantText(state.captions, event.text, event.outputType) };
    case 'tool':
      return { ...state, activity: upsertActivity(state.activity, event.activity) };
    case 'muted':
      return { ...state, muted: event.muted };
    case 'error':
      return { ...state, phase: 'error', userSpeaking: false, error: event.error };
    default:
      return state;
  }
}

// ---- server messages ---------------------------------------------------------------

export type LiveServerAction =
  | { kind: 'navigate'; path: string }
  | { kind: 'refresh' }
  | { kind: 'activity'; activity: LiveActivity }
  | { kind: 'end' };

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value ? value : undefined;
}

/** Map one RTVI server-message payload to what the app should do (or null to ignore). */
export function interpretServerMessage(data: unknown): LiveServerAction | null {
  if (!data || typeof data !== 'object') return null;
  const message = data as Record<string, unknown>;
  switch (message.type) {
    case 'manifest.navigate': {
      const path = resolveVoicePath(asString(message.path));
      return path ? { kind: 'navigate', path } : null;
    }
    case 'manifest.changed':
      return { kind: 'refresh' };
    case 'manifest.end':
      return { kind: 'end' };
    case 'manifest.tool': {
      const id = asString(message.id);
      if (!id) return null;
      const label = asString(message.label) ?? asString(message.name) ?? 'Working';
      const summary = asString(message.summary);
      let status: LiveActivityStatus = 'running';
      if (message.phase === 'finished') {
        if (message.needs_confirmation === true || summary === CONFIRMATION_SUMMARY) status = 'confirm';
        else status = message.ok === false ? 'failed' : 'done';
      }
      return { kind: 'activity', activity: { id, label, status, summary } };
    }
    default:
      return null;
  }
}

// ---- paths -----------------------------------------------------------------------

/**
 * A server path is used only when it is a same-origin app route (the agent sends real
 * routes such as /ideas/{id}/pitch-deck or /account#ai-key). Returns null otherwise.
 */
export function resolveVoicePath(path: string | undefined | null): string | null {
  if (!path || !path.startsWith('/') || path.startsWith('//')) return null;
  return /^\/[A-Za-z0-9/_?=#&.-]*$/.test(path) ? path : null;
}

// ---- connection -------------------------------------------------------------------

export interface LiveVoiceContext {
  path: string;
  ideaId?: string | null;
  ideaTitle?: string | null;
}

/** `agent` = Manifest's voice agent; `dictate` = speech to text only, for writing a note. */
export type LiveVoiceMode = 'agent' | 'dictate';

export function buildLiveVoiceUrl(
  location: { protocol: string; host: string },
  context: LiveVoiceContext,
  mode: LiveVoiceMode = 'agent',
): string {
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const params = new URLSearchParams({ path: context.path });
  if (mode !== 'agent') params.set('mode', mode);
  if (context.ideaId) params.set('idea_id', context.ideaId);
  if (context.ideaTitle) params.set('idea_title', context.ideaTitle);
  return `${scheme}//${location.host}/api/voice-agent/live?${params.toString()}`;
}

export interface LiveVoiceStatus {
  available: boolean;
  reason: 'no_api_key' | 'unavailable' | 'sign_in' | 'offline' | null;
  message: string | null;
}

/** The Pipecat client and its WebSocket transport, loaded once on first use. */
export type PipecatModules = [
  typeof import('@pipecat-ai/client-js'),
  typeof import('@pipecat-ai/websocket-transport'),
];
let pipecatModules: Promise<PipecatModules> | null = null;
export function loadPipecat(): Promise<PipecatModules> {
  pipecatModules ??= Promise.all([
    import('@pipecat-ai/client-js'),
    import('@pipecat-ai/websocket-transport'),
  ]).catch(error => {
    pipecatModules = null;
    throw error;
  });
  return pipecatModules;
}

const STATUS_FRESH_MS = 60_000;
let cachedStatus: { at: number; status: Promise<LiveVoiceStatus> } | null = null;

/**
 * The status, reused for a minute so opening voice costs no extra round trip. Asking
 * also makes the server start loading Pipecat, so call it as soon as voice is likely.
 */
export function liveVoiceStatus(): Promise<LiveVoiceStatus> {
  if (cachedStatus && Date.now() - cachedStatus.at < STATUS_FRESH_MS) return cachedStatus.status;
  const status = fetchLiveVoiceStatus().then(result => {
    if (!result.available && cachedStatus?.status === status) cachedStatus = null; // retry next time
    return result;
  });
  cachedStatus = { at: Date.now(), status };
  return status;
}

/** Ask the server again next time (after signing in or adding a key). */
export function forgetLiveVoiceStatus(): void {
  cachedStatus = null;
}

/** Warm everything a conversation needs (on hover/focus of a voice control). */
export function warmLiveVoice(): void {
  void loadPipecat().catch(() => undefined);
  void liveVoiceStatus();
}

/** Can live voice start? Never throws; network trouble reads as "offline". */
export async function fetchLiveVoiceStatus(signal?: AbortSignal): Promise<LiveVoiceStatus> {
  try {
    const response = await fetch('/api/voice-agent/live/status', {
      credentials: 'include',
      headers: { accept: 'application/json' },
      signal,
    });
    if (response.status === 401) {
      return { available: false, reason: 'sign_in', message: 'Sign in to talk to Manifest.' };
    }
    if (!response.ok) {
      return { available: false, reason: 'unavailable', message: null };
    }
    const body = (await response.json()) as Partial<LiveVoiceStatus>;
    const reason = body.reason === 'no_api_key' || body.reason === 'unavailable' ? body.reason : null;
    return { available: Boolean(body.available), reason, message: body.message ?? null };
  } catch {
    return { available: false, reason: 'offline', message: null };
  }
}

const CLOSE_CODE_ERRORS: Record<number, LiveVoiceError> = {
  4401: { kind: 'sign_in', message: 'Your sign-in expired. Sign in again to keep talking.' },
  4402: { kind: 'no_api_key', message: 'Add your OpenAI key in Account → AI settings to talk to Manifest.' },
  4403: { kind: 'origin', message: 'Voice only works from the Manifest app.' },
  4503: { kind: 'unavailable', message: "Voice isn't available on this server right now." },
};

/** Classify a transport error message ("… closed. Code: 4402") into a user-facing error. */
export function classifyConnectionError(message: string | undefined | null): LiveVoiceError {
  const code = Number((message ?? '').match(/Code:\s*(\d{4})/)?.[1] ?? (message ?? '').match(/\((\d{4})\)/)?.[1]);
  if (CLOSE_CODE_ERRORS[code]) return CLOSE_CODE_ERRORS[code];
  if (/permission|NotAllowedError|microphone|getUserMedia/i.test(message ?? '')) {
    return { kind: 'microphone', message: 'Allow microphone access to talk, or type instead.' };
  }
  return { kind: 'connection', message: "Couldn't reach Manifest voice. Check your connection and try again." };
}

/** Suggestions for the current page (short, spoken-style prompts). */
export function suggestionsFor(context: LiveVoiceContext): string[] {
  if (context.ideaId) return ["What's next?", 'Pitch deck', 'Partners'];
  if (context.path.startsWith('/messages')) return ["What's new?", 'Reply to the latest', 'New idea'];
  if (context.path.startsWith('/account')) return ['Signed-in apps', 'My AI spend', 'Privacy'];
  return ['New idea', 'My ideas', 'Inbox'];
}
