/**
 * Voice without an OpenAI key: the browser listens and speaks, and the person's own agent
 * (Claude Code, Codex) answers through `manifest bridge` on this computer.
 *
 * The bridge listens on 127.0.0.1 and answers only Manifest's pages. Chrome may ask once
 * whether Manifest may reach devices on the local network; that is this bridge.
 */
import type { LiveVoiceContext } from './liveVoice';

export const BRIDGE_URL = 'http://127.0.0.1:47821';
export const BRIDGE_COMMAND = 'manifest bridge';
/** Once, with the CLI installed: keeps the bridge running at login. */
export const BRIDGE_INSTALL_COMMAND = 'manifest bridge --install';
/**
 * Once, from nothing: installs the `manifest` CLI and starts the bridge at login, using
 * Claude Code if it is installed, else Codex (public/voice.sh, served by the app).
 */
export const VOICE_SETUP_COMMAND = 'curl -fsSL https://manifeststartup.com/voice.sh | sh';

export interface BridgeInfo {
  agent: string;
  /** The bridge's own Pipecat voice (local Whisper + Kokoro), when it runs one. */
  voice: string | null;
  /** Hanging up a turn stops the agent's answer (the person talked over it). */
  interrupt: boolean;
  /** The natural voice (Kokoro on the Apple GPU, POST /speak), e.g. "af_heart", once loaded. */
  speech: string | null;
}

export type BridgeEvent = { kind: 'say' | 'tool' | 'error'; text: string } | { kind: 'done'; text: string };

/**
 * The running bridge, or null. A bridge that isn't running fails at once (connection
 * refused), so the generous timeout only matters while Chrome asks the person whether
 * Manifest may reach this computer; it must not give up before they answer.
 */
