import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useReactiveVar } from '@apollo/client/react';
import { useLocation, useNavigate } from 'react-router-dom';

import { CREATE_IDEA, GET_IDEA_CORE, GET_IDEAS, UPDATE_IDEA } from '../core/apollo/queries';
import { sidebarVar, userVar } from '../core/apollo/localState';
import { createLogger } from '../core/logError';
import {
  postVoiceAgentJson,
  streamVoiceAgentEvents,
  VoiceAgentProcessResponse,
  VoiceAgentResponse,
  VoiceAgentStartResponse,
  VoiceAgentStreamEvent,
  VoiceAgentTranscribeResponse,
  VoiceAgentTtsResponse,
  VoiceConversationMessage,
} from './voiceAgentApi';
import { buildDraftIdeaTitle, buildMinimalVoiceNoteHtml, mergeVoiceNoteSection } from './voiceNote';
import { startVoiceBargeInMonitor } from './voiceBargeInMonitor';
import { acquireVoiceMic, releaseVoiceMic } from './voiceMicStream';
import { extractSpeakableChunks } from './sentenceChunker';
import { coalesceSpeechSegments } from './speechPlaybackMerge';
import { useVoiceAppCommands } from './useVoiceAppCommands';

/** Streaming: prefer longer clauses before cutting so TTS fires fewer times (smoother voice). */
const VOICE_STREAM_CHUNK_MAX = 400;
/**
 * The very first spoken segment of a reply uses a tighter cap so the opening
 * clause is synthesized and starts playing almost immediately (low
 * time-to-first-audio). Later segments use the larger window above so the rest
 * of the reply stays smooth. Kept standalone (not coalesced) for the same reason.
 */
const FIRST_SPEECH_CHUNK_MAX = 140;

/** Keep the first segment standalone (fast first audio); coalesce the rest for smoothness. */
function withFastFirstSegment(chunks: string[]): string[] {
  const cleaned = chunks.map(chunk => chunk.trim()).filter(Boolean);
  if (cleaned.length <= 1) {
    return coalesceSpeechSegments(cleaned);
  }
  return [cleaned[0], ...coalesceSpeechSegments(cleaned.slice(1))];
}

const logger = createLogger('useVoiceIdeaSession');

/** Shared mic constraints for voice capture and barge-in (browser AEC). */
export const VOICE_AUDIO_CONSTRAINTS: MediaTrackConstraints = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
};

const VOICE_NOTE_SAVE_WARNING =
  'Could not save your voice note to the idea. You can keep talking — try again from the workspace.';

const BROWSER_FALLBACK_WARNING =
  'Natural AI voice is unavailable in this environment. Using the browser voice fallback.';
const MICROPHONE_PERMISSION_ERROR =
  'Manifest Voice needs microphone access. Allow the microphone in your browser and system settings, then try again.';
const MICROPHONE_UNAVAILABLE_ERROR =
  'Manifest Voice could not find a microphone. Connect a mic and try again.';
const MICROPHONE_BUSY_ERROR =
  'Your microphone is busy in another app. Close that app and try again.';
const RECORDER_FALLBACK_WARNING =
  'Live browser speech recognition is unavailable here. Manifest is recording your answer and will transcribe it when you tap Stop listening.';
const RECORDER_FALLBACK_ERROR =
  'This browser cannot record microphone audio for transcription. Use Chrome, Edge, or another browser with microphone recording support.';
const PROFESSIONAL_VOICE_INSTRUCTIONS =
  'Speak in a warm, female-presenting voice like a capable executive assistant: pleasant, professional, and clear. Calm steady pace, crisp sentences, natural intonation—no slang, filler, or canned enthusiasm.';

const QUALIFIED_BUILD_PROMPT_SUFFIX =
  'Want to start building next? Say generate pitch deck, generate P R D, run background tasks, or open integrations to connect GitHub.';
const SPEECH_RECOGNITION_HINTS = [
  'SaaS',
  'AI',
  'B2B',
  'B2C',
  'go to market',
  'founder',
  'MVP',
  'startup',
  'customer pain',
  'business model',
  'distribution',
  'differentiation',
];

export interface VoiceSessionState {
  isActive: boolean;
  isPaused?: boolean;
  isListening: boolean;
  isSpeaking: boolean;
  isProcessing: boolean;
  error: string | null;
  voiceWarning: string | null;
  voiceMode: 'ai' | 'browser' | null;
  currentResponse: VoiceAgentResponse | null;
  currentMessage: string;
  interimTranscript: string;
  isQualified: boolean;
  activeIdeaId: string | null;
  /** Mirror of conversationRef for transcript UI (user + assistant turns). */
  conversationMessages: VoiceConversationMessage[];
}

declare global {
  interface Window {
    SpeechRecognition: typeof SpeechRecognition;
    webkitSpeechRecognition: typeof SpeechRecognition;
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onloadend = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      const [, base64 = ''] = result.split(',', 2);
      if (base64) {
        resolve(base64);
        return;
      }

      reject(new Error('Unable to encode recorded audio.'));
    };

    reader.onerror = () => {
      reject(reader.error || new Error('Unable to read recorded audio.'));
    };

    reader.readAsDataURL(blob);
  });
}

function guessAudioFilename(mimeType?: string | null): string {
  if (!mimeType) {
    return 'voice-input.webm';
  }

  if (mimeType.includes('ogg')) {
    return 'voice-input.ogg';
  }

  if (mimeType.includes('mp4') || mimeType.includes('m4a')) {
    return 'voice-input.m4a';
  }

  if (mimeType.includes('wav')) {
    return 'voice-input.wav';
  }

  return 'voice-input.webm';
}

function buildLocalGreeting(_hasIdeaContext: boolean): VoiceAgentResponse {
  return {
    message: '',
    is_qualified: false,
    summary: null,
    suggested_title: null,
    transcript: null,
    voice_note_html: null,
    covered_topics: [],
    missing_topics: ['problem', 'target_customer', 'solution', 'differentiation', 'go_to_market', 'business_model', 'product_scope'],
    qualification_confidence: 0.05,
    context: {},
  };
}

const LANDING_LOCAL_QUESTION_ONE =
  "Hi, welcome to Manifest—I'm glad you're here. However you'd describe yourself today, I'd love to hear it in a short phrase—are you mostly building, exploring opportunities, or here another way?";

export interface UseVoiceIdeaSessionOptions {
  landingOnboarding?: boolean;
}

