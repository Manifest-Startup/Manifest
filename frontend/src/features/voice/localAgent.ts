/**
 * Voice without an OpenAI key: the browser listens and speaks, and the person's own agent
 * (Claude Code, Codex) answers through `manifest bridge` on this computer.
 *
 * The bridge listens on 127.0.0.1 and answers only Manifest's pages. Chrome may ask once
 * whether Manifest may reach devices on the local network; that is this bridge.
 */
import type { LiveVoiceContext } from './liveVoice';

export const BRIDGE_URL = 'http://127.0.0.1:47821';
export const BRIDGE_COMMAND = 'manifest bridge --agent claude';

export interface BridgeInfo {
  agent: string;
}

export type BridgeEvent = { kind: 'say' | 'tool' | 'error'; text: string } | { kind: 'done'; text: string };

/** The running bridge, or null. Quick: never holds up opening voice for long. */
export async function probeBridge(timeoutMs = 700): Promise<BridgeInfo | null> {
  if (typeof fetch === 'undefined') return null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${BRIDGE_URL}/health`, { signal: controller.signal });
    if (!response.ok) return null;
    const body = (await response.json()) as { ok?: boolean; agent?: string };
    return body.ok ? { agent: body.agent || 'Your agent' } : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/** Send one turn; `onEvent` gets each spoken sentence and action as the agent works. */
export async function runBridgeTurn(
  text: string,
  context: LiveVoiceContext,
  onEvent: (event: BridgeEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${BRIDGE_URL}/turn`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      text,
      context: { path: context.path, idea_id: context.ideaId ?? null, idea_title: context.ideaTitle ?? null },
    }),
    signal,
  });
  if (!response.ok || !response.body) throw new Error(`bridge ${response.status}`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = '';
  for (;;) {
    const { done, value } = await reader.read();
    buffered += decoder.decode(value, { stream: !done });
    let newline = buffered.indexOf('\n');
    while (newline >= 0) {
      const line = buffered.slice(0, newline).trim();
      buffered = buffered.slice(newline + 1);
      if (line) {
        try {
          onEvent(JSON.parse(line) as BridgeEvent);
        } catch {
          // A partial or foreign line: skip it.
        }
      }
      newline = buffered.indexOf('\n');
    }
    if (done) return;
  }
}

// ---- the browser's own speech ----------------------------------------------------------

type RecognitionCtor = new () => SpeechRecognition;

export function browserRecognition(): RecognitionCtor | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function browserSpeechAvailable(): boolean {
  return Boolean(browserRecognition()) && typeof window !== 'undefined' && 'speechSynthesis' in window;
}

/**
 * Continuous recognition that keeps itself going (browsers stop after a pause or a minute)
 * until `stop()`. `onText(text, final)`: the words heard so far in the current sentence,
 * then the final sentence.
 */
export function startRecognition(handlers: {
  onText: (text: string, final: boolean) => void;
  onStart?: () => void;
  onError: (message: string) => void;
}): { stop: () => void; pause: () => void; resume: () => void } | null {
  const Ctor = browserRecognition();
  if (!Ctor) return null;
  const recognition = new Ctor();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = (typeof navigator !== 'undefined' && navigator.language) || 'en-US';
  let wanted = true;
  let paused = false;
  let started = false;

  recognition.onresult = (event: SpeechRecognitionEvent) => {
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      const text = result[0]?.transcript ?? '';
      if (result.isFinal) handlers.onText(text, true);
      else interim += text;
    }
    if (interim) handlers.onText(interim, false);
  };
  recognition.onstart = () => {
    if (!started) {
      started = true;
      handlers.onStart?.();
    }
  };
  recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
    if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
      wanted = false;
      handlers.onError('Allow microphone access to talk.');
    } else if (event.error === 'network') {
      wanted = false;
      handlers.onError("This browser's speech recognition needs a connection.");
    }
  };
  recognition.onend = () => {
    if (wanted && !paused) {
      try {
        recognition.start();
      } catch {
        // Already restarting.
      }
    }
  };
  try {
    recognition.start();
  } catch {
    return null;
  }
  return {
    stop: () => {
      wanted = false;
      recognition.abort();
    },
    pause: () => {
      paused = true;
      recognition.abort();
    },
    resume: () => {
      if (!wanted || !paused) return;
      paused = false;
      try {
        recognition.start();
      } catch {
        // Already running.
      }
    },
  };
}

/** Speak sentences in order with the browser's own voice; `onIdle` once all are spoken. */
export function createSpeaker(onSpeaking: (speaking: boolean) => void) {
  let pending = 0;
  const voice = () => {
    const voices = window.speechSynthesis.getVoices();
    const lang = navigator.language?.slice(0, 2) || 'en';
    return (
      voices.find(v => v.lang.startsWith(lang) && /Samantha|Siri|Natural|Google/i.test(v.name)) ??
      voices.find(v => v.lang.startsWith(lang)) ??
      null
    );
  };
  return {
    say(text: string) {
      const utterance = new SpeechSynthesisUtterance(text);
      const chosen = voice();
      if (chosen) utterance.voice = chosen;
      utterance.rate = 1.05;
      const done = () => {
        pending = Math.max(0, pending - 1);
        if (pending === 0) onSpeaking(false);
      };
      utterance.onend = done;
      utterance.onerror = done;
      pending += 1;
      if (pending === 1) onSpeaking(true);
      window.speechSynthesis.speak(utterance);
    },
    get speaking() {
      return pending > 0;
    },
    cancel() {
      pending = 0;
      window.speechSynthesis.cancel();
      onSpeaking(false);
    },
  };
}