export async function probeBridge(timeoutMs = 20000): Promise<BridgeInfo | null> {
  if (typeof fetch === 'undefined') return null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${BRIDGE_URL}/health`, { signal: controller.signal });
    if (!response.ok) return null;
    const body = (await response.json()) as {
      ok?: boolean;
      agent?: string;
      voice?: string | null;
      interrupt?: boolean;
      speech?: string | null;
    };
    const voice = typeof body.voice === 'string' && /^ws:\/\/127\.0\.0\.1:\d+$/.test(body.voice) ? body.voice : null;
    const speech = typeof body.speech === 'string' && body.speech ? body.speech : null;
    return body.ok ? { agent: body.agent || 'Your agent', voice, interrupt: Boolean(body.interrupt), speech } : null;
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

export interface RecognitionHandle {
  stop: () => void;
  pause: () => void;
  resume: () => void;
  /** Forget words still being recognised (already sent as a turn) and keep listening. */
  restart: () => void;
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
}): RecognitionHandle | null {
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
    // abort() drops pending results; onend then starts it again (wanted, not paused).
    restart: () => {
      if (wanted && !paused) recognition.abort();
    },
  };
}

/** The most natural local voice for this language: Premium/Enhanced first (no network). */
export function pickVoice(voices: SpeechSynthesisVoice[], language: string): SpeechSynthesisVoice | null {
  const lang = language.slice(0, 2) || 'en';
  const mine = voices.filter(v => v.lang.toLowerCase().startsWith(lang));
  const local = mine.filter(v => v.localService);
  return (
    local.find(v => /Premium|Enhanced|Siri/i.test(v.name)) ??
    local.find(v => /Samantha|Ava|Zoe|Allison|Natural/i.test(v.name)) ??
    local.find(v => v.default) ??
    local[0] ??
    mine[0] ??
    null
  );
}

export interface Speaker {
  /** Queue one sentence; it is spoken after the ones before it. */
  say: (text: string) => void;
  readonly speaking: boolean;
  /** What it said recently, to tell its own echo from the person talking over it. */
  readonly recent: string;
  cancel: () => void;
  /** How loud it is right now (0–1), for the orb; absent when unknown. */
  level?: () => number;
}

/**
 * Speak sentences in order with the browser's own voice. `onSpeaking` flips when speech
 * starts and when everything queued has been said; `onWord` pulses on each spoken word.
 */
export function createSpeaker(onSpeaking: (speaking: boolean) => void, onWord?: () => void): Speaker {
  let pending = 0;
  let recent: string[] = [];
  let generation = 0;
  return {
    say(text: string) {
      const utterance = new SpeechSynthesisUtterance(text);
      const chosen = pickVoice(window.speechSynthesis.getVoices(), navigator.language || 'en');
      if (chosen) utterance.voice = chosen;
      utterance.rate = 1.08;
      const mine = generation;
      const done = () => {
        if (mine !== generation) return; // cancelled
        pending = Math.max(0, pending - 1);
        if (pending === 0) onSpeaking(false);
      };
      utterance.onend = done;
      utterance.onerror = done;
      if (onWord) utterance.onboundary = () => onWord();
      recent = [...recent, text].slice(-3);
      pending += 1;
      if (pending === 1) onSpeaking(true);
      window.speechSynthesis.speak(utterance);
    },
    get speaking() {
      return pending > 0;
    },
    get recent() {
      return recent.join(' ');
    },
    cancel() {
      generation += 1;
      const was = pending > 0;
      pending = 0;
      window.speechSynthesis.cancel();
      if (was) onSpeaking(false);
    },
  };
}

const words = (text: string) =>
  text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s']/gu, ' ')
    .split(/\s+/)
    .filter(Boolean);

const STOP_WORDS = /^(stop|wait|hold on|hang on|pause|no|nope|actually|sorry|excuse me|quiet|shh+)\b/i;

/**
 * While the voice is speaking, is what the mic heard the person talking over it (true) or the
 * speaker's own sound coming back (false)? Speech through the speakers is recognised as the
 * very words being said, so text that mostly repeats them is echo. A clear "stop" / "wait",
 * or two or more words of something else, is the person.
 */
export function isBargeIn(heard: string, speaking: string): boolean {
  const said = words(heard);
  if (said.length === 0) return false;
  if (STOP_WORDS.test(heard.trim())) return true;
  if (said.length < 2) return false;
  const bot = new Set(words(speaking));
  const echoed = said.filter(word => bot.has(word)).length;
  return echoed / said.length < 0.6;
}

/** Wake the natural voice while the person is still talking (it may have been paged out). */
export function warmBridgeSpeech(): void {
  void fetch(`${BRIDGE_URL}/speak/warm`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}' }).catch(
    () => undefined,
  );
}

/**
 * Split a sentence at its pauses (, ; : — –) into pieces of at least `min` words, so the
 * natural voice can start on the first piece (Kokoro's time grows with length) while the
 * rest is made. Pauses are where the voice breathes anyway, so it sounds the same.
 */
export function speechPieces(text: string, min = 4): string[] {
  const parts = text.match(/[^,;:—–]+[,;:—–]?\s*/g) ?? [text];
  const pieces: string[] = [];
  let piece = '';
  for (const part of parts) {
    piece += part;
    if (piece.trim().split(/\s+/).length >= min) {
      pieces.push(piece.trim());
      piece = '';
    }
  }
  if (piece.trim()) {
    if (pieces.length && piece.trim().split(/\s+/).length < min) pieces[pieces.length - 1] += ` ${piece.trim()}`;
    else pieces.push(piece.trim());
  }
  return pieces.length ? pieces : [text];
}

/** Once a piece is due to play, wait no longer than this; then the browser says it. */
export const BRIDGE_SPEECH_TIMEOUT_MS = 4000;

/**
 * The natural voice: each sentence is made by Kokoro on this Mac's GPU (the bridge's
 * POST /speak, about 0.5 s) and played here. A sentence is requested the moment it arrives,
 * so the next one is ready while the current one plays. Any sentence that fails or is slow
 * is spoken by the browser's voice instead, so it never goes silent.
 */
export function createBridgeSpeaker(onSpeaking: (speaking: boolean) => void): Speaker {
  const Ctx =
    window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  const context = new Ctx();
  const analyser = context.createAnalyser();
  analyser.fftSize = 512;
  analyser.connect(context.destination);
  const samples = new Float32Array(analyser.fftSize);
  const fallback = createSpeaker(() => undefined);

  type Item = { text: string; audio: Promise<AudioBuffer | null>; abort: AbortController };
  let queue: Item[] = [];
  let current: AudioBufferSourceNode | null = null;
  let playing = false;
  let generation = 0;
  let recent: string[] = [];

  const fetchAudio = async (text: string, abort: AbortController): Promise<AudioBuffer | null> => {
    try {
      const response = await fetch(`${BRIDGE_URL}/speak`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ text }),
        signal: abort.signal,
      });
      if (!response.ok) return null;
      const rate = Number(response.headers.get('x-sample-rate')) || 24000;
      const pcm = new Int16Array(await response.arrayBuffer());
      if (pcm.length === 0) return null;
      const buffer = context.createBuffer(1, pcm.length, rate);
      const channel = buffer.getChannelData(0);
      for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 32768;
      return buffer;
    } catch {
      return null;
    }
  };

  /** The piece's audio, or null if it isn't ready this long after it's due to play. */
  const due = (item: Item): Promise<AudioBuffer | null> =>
    Promise.race([
      item.audio,
      new Promise<null>(resolve =>
        setTimeout(() => {
          item.abort.abort();
          resolve(null);
        }, BRIDGE_SPEECH_TIMEOUT_MS),
      ),
    ]);

  const finish = () => {
    playing = false;
    current = null;
    onSpeaking(false);
  };

  const playNext = async (mine: number): Promise<void> => {
    const item = queue[0];
    if (!item) return finish();
    const buffer = await due(item);
    if (mine !== generation) return;
    queue = queue.slice(1);
    if (!buffer) {
      // The natural voice couldn't say this one in time: the browser says it.
      await new Promise<void>(resolve => {
        const utterance = new SpeechSynthesisUtterance(item.text);
        const chosen = pickVoice(window.speechSynthesis.getVoices(), navigator.language || 'en');
        if (chosen) utterance.voice = chosen;
        utterance.onend = () => resolve();
        utterance.onerror = () => resolve();
        window.speechSynthesis.speak(utterance);
      });
      if (mine === generation) void playNext(mine);
      return;
    }
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(analyser);
    source.onended = () => {
      if (mine === generation) void playNext(mine);
    };
    current = source;
    source.start();
  };

  return {
    say(text: string) {
      if (context.state === 'suspended') void context.resume();
      for (const piece of speechPieces(text)) {
        const abort = new AbortController();
        queue = [...queue, { text: piece, abort, audio: fetchAudio(piece, abort) }];
      }
      recent = [...recent, text].slice(-3);
      if (!playing) {
        playing = true;
        onSpeaking(true);
        void playNext(generation);
      }
    },
    get speaking() {
      return playing;
    },
    get recent() {
      return recent.join(' ');
    },
    level() {
      if (!current) return 0;
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      for (const value of samples) sum += value * value;
      return Math.min(1, Math.sqrt(sum / samples.length) * 4);
    },
    cancel() {
      generation += 1;
      for (const item of queue) item.abort.abort();
      queue = [];
      try {
        current?.stop();
      } catch {
        // Already stopped.
      }
      fallback.cancel();
      if (playing) finish();
    },
  };
}