export function useVoiceIdeaSession(options?: UseVoiceIdeaSessionOptions) {
  const landingOnboarding = Boolean(options?.landingOnboarding);
  const location = useLocation();
  const navigate = useNavigate();
  const { currentIdeaId } = useReactiveVar(sidebarVar);
  const { isGuest } = useReactiveVar(userVar);
  /** Backend requires onboarding_mode with landing_onboarding; guests are always onboarding. */
  const voiceApiOnboarding = Boolean(isGuest) || landingOnboarding;
  const routeIdeaId = location.pathname.match(/^\/ideas\/([^/]+)/)?.[1] || null;

  const [state, setState] = useState<VoiceSessionState>({
    isActive: false,
    isListening: false,
    isSpeaking: false,
    isProcessing: false,
    error: null,
    voiceWarning: null,
    voiceMode: null,
    currentResponse: null,
    currentMessage: '',
    interimTranscript: '',
    isQualified: false,
    activeIdeaId: null,
    conversationMessages: [],
  });

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recordedChunksRef = useRef<BlobPart[]>([]);
  const conversationRef = useRef<VoiceConversationMessage[]>([]);
  const ideaDescriptionRef = useRef<string | null>(null);
  const lastSavedDescriptionRef = useRef<string | null>(null);
  const sessionActiveRef = useRef(false);
  const activeAudioUrlRef = useRef<string | null>(null);
  const discardRecorderResultRef = useRef(false);
  const forceRecorderFallbackRef = useRef(false);
  const processAbortRef = useRef<AbortController | null>(null);
  const ttsAbortRef = useRef<AbortController | null>(null);
  const ttsPrefetchAbortRef = useRef<AbortController | null>(null);
  type TtsPrefetchedBundle = { text: string; audioUrl: string | null; fallbackToBrowser: boolean };
  const ttsPrefetchedRef = useRef<TtsPrefetchedBundle | null>(null);
  const speechQueueRef = useRef<string[]>([]);
  const speechQueueBusyRef = useRef(false);
  const speechQueuePendingRef = useRef(false);
  const speechQueueOnCompleteRef = useRef<(() => void) | null>(null);
  const streamStructuredResponseRef = useRef<VoiceAgentResponse | null>(null);
  const startListeningRef = useRef<() => void>(() => undefined);
  const processUserTurnRef = useRef<(userMessage: string) => Promise<void>>(async () => undefined);
  const contextualIdeaIdRef = useRef<string | null>(null);
  const microphoneReadyRef = useRef(false);
  const startSessionRequestIdRef = useRef(0);
  const voicePlaceholderCreatedRef = useRef(false);
  const prevVoiceQualifiedRef = useRef(false);
  const interruptAndStartListeningRef = useRef<() => void>(() => undefined);
  const voiceIdeaContextRef = useRef({
    activeIdeaId: null as string | null,
    currentIdeaId: null as string | null,
    routeIdeaId: null as string | null,
    contextualIdeaId: null as string | null,
  });

  const contextualIdeaId = state.activeIdeaId || currentIdeaId || routeIdeaId || null;

  useEffect(() => {
    voiceIdeaContextRef.current = {
      activeIdeaId: state.activeIdeaId,
      currentIdeaId,
      routeIdeaId,
      contextualIdeaId,
    };
  }, [contextualIdeaId, currentIdeaId, routeIdeaId, state.activeIdeaId]);

  useEffect(() => {
    contextualIdeaIdRef.current = contextualIdeaId;
  }, [contextualIdeaId]);

  const { data: ideaData } = useQuery(GET_IDEA_CORE, {
    variables: { ideaId: (routeIdeaId || currentIdeaId) as string },
    skip: !(routeIdeaId || currentIdeaId),
    fetchPolicy: 'cache-first',
  });

  useEffect(() => {
    const description = ideaData?.idea?.description;
    const matchedIdeaId = routeIdeaId || currentIdeaId;
    if (typeof description === 'string' && matchedIdeaId && contextualIdeaId === matchedIdeaId) {
      ideaDescriptionRef.current = description;
      lastSavedDescriptionRef.current = description;
    }
  }, [contextualIdeaId, currentIdeaId, ideaData?.idea?.description, routeIdeaId]);

  const [createIdea] = useMutation(CREATE_IDEA, {
    refetchQueries: [{ query: GET_IDEAS }],
    awaitRefetchQueries: true,
  });
  const [updateIdea] = useMutation(UPDATE_IDEA);
  const { executeCommand } = useVoiceAppCommands();

  const syncIdeaSelection = useCallback((ideaId: string) => {
    const currentSidebar = sidebarVar();
    const allIdeaIds = currentSidebar.allIdeaIds.includes(ideaId)
      ? currentSidebar.allIdeaIds
      : [ideaId, ...currentSidebar.allIdeaIds];

    sidebarVar({
      ...currentSidebar,
      currentIdeaId: ideaId,
      allIdeaIds,
    });
    contextualIdeaIdRef.current = ideaId;
  }, []);

  const resetAudioPlayback = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.onended = null;
      audioRef.current.onerror = null;

      if (process.env.NODE_ENV !== 'test') {
        try {
          audioRef.current.pause();
        } catch (error) {
          logger.debug('Audio pause unavailable in this environment', error);
        }
      }

      audioRef.current.src = '';
    }

    if (activeAudioUrlRef.current) {
      URL.revokeObjectURL(activeAudioUrlRef.current);
      activeAudioUrlRef.current = null;
    }
  }, []);

  const revokePrefetchedAudio = useCallback(() => {
    const bundle = ttsPrefetchedRef.current;
    if (bundle?.audioUrl) {
      URL.revokeObjectURL(bundle.audioUrl);
    }
    ttsPrefetchedRef.current = null;
  }, []);

  const schedulePrefetchNextSpeechSegment = useCallback(() => {
    ttsPrefetchAbortRef.current?.abort();
    ttsPrefetchAbortRef.current = null;

    const nextRaw = speechQueueRef.current[0];
    const nextText = nextRaw?.trim() ?? '';
    if (!nextText) {
      return;
    }

    const existing = ttsPrefetchedRef.current;
    if (existing?.text === nextText && existing.audioUrl) {
      return;
    }

    revokePrefetchedAudio();

    const controller = new AbortController();
    ttsPrefetchAbortRef.current = controller;

    void (async () => {
      try {
        const data = await postVoiceAgentJson<VoiceAgentTtsResponse>(
          '/api/voice-agent/tts',
          {
            text: nextText,
            instructions: PROFESSIONAL_VOICE_INSTRUCTIONS,
          },
          { signal: controller.signal },
        );

        if (controller.signal.aborted) {
          return;
        }

        if (data.audio_base64) {
          const audioBlob = await fetch(`data:audio/mp3;base64,${data.audio_base64}`).then(response => response.blob());
          if (controller.signal.aborted) {
            return;
          }
          const audioUrl = URL.createObjectURL(audioBlob);
          ttsPrefetchedRef.current = { text: nextText, audioUrl, fallbackToBrowser: Boolean(data.fallback_to_browser) };
          return;
        }

        ttsPrefetchedRef.current = { text: nextText, audioUrl: null, fallbackToBrowser: true };
      } catch (error) {
        if (isAbortError(error)) {
          return;
        }
        logger.log('Voice TTS prefetch failed', error);
        if (!controller.signal.aborted) {
          ttsPrefetchedRef.current = { text: nextText, audioUrl: null, fallbackToBrowser: true };
        }
      } finally {
        if (ttsPrefetchAbortRef.current === controller) {
          ttsPrefetchAbortRef.current = null;
        }
      }
    })();
  }, [revokePrefetchedAudio]);

  const maybeResumeListeningAfterSpeech = useCallback(() => {
    const response = streamStructuredResponseRef.current;
    if (!response || speechQueuePendingRef.current || speechQueueBusyRef.current || speechQueueRef.current.length > 0) {
      return;
    }

    streamStructuredResponseRef.current = null;
    if (response.landing_complete) {
      return;
    }
    if (!response.is_qualified && sessionActiveRef.current) {
      startListeningRef.current();
    }
  }, []);

  const maybeCompleteSpeechQueue = useCallback((cancelled = false) => {
    if (speechQueuePendingRef.current || speechQueueBusyRef.current || speechQueueRef.current.length > 0) {
      return;
    }

    setState(prev => ({ ...prev, isSpeaking: false }));
    const onComplete = speechQueueOnCompleteRef.current;
    speechQueueOnCompleteRef.current = null;

    if (!cancelled) {
      onComplete?.();
      maybeResumeListeningAfterSpeech();
    }
  }, [maybeResumeListeningAfterSpeech]);

  const playSpeechSegment = useCallback(
    async (text: string) => {
      const spokenText = text.trim();
      if (!spokenText) {
        return;
      }

      if (ttsPrefetchedRef.current && ttsPrefetchedRef.current.text !== spokenText) {
        revokePrefetchedAudio();
      }
      ttsPrefetchAbortRef.current?.abort();
      ttsPrefetchAbortRef.current = null;

      setState(prev => ({ ...prev, isSpeaking: true, voiceWarning: null, interimTranscript: '' }));

      const controller = new AbortController();
      ttsAbortRef.current = controller;

      const prefetchBundle = ttsPrefetchedRef.current;
      const prefetchMatches = prefetchBundle?.text === spokenText;
      if (prefetchMatches && prefetchBundle) {
        ttsPrefetchedRef.current = null;
      }

      try {
        if (prefetchMatches && prefetchBundle?.audioUrl && audioRef.current) {
          setState(prev => ({ ...prev, voiceMode: 'ai', voiceWarning: null }));

          activeAudioUrlRef.current = prefetchBundle.audioUrl;
          audioRef.current.src = prefetchBundle.audioUrl;

          await new Promise<void>((resolve, reject) => {
            if (!audioRef.current) {
              resolve();
              return;
            }

            audioRef.current.onended = () => {
              resetAudioPlayback();
              resolve();
            };
            audioRef.current.onerror = () => {
              resetAudioPlayback();
              resolve();
            };

            void audioRef.current.play().catch(reject);
          });
          return;
        }

        if (prefetchMatches && prefetchBundle && !prefetchBundle.audioUrl && prefetchBundle.fallbackToBrowser) {
          setState(prev => ({
            ...prev,
            voiceMode: 'browser',
            voiceWarning: BROWSER_FALLBACK_WARNING,
          }));
        } else {
          const data = await postVoiceAgentJson<VoiceAgentTtsResponse>(
            '/api/voice-agent/tts',
            {
              text: spokenText,
              instructions: PROFESSIONAL_VOICE_INSTRUCTIONS,
            },
            { signal: controller.signal },
          );

          if (controller.signal.aborted) {
            throw new DOMException('Speech playback aborted', 'AbortError');
          }

          if (data.audio_base64 && audioRef.current) {
            setState(prev => ({ ...prev, voiceMode: 'ai', voiceWarning: null }));

            const audioBlob = await fetch(`data:audio/mp3;base64,${data.audio_base64}`).then(response => response.blob());
            if (controller.signal.aborted) {
              throw new DOMException('Speech playback aborted', 'AbortError');
            }

            const audioUrl = URL.createObjectURL(audioBlob);
            activeAudioUrlRef.current = audioUrl;
            audioRef.current.src = audioUrl;

            await new Promise<void>((resolve, reject) => {
              if (!audioRef.current) {
                resolve();
                return;
              }

              audioRef.current.onended = () => {
                resetAudioPlayback();
                resolve();
              };
              audioRef.current.onerror = () => {
                resetAudioPlayback();
                resolve();
              };

              void audioRef.current.play().catch(reject);
            });
            return;
          }

          if (data.fallback_to_browser) {
            setState(prev => ({
              ...prev,
              voiceMode: 'browser',
              voiceWarning: BROWSER_FALLBACK_WARNING,
            }));
          }
        }
      } catch (error) {
        if (isAbortError(error)) {
          throw error;
        }

        logger.log('OpenAI TTS unavailable, falling back to browser speech synthesis', error);
        setState(prev => ({
          ...prev,
          voiceMode: 'browser',
          voiceWarning: BROWSER_FALLBACK_WARNING,
        }));
      } finally {
        if (ttsAbortRef.current === controller) {
          ttsAbortRef.current = null;
        }
      }

      if ('speechSynthesis' in window) {
        if (controller.signal.aborted) {
          throw new DOMException('Speech playback aborted', 'AbortError');
        }

        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(spokenText);
        utterance.rate = 0.98;
        utterance.pitch = 1;
        utterance.volume = 1;

        const voices = window.speechSynthesis.getVoices() || [];
        const preferredVoice = [...voices]
          .filter(voice => voice.lang.toLowerCase().startsWith('en'))
          .sort((left, right) => {
            const score = (voice: SpeechSynthesisVoice) => {
              const name = voice.name.toLowerCase();
              let value = 0;
              if (name.includes('premium') || name.includes('enhanced')) value += 5;
              if (name.includes('natural') || name.includes('neural')) value += 4;
              if (/\bfemale\b/.test(name) || /\bwoman\b/.test(name)) value += 6;
              const femaleNameHints = [
                'samantha',
                'karen',
                'moira',
                'fiona',
                'victoria',
                'serena',
                'ava',
                'zira',
                'aria',
                'jenny',
                'sonia',
                'amy',
                'joanna',
                'ivy',
                'kimberly',
                'salli',
                'nicole',
              ];
              for (const hint of femaleNameHints) {
                if (name.includes(hint)) value += 6;
              }
              if (/\bmale\b/.test(name) && !/\bfemale\b/.test(name)) value -= 4;
              const maleNameHints = ['daniel', 'fred', 'david', 'mark', 'thomas', 'arthur', 'jorge', 'diego'];
              for (const hint of maleNameHints) {
                if (name.includes(hint)) value -= 4;
              }
              if (name.includes('google') || name.includes('microsoft')) value += 2;
              return value;
            };

            return score(right) - score(left);
          })[0];

        if (preferredVoice) {
          utterance.voice = preferredVoice;
        }

        await new Promise<void>(resolve => {
          utterance.onend = () => resolve();
          utterance.onerror = () => resolve();
          window.speechSynthesis.speak(utterance);
        });
      }
    },
    [resetAudioPlayback, revokePrefetchedAudio],
  );

  const runSpeechQueue = useCallback(() => {
    if (speechQueueBusyRef.current) {
      return;
    }

    const nextSegment = speechQueueRef.current.shift();
    if (!nextSegment) {
      maybeCompleteSpeechQueue();
      return;
    }

    speechQueueBusyRef.current = true;
    void (async () => {
      try {
        await playSpeechSegment(nextSegment);
      } catch (error) {
        if (!isAbortError(error)) {
          logger.log('Voice chunk playback failed', error);
        }
      } finally {
        speechQueueBusyRef.current = false;
        schedulePrefetchNextSpeechSegment();
        if (speechQueueRef.current.length > 0) {
          runSpeechQueue();
        } else {
          maybeCompleteSpeechQueue();
        }
      }
    })();
  }, [maybeCompleteSpeechQueue, playSpeechSegment, schedulePrefetchNextSpeechSegment]);

  const enqueueSpeechSegments = useCallback(
    (segments: string[]) => {
      const cleanedSegments = segments.map(segment => segment.trim()).filter(Boolean);
      if (!cleanedSegments.length) {
        return;
      }

      speechQueueRef.current.push(...cleanedSegments);
      setState(prev => ({ ...prev, isSpeaking: true, voiceWarning: null, interimTranscript: '' }));
      schedulePrefetchNextSpeechSegment();
      runSpeechQueue();
    },
    [runSpeechQueue, schedulePrefetchNextSpeechSegment],
  );

  const cancelSpeechOutput = useCallback(() => {
    speechQueueRef.current = [];
    speechQueueBusyRef.current = false;
    speechQueuePendingRef.current = false;
    speechQueueOnCompleteRef.current = null;
    streamStructuredResponseRef.current = null;
    ttsPrefetchAbortRef.current?.abort();
    ttsPrefetchAbortRef.current = null;
    revokePrefetchedAudio();
    ttsAbortRef.current?.abort();
    ttsAbortRef.current = null;
    window.speechSynthesis?.cancel();
    resetAudioPlayback();
    setState(prev => ({ ...prev, isSpeaking: false }));
  }, [resetAudioPlayback, revokePrefetchedAudio]);

  const abortProcessing = useCallback(() => {
    processAbortRef.current?.abort();
    processAbortRef.current = null;
    setState(prev => ({ ...prev, isProcessing: false }));
  }, []);

  const stopMediaTracks = useCallback(() => {
    mediaStreamRef.current?.getTracks().forEach(track => track.stop());
    mediaStreamRef.current = null;
  }, []);

  const abortListeningCapture = useCallback(() => {
    discardRecorderResultRef.current = true;

    if (recognitionRef.current) {
      recognitionRef.current.abort?.();
      recognitionRef.current = null;
    }

    const mediaRecorder = mediaRecorderRef.current;
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
    } else {
      mediaRecorderRef.current = null;
      recordedChunksRef.current = [];
      stopMediaTracks();
    }

    setState(prev => ({ ...prev, isListening: false, interimTranscript: '' }));
  }, [stopMediaTracks]);

  const stopListening = useCallback(() => {
    discardRecorderResultRef.current = false;

    const mediaRecorder = mediaRecorderRef.current;
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
    } else {
      recognitionRef.current?.stop?.();
    }

    setState(prev => ({ ...prev, isListening: false, interimTranscript: '' }));
  }, []);

  const ensureMicrophoneAccess = useCallback(async (): Promise<boolean> => {
    if (microphoneReadyRef.current || typeof navigator === 'undefined') {
      return true;
    }

    const permissions = (navigator as Navigator & {
      permissions?: { query?: (descriptor: PermissionDescriptor) => Promise<PermissionStatus> };
    }).permissions;

    if (permissions?.query) {
      try {
        const permissionStatus = await permissions.query({ name: 'microphone' as PermissionName });
        if (permissionStatus.state === 'granted') {
          microphoneReadyRef.current = true;
          return true;
        }

        if (permissionStatus.state === 'denied') {
          setState(prev => ({
            ...prev,
            error: MICROPHONE_PERMISSION_ERROR,
            isListening: false,
            interimTranscript: '',
          }));
          return false;
        }
      } catch (error) {
        logger.debug('Microphone permission query unavailable', error);
      }
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      return true;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: VOICE_AUDIO_CONSTRAINTS });
      microphoneReadyRef.current = true;
      stream.getTracks().forEach(track => track.stop());
      return true;
    } catch (error) {
      logger.log('Microphone permission check failed', error);
      const message =
        error instanceof DOMException && (error.name === 'NotAllowedError' || error.name === 'SecurityError')
          ? MICROPHONE_PERMISSION_ERROR
          : error instanceof DOMException && error.name === 'NotFoundError'
            ? MICROPHONE_UNAVAILABLE_ERROR
            : error instanceof DOMException && error.name === 'NotReadableError'
              ? MICROPHONE_BUSY_ERROR
              : 'Manifest Voice could not start the microphone. Check browser permissions and try again.';

      setState(prev => ({
        ...prev,
        error: message,
        isListening: false,
        interimTranscript: '',
      }));
      return false;
    }
  }, []);

  const startRecorderFallback = useCallback(async (): Promise<boolean> => {
    if (typeof window === 'undefined' || typeof MediaRecorder === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setState(prev => ({
        ...prev,
        error: RECORDER_FALLBACK_ERROR,
        isListening: false,
        interimTranscript: '',
      }));
      return false;
    }

    const canUseMicrophone = await ensureMicrophoneAccess();
    if (!canUseMicrophone || !sessionActiveRef.current) {
      return false;
    }

    discardRecorderResultRef.current = false;
    recordedChunksRef.current = [];

    const mimeTypeCandidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
    const selectedMimeType = mimeTypeCandidates.find(candidate =>
      typeof MediaRecorder.isTypeSupported === 'function' ? MediaRecorder.isTypeSupported(candidate) : true,
    );

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: VOICE_AUDIO_CONSTRAINTS });
      if (!sessionActiveRef.current) {
        stream.getTracks().forEach(track => track.stop());
        return false;
      }

      stopMediaTracks();
      mediaStreamRef.current = stream;

      const mediaRecorder = selectedMimeType ? new MediaRecorder(stream, { mimeType: selectedMimeType }) : new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.onstart = () => {
        if (!sessionActiveRef.current || mediaRecorderRef.current !== mediaRecorder) {
          return;
        }

        setState(prev => ({
          ...prev,
          isListening: true,
          isProcessing: false,
          error: null,
          voiceWarning: RECORDER_FALLBACK_WARNING,
          interimTranscript: '',
        }));
      };

      mediaRecorder.ondataavailable = event => {
        if (event.data && event.data.size > 0) {
          recordedChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onerror = event => {
        logger.log('MediaRecorder error', event);
        mediaRecorderRef.current = null;
        recordedChunksRef.current = [];
        stopMediaTracks();

        setState(prev => ({
          ...prev,
          error: 'Manifest Voice could not record your microphone. Try again.',
          isListening: false,
          isProcessing: false,
          interimTranscript: '',
        }));
      };

      mediaRecorder.onstop = () => {
        const shouldDiscard = discardRecorderResultRef.current || !sessionActiveRef.current;
        const recordedBlob = recordedChunksRef.current.length
          ? new Blob(recordedChunksRef.current, {
              type: mediaRecorder.mimeType || selectedMimeType || 'audio/webm',
            })
          : null;

        mediaRecorderRef.current = null;
        recordedChunksRef.current = [];
        stopMediaTracks();
        setState(prev => ({ ...prev, isListening: false, interimTranscript: '' }));

        if (shouldDiscard || !recordedBlob || recordedBlob.size === 0) {
          discardRecorderResultRef.current = false;
          setState(prev => ({ ...prev, isProcessing: false }));
          return;
        }

        void (async () => {
          setState(prev => ({ ...prev, isProcessing: true, error: null }));

          try {
            const audioBase64 = await blobToBase64(recordedBlob);

            if (discardRecorderResultRef.current || !sessionActiveRef.current) {
              return;
            }

            const data = await postVoiceAgentJson<VoiceAgentTranscribeResponse>('/api/voice-agent/transcribe', {
              audio_base64: audioBase64,
              mime_type: recordedBlob.type || mediaRecorder.mimeType || selectedMimeType || 'audio/webm',
              filename: guessAudioFilename(recordedBlob.type || mediaRecorder.mimeType || selectedMimeType),
              language: 'en',
            });

            if (discardRecorderResultRef.current || !sessionActiveRef.current) {
              return;
            }

            const transcript = data.transcript?.trim();
            if (!data.success || !transcript) {
              setState(prev => ({
                ...prev,
                isProcessing: false,
                error: data.error || 'Manifest Voice could not transcribe that recording. Try again.',
              }));
              return;
            }

            await processUserTurnRef.current(transcript);
          } catch (error) {
            logger.log('Recorder transcription failed', error);

            if (discardRecorderResultRef.current || !sessionActiveRef.current) {
              return;
            }

            setState(prev => ({
              ...prev,
              isProcessing: false,
              error: 'Manifest Voice could not transcribe that recording. Try again.',
            }));
          } finally {
            discardRecorderResultRef.current = false;
          }
        })();
      };

      mediaRecorder.start();
      return true;
    } catch (error) {
      logger.log('Recorder fallback failed to start', error);
      stopMediaTracks();
      mediaRecorderRef.current = null;
      recordedChunksRef.current = [];

      const message =
        error instanceof DOMException && (error.name === 'NotAllowedError' || error.name === 'SecurityError')
          ? MICROPHONE_PERMISSION_ERROR
          : error instanceof DOMException && error.name === 'NotFoundError'
            ? MICROPHONE_UNAVAILABLE_ERROR
            : error instanceof DOMException && error.name === 'NotReadableError'
              ? MICROPHONE_BUSY_ERROR
              : 'Manifest Voice could not start microphone recording. Try again.';

      setState(prev => ({
        ...prev,
        error: message,
        isListening: false,
        isProcessing: false,
        interimTranscript: '',
      }));
      return false;
    }
  }, [ensureMicrophoneAccess, stopMediaTracks]);

  const persistVoiceNote = useCallback(async (response: VoiceAgentResponse): Promise<string | null> => {
    const { activeIdeaId, currentIdeaId: sidebarIdeaId, routeIdeaId: routeId, contextualIdeaId: ctxIdeaId } =
      voiceIdeaContextRef.current;

    const trimmedHtml = response.voice_note_html?.trim();
    const fallbackHtml = trimmedHtml ? null : buildMinimalVoiceNoteHtml(response);
    const voiceNoteHtml = trimmedHtml || fallbackHtml?.trim();
    if (!voiceNoteHtml) {
      return ctxIdeaId;
    }

    const mergedDescription = mergeVoiceNoteSection(ideaDescriptionRef.current, voiceNoteHtml);
    if (mergedDescription === lastSavedDescriptionRef.current) {
      return ctxIdeaId;
    }

    const targetIdeaId = activeIdeaId || sidebarIdeaId || routeId;
    if (targetIdeaId) {
      await updateIdea({
        variables: {
          ideaId: targetIdeaId,
          title: response.suggested_title || undefined,
          description: mergedDescription,
        },
      });
      syncIdeaSelection(targetIdeaId);
      ideaDescriptionRef.current = mergedDescription;
      lastSavedDescriptionRef.current = mergedDescription;
      return targetIdeaId;
    }

    const result = await createIdea({
      variables: {
        title: buildDraftIdeaTitle(response.suggested_title, response.transcript),
        description: mergedDescription,
      },
    });

    const newIdeaId = result.data?.createIdea?.ideaId || null;
    if (newIdeaId) {
      syncIdeaSelection(newIdeaId);
      ideaDescriptionRef.current = mergedDescription;
      lastSavedDescriptionRef.current = mergedDescription;
    }
    return newIdeaId;
  }, [createIdea, syncIdeaSelection, updateIdea]);

  const speak = useCallback(async (text: string, onEnd?: () => void) => {
    const spokenText = text.trim();
    if (!spokenText) {
      onEnd?.();
      return;
    }

    cancelSpeechOutput();
    speechQueueOnCompleteRef.current = onEnd || null;
    speechQueuePendingRef.current = false;
    const openingChunks = extractSpeakableChunks(spokenText, {
      maxChunkLength: VOICE_STREAM_CHUNK_MAX,
      firstChunkMaxLength: FIRST_SPEECH_CHUNK_MAX,
    });
    const merged = withFastFirstSegment(
      [...openingChunks.chunks, openingChunks.remainder].filter(Boolean),
    );
    enqueueSpeechSegments(merged.length ? merged : [spokenText]);
    maybeCompleteSpeechQueue();
  }, [cancelSpeechOutput, enqueueSpeechSegments, maybeCompleteSpeechQueue]);

  const processUserTurn = useCallback(async (userMessage: string) => {
    const normalizedMessage = userMessage.trim();
    if (!normalizedMessage) {
      return;
    }

    try {
      const commandExecution = await executeCommand(normalizedMessage, {
        ideaDescriptionHtml: ideaDescriptionRef.current,
      });
      if (commandExecution) {
        const commandUserLine: VoiceConversationMessage = { role: 'user', content: normalizedMessage };
        const commandAssistantLine: VoiceConversationMessage = {
          role: 'assistant',
          content: JSON.stringify({ message: commandExecution.response }),
        };
        conversationRef.current = [...conversationRef.current, commandUserLine, commandAssistantLine];
        setState(prev => ({
          ...prev,
          error: null,
          isListening: false,
          isProcessing: false,
          interimTranscript: '',
          currentMessage: commandExecution.response,
          conversationMessages: [...prev.conversationMessages, commandUserLine, commandAssistantLine],
        }));

        await speak(commandExecution.response, () => {
          if (sessionActiveRef.current) {
            startListeningRef.current();
          }
        });
        return;
      }
    } catch (error) {
      logger.log('Voice command execution failed', error);
      setState(prev => ({
        ...prev,
        error: 'Manifest Voice could not complete that command. Try again.',
        isListening: false,
        isProcessing: false,
        interimTranscript: '',
      }));
      return;
    }

    abortProcessing();
    cancelSpeechOutput();

    const controller = new AbortController();
    processAbortRef.current = controller;
    setState(prev => ({ ...prev, isProcessing: true, error: null, interimTranscript: '' }));

    try {
      const historyBeforeTurn = [...conversationRef.current];
      const streamingUserLine: VoiceConversationMessage = { role: 'user', content: normalizedMessage };
      setState(prev => ({
        ...prev,
        currentMessage: '',
        conversationMessages: [...historyBeforeTurn, streamingUserLine],
      }));

      let streamedAssistantText = '';
      let speechBuffer = '';
      let firstSegmentSent = false;
      let structuredPayload: VoiceAgentProcessResponse<VoiceAgentResponse> | null = null;
      let usedFallbackResponse = false;
      streamStructuredResponseRef.current = null;
      speechQueuePendingRef.current = true;

      const handleStreamEvent = (event: VoiceAgentStreamEvent) => {
        if (controller.signal.aborted) {
          return;
        }

        if (event.type === 'delta') {
          streamedAssistantText += event.text;
          const chunkResult = extractSpeakableChunks(speechBuffer + event.text, {
            maxChunkLength: VOICE_STREAM_CHUNK_MAX,
            firstChunkMaxLength: firstSegmentSent ? undefined : FIRST_SPEECH_CHUNK_MAX,
          });
          speechBuffer = chunkResult.remainder;
          if (chunkResult.chunks.length) {
            const segments = firstSegmentSent
              ? coalesceSpeechSegments(chunkResult.chunks)
              : withFastFirstSegment(chunkResult.chunks);
            firstSegmentSent = true;
            enqueueSpeechSegments(segments);
          }
          setState(prev => ({
            ...prev,
            currentMessage: streamedAssistantText,
            conversationMessages: [
              ...historyBeforeTurn,
              streamingUserLine,
              { role: 'assistant', content: streamedAssistantText },
            ],
          }));
          return;
        }

        if (event.type === 'structured') {
          structuredPayload = event.payload;
          return;
        }

        if (event.type === 'error') {
          throw new Error(event.error);
        }
      };

      try {
        await streamVoiceAgentEvents(
          '/api/voice-agent/process-stream',
          {
            messages: historyBeforeTurn,
            user_message: normalizedMessage,
            idea_id: contextualIdeaIdRef.current,
            onboarding_mode: voiceApiOnboarding,
            landing_onboarding: landingOnboarding,
          },
          handleStreamEvent,
          { signal: controller.signal },
        );
      } catch (streamError) {
        if (!controller.signal.aborted) {
          cancelSpeechOutput();
          const fallbackData = await postVoiceAgentJson<VoiceAgentProcessResponse<VoiceAgentResponse>>(
            '/api/voice-agent/process',
            {
              messages: historyBeforeTurn,
              user_message: normalizedMessage,
              idea_id: contextualIdeaIdRef.current,
              onboarding_mode: voiceApiOnboarding,
              landing_onboarding: landingOnboarding,
            },
            { signal: controller.signal },
          );
          usedFallbackResponse = true;
          structuredPayload = fallbackData;
          streamedAssistantText = fallbackData.response.message;
          speechBuffer = fallbackData.response.message;
        } else {
          throw streamError;
        }
      }

      if (controller.signal.aborted || !structuredPayload) {
        return;
      }

      const remainderResult = extractSpeakableChunks(speechBuffer, {
        maxChunkLength: VOICE_STREAM_CHUNK_MAX,
        firstChunkMaxLength: firstSegmentSent ? undefined : FIRST_SPEECH_CHUNK_MAX,
      });
      speechQueuePendingRef.current = false;
      const remainderSegments = [...remainderResult.chunks, remainderResult.remainder].filter(Boolean);
      // If nothing was spoken yet (short reply / fallback), keep a fast first segment.
      const finalSegments = firstSegmentSent
        ? coalesceSpeechSegments(remainderSegments)
        : withFastFirstSegment(remainderSegments);
      if (remainderSegments.length) {
        firstSegmentSent = true;
      }
      if (usedFallbackResponse && !finalSegments.length && structuredPayload.response.message.trim()) {
        finalSegments.push(structuredPayload.response.message.trim());
      }

      const response = structuredPayload.response;
      const becameQualified = response.is_qualified && !prevVoiceQualifiedRef.current;
      if (becameQualified) {
        finalSegments.push(QUALIFIED_BUILD_PROMPT_SUFFIX);
      }
      prevVoiceQualifiedRef.current = response.is_qualified;

      if (response.landing_complete) {
        speechQueueOnCompleteRef.current = () => {
          streamStructuredResponseRef.current = null;
          if (sessionActiveRef.current) {
            navigate('/ideas');
          }
        };
      }

      enqueueSpeechSegments(finalSegments);
      if (response.landing_complete && !finalSegments.length) {
        streamStructuredResponseRef.current = null;
        if (sessionActiveRef.current) {
          navigate('/ideas');
        }
      }

      conversationRef.current = structuredPayload.messages;
      const nextConversationMessages = structuredPayload.messages;
      streamStructuredResponseRef.current = response;

      if (processAbortRef.current === controller) {
        processAbortRef.current = null;
      }

      setState(prev => ({
        ...prev,
        isProcessing: false,
        currentResponse: response,
        currentMessage: becameQualified ? `${response.message} ${QUALIFIED_BUILD_PROMPT_SUFFIX}` : response.message,
        isQualified: response.is_qualified,
        activeIdeaId: prev.activeIdeaId || currentIdeaId || routeIdeaId || null,
        conversationMessages: [...nextConversationMessages],
      }));

      void (async () => {
        try {
          const savedIdeaId = await persistVoiceNote(response);
          if (!sessionActiveRef.current) {
            return;
          }
          if (savedIdeaId) {
            setState(prev => ({
              ...prev,
              activeIdeaId: savedIdeaId,
            }));
          }
        } catch (error) {
          logger.log('Voice note persistence failed', error);
          if (sessionActiveRef.current) {
            setState(prev => ({
              ...prev,
              voiceWarning: VOICE_NOTE_SAVE_WARNING,
            }));
          }
        }
      })();
      maybeResumeListeningAfterSpeech();
    } catch (error) {
      if (processAbortRef.current === controller) {
        processAbortRef.current = null;
      }

      if (isAbortError(error)) {
        return;
      }

      logger.log('Voice agent processing failed', error);
      setState(prev => ({
        ...prev,
        isProcessing: false,
        error: 'Voice mode could not process that turn. Try again.',
      }));
    }
  }, [
    abortProcessing,
    cancelSpeechOutput,
    currentIdeaId,
    enqueueSpeechSegments,
    executeCommand,
    isGuest,
    maybeResumeListeningAfterSpeech,
    voiceApiOnboarding,
    persistVoiceNote,
    routeIdeaId,
    speak,
    landingOnboarding,
    navigate,
  ]);

  useEffect(() => {
    processUserTurnRef.current = processUserTurn;
  }, [processUserTurn]);

  const startListening = useCallback(() => {
    if (!sessionActiveRef.current) return;
    void (async () => {
      const SpeechRecognitionConstructor = window.SpeechRecognition || window.webkitSpeechRecognition;

      if (mediaRecorderRef.current?.state === 'recording') {
        return;
      }

      if (forceRecorderFallbackRef.current || !SpeechRecognitionConstructor) {
        forceRecorderFallbackRef.current = true;
        await startRecorderFallback();
        return;
      }

      const canUseMicrophone = await ensureMicrophoneAccess();
      if (!canUseMicrophone || !sessionActiveRef.current) {
        return;
      }

      if (recognitionRef.current) {
        recognitionRef.current.stop?.();
        recognitionRef.current = null;
      }

      const recognition = new SpeechRecognitionConstructor();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;
      recognition.lang = 'en-US';

      const recognitionWithHints = recognition as SpeechRecognition & {
        phrases?: Array<{ phrase: string; boost?: number }>;
      };
      if ('phrases' in recognitionWithHints) {
        recognitionWithHints.phrases = SPEECH_RECOGNITION_HINTS.map(phrase => ({ phrase, boost: 5 }));
      }

      recognition.onstart = () => {
        if (!sessionActiveRef.current || recognitionRef.current !== recognition) {
          return;
        }

        setState(prev => ({ ...prev, isListening: true, error: null, voiceWarning: null, interimTranscript: '' }));
      };

      recognition.onresult = (event: SpeechRecognitionEvent) => {
        if (!sessionActiveRef.current || recognitionRef.current !== recognition) {
          return;
        }

        let finalTranscript = '';
        let interimTranscript = '';

        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const result = event.results[index];
          const transcript = result[0]?.transcript?.trim();
          if (!transcript) {
            continue;
          }

          if (result.isFinal) {
            finalTranscript += `${finalTranscript ? ' ' : ''}${transcript}`;
          } else {
            interimTranscript += `${interimTranscript ? ' ' : ''}${transcript}`;
          }
        }

        if (interimTranscript) {
          setState(prev => ({ ...prev, interimTranscript }));
        }

        if (finalTranscript) {
          const normalizedFinalTranscript = finalTranscript.trim();
          setState(prev => ({ ...prev, isListening: false, interimTranscript: '' }));
          recognition.stop?.();
          void processUserTurnRef.current(normalizedFinalTranscript);
        }
      };

      recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
        if (recognitionRef.current !== recognition) {
          return;
        }

        logger.log('Speech recognition error', event.error);
        if (event.error === 'service-not-allowed' || event.error === 'network') {
          recognitionRef.current = null;
          forceRecorderFallbackRef.current = true;
          void startRecorderFallback();
          return;
        }

        const errorMessage =
          event.error === 'not-allowed'
            ? MICROPHONE_PERMISSION_ERROR
            : event.error === 'audio-capture'
              ? MICROPHONE_UNAVAILABLE_ERROR
              : event.error === 'no-speech' || event.error === 'aborted'
                ? null
                : `Voice capture error: ${event.error}`;

        setState(prev => ({
          ...prev,
          error: errorMessage,
          isListening: false,
          interimTranscript: '',
        }));
      };

      recognition.onend = () => {
        if (recognitionRef.current === recognition) {
          recognitionRef.current = null;
        }

        setState(prev => ({ ...prev, isListening: false, interimTranscript: '' }));
      };

      recognitionRef.current = recognition;

      try {
        recognition.start();
      } catch (error) {
        logger.log('Speech recognition failed to start', error);
        if (recognitionRef.current === recognition) {
          recognitionRef.current = null;
        }
        forceRecorderFallbackRef.current = true;
        await startRecorderFallback();
      }
    })();
  }, [ensureMicrophoneAccess, startRecorderFallback]);

  useEffect(() => {
    startListeningRef.current = startListening;
  }, [startListening]);

  const interruptAndStartListening = useCallback(() => {
    abortListeningCapture();
    cancelSpeechOutput();
    abortProcessing();
    setState(prev => ({ ...prev, error: null, interimTranscript: '' }));

    if (sessionActiveRef.current) {
      startListeningRef.current();
    }
  }, [abortListeningCapture, abortProcessing, cancelSpeechOutput]);

  interruptAndStartListeningRef.current = interruptAndStartListening;

  useEffect(() => {
    if (!state.isActive || (!state.isSpeaking && !state.isProcessing)) {
      return undefined;
    }

    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      return undefined;
    }

    let cleanupMonitor: (() => void) | undefined;
    let cancelled = false;
    let acquired = false;

    void (async () => {
      try {
        const { stream, context } = await acquireVoiceMic();
        if (cancelled) {
          releaseVoiceMic();
          return;
        }
        acquired = true;
        cleanupMonitor = startVoiceBargeInMonitor(
          stream,
          () => {
            interruptAndStartListeningRef.current();
          },
          { context, ownsStream: false },
        );
      } catch (error) {
        logger.debug('Voice barge-in monitor could not open microphone', error);
      }
    })();

    return () => {
      cancelled = true;
      cleanupMonitor?.();
      if (acquired) {
        releaseVoiceMic();
      }
    };
  }, [state.isActive, state.isProcessing, state.isSpeaking]);

  const startSession = useCallback(async () => {
    const requestId = startSessionRequestIdRef.current + 1;
    startSessionRequestIdRef.current = requestId;
    sessionActiveRef.current = true;
    prevVoiceQualifiedRef.current = false;
    discardRecorderResultRef.current = false;
    abortProcessing();
    cancelSpeechOutput();
    abortListeningCapture();
    conversationRef.current = [];
    voicePlaceholderCreatedRef.current = false;

    setState(prev => ({
      ...prev,
      isActive: true,
      isPaused: false,
      error: null,
      voiceWarning: null,
      voiceMode: null,
      currentResponse: null,
      currentMessage: '',
      interimTranscript: '',
      isQualified: false,
      activeIdeaId: contextualIdeaId,
      conversationMessages: [],
    }));

    const ensureVoicePlaceholderIdea = async (): Promise<string | null> => {
      const resolvedId = contextualIdeaIdRef.current;
      if (resolvedId) {
        return resolvedId;
      }
      if (voicePlaceholderCreatedRef.current) {
        return null;
      }
      voicePlaceholderCreatedRef.current = true;
      try {
        const result = await createIdea({
          variables: { title: 'Voice Idea', description: '<p>Voice session draft.</p>' },
        });
        const newId = result.data?.createIdea?.ideaId ?? null;
        if (newId) {
          syncIdeaSelection(newId);
          ideaDescriptionRef.current = '<p>Voice session draft.</p>';
          lastSavedDescriptionRef.current = '<p>Voice session draft.</p>';
          setState(prev => ({ ...prev, activeIdeaId: newId }));
          return newId;
        }
        voicePlaceholderCreatedRef.current = false;
        return null;
      } catch (error) {
        logger.log('Voice placeholder idea creation failed', error);
        voicePlaceholderCreatedRef.current = false;
        return null;
      }
    };

    try {
      await ensureVoicePlaceholderIdea();

      const startIdeaId = contextualIdeaIdRef.current;
      const data = await postVoiceAgentJson<VoiceAgentStartResponse>('/api/voice-agent/start', {
        idea_id: startIdeaId,
        onboarding_mode: voiceApiOnboarding,
        landing_onboarding: landingOnboarding,
      });

      if (!sessionActiveRef.current || startSessionRequestIdRef.current !== requestId) {
        return;
      }

      conversationRef.current = data.messages;
      prevVoiceQualifiedRef.current = data.response.is_qualified;
      setState(prev => ({
        ...prev,
        isActive: true,
        currentResponse: data.response,
        currentMessage: data.response.message,
        isQualified: data.response.is_qualified,
        activeIdeaId: contextualIdeaIdRef.current,
        conversationMessages: [...data.messages],
      }));

      const greeting = data.response.message?.trim() ?? '';
      if (greeting) {
        await speak(greeting, () => {
          if (sessionActiveRef.current) {
            startListeningRef.current();
          }
        });
      } else if (sessionActiveRef.current) {
        startListeningRef.current();
      }
      return;
    } catch (error) {
      logger.log('Voice agent start endpoint unavailable, using local greeting', error);
    }

    if (!sessionActiveRef.current || startSessionRequestIdRef.current !== requestId) {
      return;
    }

    await ensureVoicePlaceholderIdea();

    if (!sessionActiveRef.current || startSessionRequestIdRef.current !== requestId) {
      return;
    }

    const baseLocal = buildLocalGreeting(Boolean(ideaDescriptionRef.current));
    const localResponse: VoiceAgentResponse = landingOnboarding
      ? {
          ...baseLocal,
          message: LANDING_LOCAL_QUESTION_ONE,
          landing_onboarding_step: 1,
          landing_complete: false,
        }
      : baseLocal;
    conversationRef.current = [
      {
        role: 'assistant',
        content: JSON.stringify({
          message: localResponse.message,
          is_qualified: false,
          summary: null,
          suggested_title: null,
          covered_topics: [],
          missing_topics: localResponse.missing_topics,
          qualification_confidence: 0.05,
          ...(landingOnboarding ? { landing_onboarding_step: 1, landing_complete: false } : {}),
        }),
      },
    ];

    setState(prev => ({
      ...prev,
      isActive: true,
      currentResponse: localResponse,
      currentMessage: localResponse.message,
      isQualified: false,
      activeIdeaId: contextualIdeaIdRef.current,
      conversationMessages: [...conversationRef.current],
    }));

    const localGreeting = localResponse.message?.trim() ?? '';
    if (localGreeting) {
      await speak(localGreeting, () => {
        if (sessionActiveRef.current) {
          startListeningRef.current();
        }
      });
    } else if (sessionActiveRef.current) {
      startListeningRef.current();
    }
  }, [
    abortListeningCapture,
    abortProcessing,
    cancelSpeechOutput,
    contextualIdeaId,
    createIdea,
    landingOnboarding,
    speak,
    syncIdeaSelection,
    voiceApiOnboarding,
  ]);

  const endSession = useCallback(() => {
    startSessionRequestIdRef.current += 1;
    sessionActiveRef.current = false;
    abortProcessing();
    cancelSpeechOutput();
    abortListeningCapture();
    recognitionRef.current = null;
    mediaRecorderRef.current = null;
    recordedChunksRef.current = [];
    stopMediaTracks();
    conversationRef.current = [];
    voicePlaceholderCreatedRef.current = false;

    setState(prev => ({
      ...prev,
      isActive: false,
      isPaused: false,
      isListening: false,
      isSpeaking: false,
      isProcessing: false,
      error: null,
      voiceWarning: null,
      voiceMode: null,
      currentResponse: null,
      currentMessage: '',
      interimTranscript: '',
      isQualified: false,
      activeIdeaId: null,
      conversationMessages: [],
    }));
  }, [abortListeningCapture, abortProcessing, cancelSpeechOutput, stopMediaTracks]);

  const pauseSession = useCallback(() => {
    startSessionRequestIdRef.current += 1;
    sessionActiveRef.current = false;
    abortProcessing();
    cancelSpeechOutput();
    abortListeningCapture();
    stopMediaTracks();
    setState(prev => ({ ...prev, isPaused: true, isListening: false, isSpeaking: false, isProcessing: false }));
  }, [abortProcessing, cancelSpeechOutput, abortListeningCapture, stopMediaTracks]);

  const resumeSession = useCallback(() => {
    sessionActiveRef.current = true;
    setState(prev => ({ ...prev, isPaused: false, error: null }));
    startListeningRef.current();
  }, []);

  const openWorkspace = useCallback(() => {
    const ideaId = state.activeIdeaId || currentIdeaId || routeIdeaId;
    if (ideaId) {
      navigate(`/ideas/${ideaId}/description`);
    } else {
      navigate('/ideas');
    }
  }, [currentIdeaId, navigate, routeIdeaId, state.activeIdeaId]);

  useEffect(() => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.getVoices();
    }

    return () => {
      startSessionRequestIdRef.current += 1;
      sessionActiveRef.current = false;
      abortProcessing();
      cancelSpeechOutput();
      abortListeningCapture();
      recognitionRef.current = null;
      mediaRecorderRef.current = null;
      recordedChunksRef.current = [];
      stopMediaTracks();
    };
  }, [abortListeningCapture, abortProcessing, cancelSpeechOutput, stopMediaTracks]);

  return {
    audioRef,
    state,
    startSession,
    endSession,
    pauseSession,
    resumeSession,
    startListening,
    stopListening,
    interruptAndStartListening,
    openWorkspace,
  };
}

export type VoiceIdeaSessionApi = ReturnType<typeof useVoiceIdeaSession>;
