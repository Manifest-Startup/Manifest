/**
 * Voice without an OpenAI key: the browser listens and speaks, and the person's own agent
 * (Claude Code, Codex) answers through `manifest bridge` on this computer.
 *
 * The bridge listens on 127.0.0.1 and answers only Manifest's pages. Chrome may ask once
 * whether Manifest may reach devices on the local network; that is this bridge.
 */
import type { LiveVoiceContext } from './liveVoice';
import type { ToneCue } from './voiceProsody';

export const BRIDGE_URL = 'http://127.0.0.1:47821';
/** The same bridge over HTTPS (`manifest bridge --install` sets it up): Safari only allows this. */
export const BRIDGE_HTTPS_URL = 'https://127.0.0.1:47823';
let bridgeBase = BRIDGE_URL;
/** Where the bridge answered last (HTTPS when it can, so Safari works). */
export const bridgeUrl = () => bridgeBase;
export const BRIDGE_COMMAND = 'manifest bridge';
/** Once, with the CLI installed: keeps the bridge running at login. */
export const BRIDGE_INSTALL_COMMAND = 'manifest bridge --install';
/**
 * Once, from nothing: installs the `manifest` CLI and starts the bridge at login, using
 * Claude Code if it is installed, else Codex (public/voice.sh, served by the app).
 */
/** How many already-spoken sentences still count as its own voice (speakers lag a little). */
const RECENT_SENTENCES = 3;

export const VOICE_SETUP_COMMAND = 'curl -fsSL https://manifeststartup.com/voice.sh | sh';

/** The bridge could speak naturally here but its install lacks the voice (issue #108). */
export function naturalVoiceMissing(speechStatus?: string): boolean {
  return Boolean(speechStatus?.startsWith('natural voice not installed'));
}

export const NATURAL_VOICE_MISSING_NOTE = `The natural voice isn't on this Mac yet, so answers appear as text. To turn it on, run: ${VOICE_SETUP_COMMAND}`;

export interface BridgeInfo {
  agent: string;
  /** The bridge's own Pipecat voice (local Whisper + Kokoro), when it runs one. */
  voice: string | null;
  /** Hanging up a turn stops the agent's answer (the person talked over it). */
  interrupt: boolean;
  /** The natural voice (Kokoro on the Apple GPU, POST /speak), e.g. "af_heart", once loaded. */
  speech: string | null;
  /** "ready", "loading", "off", or what's wrong with the natural voice. */
  speechStatus?: string;
  /** False when the agent can't answer yet (e.g. Codex has no trusted project); see `problem`. */
  ready: boolean;
  /** Why it can't answer, and the next step (issue #132). */
  problem: { message: string; fix: string } | null;
  /** It answers, but something is missing, e.g. the agent isn't signed in to Manifest. */
  warning?: { message: string; fix: string } | null;
  /** Every agent set up on this computer; say "switch to Codex" to change. */
  agents: { id: string; name: string; ready: boolean }[];
}

/** The one line to show when the bridge runs but its agent can't answer yet. */
export function bridgeNotReadyMessage(bridge: BridgeInfo): string | null {
  if (bridge.ready) return null;
  const problem = bridge.problem;
  return problem ? `${problem.message} ${problem.fix}` : `${bridge.agent} can't answer yet. Run: manifest bridge --doctor`;
}

export type BridgeEvent = { kind: 'say' | 'tool' | 'error'; text: string } | { kind: 'done'; text: string };

/**
 * The running bridge, or null. A bridge that isn't running fails at once (connection
 * refused), so the generous timeout only matters while Chrome asks the person whether
 * Manifest may reach this computer; it must not give up before they answer.
 */
