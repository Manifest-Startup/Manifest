import { VOICE_AUDIO_CONSTRAINTS } from './useVoiceIdeaSession';

export interface VoiceMicResource {
  stream: MediaStream;
  context: AudioContext;
}

interface SharedMic {
  stream: MediaStream;
  context: AudioContext;
  refcount: number;
}

let shared: SharedMic | null = null;
let acquiring: Promise<VoiceMicResource> | null = null;

function currentShared(): SharedMic | null {
  return shared;
}

function getAudioContextConstructor(): typeof AudioContext | null {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.AudioContext;
}

async function buildShared(): Promise<SharedMic> {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    throw new Error('voiceMicStream: getUserMedia unavailable');
  }
  const Ctor = getAudioContextConstructor();
  if (!Ctor) {
    throw new Error('voiceMicStream: AudioContext unavailable');
  }

  const stream = await navigator.mediaDevices.getUserMedia({ audio: VOICE_AUDIO_CONSTRAINTS });
  const context = new Ctor();
  if (context.state === 'suspended') {
    try {
      await context.resume();
    } catch {
      /* ignore — caller will see analyser fail to read silently */
    }
  }
  return { stream, context, refcount: 0 };
}

/**
 * Refcounted singleton that shares one MediaStream + AudioContext across the
 * voice agent's monitoring consumers (orb analyser, barge-in detector). The
 * primary listener path (MediaRecorder fallback) keeps its own stream — this
 * pool is only for amplitude/visualisation monitors.
 *
 * Must first be called inside a user-gesture handler so Safari resumes the
 * AudioContext.
 */
export async function acquireVoiceMic(): Promise<VoiceMicResource> {
  if (shared) {
    shared.refcount += 1;
    return { stream: shared.stream, context: shared.context };
  }
  if (!acquiring) {
    acquiring = (async () => {
      try {
        const next = await buildShared();
        next.refcount = 1;
        shared = next;
        return { stream: next.stream, context: next.context };
      } finally {
        acquiring = null;
      }
    })();
  } else {
    const resource = await acquiring;
    // `shared` is reassigned while awaiting; re-read it so TypeScript does not
    // keep the pre-await `null` narrowing.
    const sharedAfterAcquire = currentShared();
    if (sharedAfterAcquire) {
      sharedAfterAcquire.refcount += 1;
    }
    return resource;
  }
  return acquiring;
}

export function releaseVoiceMic(): void {
  if (!shared) {
    return;
  }
  shared.refcount -= 1;
  if (shared.refcount > 0) {
    return;
  }
  const { stream, context } = shared;
  shared = null;
  try {
    stream.getTracks().forEach(track => track.stop());
  } catch {
    /* ignore */
  }
  if (typeof context.close === 'function') {
    void context.close();
  }
}

/** Test-only reset. Not exported in production paths. */
export function __resetVoiceMicForTests(): void {
  shared = null;
  acquiring = null;
}