async function probeAt(base: string, signal: AbortSignal): Promise<BridgeInfo | null> {
  try {
    const response = await fetch(`${base}/health`, { signal });
    if (!response.ok) return null;
    const body = (await response.json()) as {
      ok?: boolean;
      agent?: string;
      voice?: string | null;
      interrupt?: boolean;
      speech?: string | null;
      speech_status?: string;
      ready?: boolean;
      problems?: { message?: unknown; fix?: unknown }[];
      warnings?: { message?: unknown; fix?: unknown }[];
      agents?: { id?: unknown; name?: unknown; ready?: unknown }[];
    };
    const voice = typeof body.voice === 'string' && /^ws:\/\/127\.0\.0\.1:\d+$/.test(body.voice) ? body.voice : null;
    const speech = typeof body.speech === 'string' && body.speech ? body.speech : null;
    const speechStatus = typeof body.speech_status === 'string' ? body.speech_status.slice(0, 300) : undefined;
    const first = Array.isArray(body.problems) ? body.problems[0] : undefined;
    const problem =
      first && typeof first.message === 'string'
        ? { message: first.message.slice(0, 400), fix: typeof first.fix === 'string' ? first.fix.slice(0, 400) : '' }
        : null;
    const note = Array.isArray(body.warnings) ? body.warnings[0] : undefined;
    const warning =
      note && typeof note.message === 'string'
        ? { message: note.message.slice(0, 400), fix: typeof note.fix === 'string' ? note.fix.slice(0, 400) : '' }
        : null;
    const agents = (Array.isArray(body.agents) ? body.agents : [])
      .filter(a => typeof a.id === 'string' && typeof a.name === 'string')
      .map(a => ({ id: String(a.id), name: String(a.name), ready: Boolean(a.ready) }));
    return body.ok
      ? {
          agent: body.agent || 'Your agent',
          voice,
          interrupt: Boolean(body.interrupt),
          speech,
          speechStatus,
          // Older bridges don't say; they were ready whenever they answered.
          ready: body.ready !== false,
          problem,
          warning,
          agents,
        }
      : null;
  } catch {
    return null; // not running, or (Safari) plain HTTP to this computer is blocked
  }
}

export async function probeBridge(timeoutMs = 20000): Promise<BridgeInfo | null> {
  if (typeof fetch === 'undefined') return null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const [secure, plain] = await Promise.all([
      probeAt(BRIDGE_HTTPS_URL, controller.signal),
      probeAt(BRIDGE_URL, controller.signal),
    ]);
    bridgeBase = secure ? BRIDGE_HTTPS_URL : BRIDGE_URL;
    return secure ?? plain;
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
  tone?: ToneCue | null,
): Promise<void> {
  const response = await fetch(`${bridgeBase}/turn`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      text,
      context: { path: context.path, idea_id: context.ideaId ?? null, idea_title: context.ideaTitle ?? null },
      // Opt-in tone of voice, read on this device: a label and fixed phrases, never audio.
      ...(tone ? { tone } : {}),
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

/** The browser can hear the person (its own speech recognition); answers use the natural voice. */
export function browserSpeechAvailable(): boolean {
  return Boolean(browserRecognition());
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
export function startRecognition(
  handlers: {
    onText: (text: string, final: boolean) => void;
    onStart?: () => void;
    onError: (message: string) => void;
  },
  /** An echo-cancelled mic (Chrome): the voice playing in this tab is removed before it is heard. */
  track?: MediaStreamTrack | null,
): RecognitionHandle | null {
  const Ctor = browserRecognition();
  if (!Ctor) return null;
  const recognition = new Ctor();
  let useTrack = Boolean(track);
  const begin = () => {
    if (useTrack && track && track.readyState === 'live') {
      try {
        (recognition.start as (t?: MediaStreamTrack) => void)(track);
        return;
      } catch (error) {
        if (!(error instanceof TypeError)) throw error;
        useTrack = false; // this browser can't take a track: its own mic, echo filtered by words
      }
    }
    recognition.start();
  };
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
        begin();
      } catch {
        // Already restarting.
      }
    }
  };
  try {
    begin();
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
        begin();
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


export interface Speaker {
  /** Queue one sentence; it is spoken after the ones before it. */
  say: (text: string) => void;
  readonly speaking: boolean;
  /** What it said recently, to tell its own echo from the person talking over it. */
  readonly recent: string;
  cancel: () => void;
  /** How loud it is right now (0–1), for the orb; absent when unknown. */
  level?: () => number;
  /** Make these short lines' audio now, so saying them later is instant (fillers). */
  preload?: (texts: string[]) => void;
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
/**
 * Just after it stopped talking, is this the tail of its own voice (recognition can deliver
 * the speakers' echo up to a second late)? Mostly its own recent words means echo.
 */
export function isEcho(heard: string, spoken: string): boolean {
  const said = words(heard);
  if (said.length === 0) return true;
  const bot = new Set(words(spoken));
  return said.filter(word => bot.has(word)).length / said.length >= 0.6;
}

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
  void fetch(`${bridgeBase}/speak/warm`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}' }).catch(
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
/** How long one piece may wait for the natural voice (loading, busy) before it is skipped. */
export const NATURAL_VOICE_WAIT_MS = 30000;

/**
 * The natural voice: each sentence is made by Kokoro on this Mac's GPU (the bridge's
 * POST /speak, about 0.5 s) and played here. A sentence is requested the moment it arrives,
 * so the next one is ready while the current one plays. A slow or failed sentence waits and
 * retries; the browser's flat voice is never used.
 */
let sharedAudio: AudioContext | null = null;

/** One audio output for the voice, made on the first click (Safari plays sound only after one). */
export function voiceAudioContext(): AudioContext | null {
  if (sharedAudio) return sharedAudio;
  if (typeof window === 'undefined') return null;
  const Ctx =
    window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctx) return null;
  sharedAudio = new Ctx();
  return sharedAudio;
}

/** Call from the click (or key) that opens voice, so its answers can be heard in every browser. */
export function primeVoiceAudio(): void {
  try {
    const context = voiceAudioContext();
    if (context && context.state === 'suspended') void context.resume();
  } catch {
    // No Web Audio here: the browser's own voice speaks instead.
  }
}

/**
 * No voice at all, only the words on screen: used when the natural voice can't run here,
 * because the browser's flat voice is never used for answers.
 */
export function createSilentSpeaker(): Speaker {
  let recent: string[] = [];
  return {
    say(text: string) {
      recent = [...recent, text].slice(-3);
    },
    speaking: false,
    get recent() {
      return recent.join(' ');
    },
    cancel() {
      // Nothing is playing.
    },
  };
}

export function createBridgeSpeaker(onSpeaking: (speaking: boolean) => void): Speaker {
  const context = voiceAudioContext() as AudioContext;
  const analyser = context.createAnalyser();
  analyser.fftSize = 512;
  analyser.connect(context.destination);
  const samples = new Float32Array(analyser.fftSize);

  type Item = { text: string; audio: Promise<AudioBuffer | null>; abort: AbortController };
  let queue: Item[] = [];
  let current: AudioBufferSourceNode | null = null;
  let playing = false;
  let generation = 0;
  let said: string[] = []; // pieces already played (or playing), the last few
  let sayingNow: string | null = null;
  // Short lines made ahead of time ("One moment."): they play the instant they're needed.
  const ready = new Map<string, Promise<AudioBuffer | null>>();

  const fetchOnce = async (text: string, abort: AbortController): Promise<AudioBuffer | null> => {
    try {
      const response = await fetch(`${bridgeBase}/speak`, {
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

  /**
   * The natural voice, always: while it is still loading, busy or briefly unreachable, wait
   * and ask again rather than switch to the browser's flat voice. Only after a long wait is
   * the piece left unspoken (its words are on screen).
   */
  const fetchAudio = async (text: string, abort: AbortController): Promise<AudioBuffer | null> => {
    const deadline = Date.now() + NATURAL_VOICE_WAIT_MS;
    for (let attempt = 0; ; attempt++) {
      const buffer = await fetchOnce(text, abort);
      if (buffer || abort.signal.aborted || Date.now() >= deadline) return buffer;
      await new Promise(resolve => setTimeout(resolve, Math.min(2000, 250 * 2 ** attempt)));
    }
  };

  const due = (item: Item): Promise<AudioBuffer | null> => item.audio;

  const finish = () => {
    if (sayingNow) said = [...said, sayingNow].slice(-RECENT_SENTENCES * 2);
    sayingNow = null;
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
    if (sayingNow) said = [...said, sayingNow].slice(-RECENT_SENTENCES * 2);
    sayingNow = item.text;
    if (!buffer) {
      // Never the browser's voice: the words are on screen, and the next piece goes on.
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
        const made = ready.get(piece);
        queue = [...queue, { text: piece, abort, audio: made ?? fetchAudio(piece, abort) }];
      }
      if (!playing) {
        playing = true;
        onSpeaking(true);
        void playNext(generation);
      }
    },
    preload(texts: string[]) {
      for (const text of texts) {
        if (!ready.has(text)) ready.set(text, fetchAudio(text, new AbortController()));
      }
    },
    get speaking() {
      return playing;
    },
    get recent() {
      // Everything it may still be heard saying: recent pieces, the one playing, and the
      // queue. Claude streams sentences faster than they're spoken, so the queue can be
      // several sentences ahead of the speakers.
      return [...said, ...(sayingNow ? [sayingNow] : []), ...queue.map(item => item.text)].join(' ');
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
      if (playing) finish();
    },
  };
}
