import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useReactiveVar } from '@apollo/client/react';
import { useLocation, useNavigate } from 'react-router-dom';

import { CREATE_IDEA, UPDATE_IDEA } from '../core/apollo/queries';
import { sidebarVar, userVar } from '../core/apollo/localState';
import { createLogger } from '../core/logError';
import {
  postVoiceAgentJson,
  fetchRealtimeSession,
  VoiceAgentProcessResponse,
  VoiceAgentResponse,
  VoiceConversationMessage,
} from './voiceAgentApi';
import { connectRealtimeVoice, RealtimeConnection } from './realtimeVoiceClient';
import {
  createRealtimeTranscriptState,
  reduceRealtimeEvent,
  RealtimeTranscriptState,
} from './realtimeEvents';
import { VOICE_AUDIO_CONSTRAINTS, VoiceSessionState } from './useVoiceIdeaSession';
import {
  buildDraftIdeaTitle,
  buildMinimalVoiceNoteHtml,
  mergeVoiceNoteSection,
} from './voiceNote';

const log = createLogger('useRealtimeVoiceSession');

const GREETING_INSTRUCTION =
  'Greet the founder warmly in one short sentence, then ask what they want to work on. Keep it brief.';

const INITIAL_STATE: VoiceSessionState = {
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
};

function toConversationMessages(state: RealtimeTranscriptState): VoiceConversationMessage[] {
  return state.messages.map(turn => ({ role: turn.role, content: turn.content }));
}

export interface UseRealtimeVoiceSessionOptions {
  landingOnboarding?: boolean;
}

/**
 * Speech-to-speech voice session backed by the OpenAI Realtime API over WebRTC.
 *
 * Returns the same shape as {@link useVoiceIdeaSession} so the voice UI can swap
 * implementations transparently. Turn-taking and barge-in are handled natively
 * by the server's voice-activity detection, so this path has near-instant
 * time-to-first-audio. The durable idea note is synthesized once at the end of
 * the session via the existing structured pipeline (kept off the hot path to
 * preserve latency and contain cost).
 */
export function useRealtimeVoiceSession(options?: UseRealtimeVoiceSessionOptions) {
  const landingOnboarding = Boolean(options?.landingOnboarding);
  const location = useLocation();
  const navigate = useNavigate();
  const { currentIdeaId } = useReactiveVar(sidebarVar);
  const { isGuest } = useReactiveVar(userVar);
  const voiceApiOnboarding = Boolean(isGuest) || landingOnboarding;
  const routeIdeaId = location.pathname.match(/^\/ideas\/([^/]+)/)?.[1] || null;

  const [state, setState] = useState<VoiceSessionState>(INITIAL_STATE);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const connectionRef = useRef<RealtimeConnection | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const transcriptRef = useRef<RealtimeTranscriptState>(createRealtimeTranscriptState());
  const sessionActiveRef = useRef(false);
  const finalizedRef = useRef(false);
  const activeIdeaIdRef = useRef<string | null>(null);

  const [createIdea] = useMutation(CREATE_IDEA);
  const [updateIdea] = useMutation(UPDATE_IDEA);

  const syncTranscriptToState = useCallback(() => {
    const t = transcriptRef.current;
    setState(prev => ({
      ...prev,
      isListening: t.phase === 'listening',
      isSpeaking: t.phase === 'speaking',
      isProcessing: t.phase === 'thinking',
      currentMessage: t.assistantText,
      interimTranscript: t.userText,
      conversationMessages: toConversationMessages(t),
      error: t.error || prev.error,
    }));
  }, []);

  const stopMic = useCallback(() => {
    const stream = micStreamRef.current;
    micStreamRef.current = null;
    if (stream) {
      try {
        stream.getTracks().forEach(track => track.stop());
      } catch {
        /* ignore */
      }
    }
  }, []);

  const teardownConnection = useCallback(() => {
    const connection = connectionRef.current;
    connectionRef.current = null;
    if (connection) {
      try {
        connection.close();
      } catch {
        /* ignore */
      }
    }
    stopMic();
  }, [stopMic]);

  /**
   * Synthesize + persist the durable voice note from the spoken transcript.
   * Best-effort: failures never surface as a hard error to the founder.
   */
  const persistConversation = useCallback(async (): Promise<string | null> => {
    const messages = toConversationMessages(transcriptRef.current);
    const lastUserIndex = [...messages].reverse().findIndex(m => m.role === 'user');
    if (lastUserIndex === -1) {
      return activeIdeaIdRef.current;
    }
    const absoluteIndex = messages.length - 1 - lastUserIndex;
    const priorMessages = messages.slice(0, absoluteIndex);
    const lastUserMessage = messages[absoluteIndex]?.content?.trim();
    if (!lastUserMessage) {
      return activeIdeaIdRef.current;
    }

    let payload: VoiceAgentProcessResponse<VoiceAgentResponse>;
    try {
      payload = await postVoiceAgentJson<VoiceAgentProcessResponse<VoiceAgentResponse>>(
        '/api/voice-agent/process',
        {
          messages: priorMessages,
          user_message: lastUserMessage,
          idea_id: activeIdeaIdRef.current || currentIdeaId || routeIdeaId,
          onboarding_mode: voiceApiOnboarding,
          landing_onboarding: landingOnboarding,
        },
      );
    } catch (error) {
      log.error('Realtime note synthesis failed', error);
      return activeIdeaIdRef.current;
    }

    const response = payload.response;
    const voiceNoteHtml =
      response.voice_note_html?.trim() || buildMinimalVoiceNoteHtml(response)?.trim();
    if (!voiceNoteHtml) {
      return activeIdeaIdRef.current;
    }
    const mergedDescription = mergeVoiceNoteSection(null, voiceNoteHtml);

    const targetIdeaId = activeIdeaIdRef.current || currentIdeaId || routeIdeaId;
    try {
      if (targetIdeaId) {
        await updateIdea({
          variables: {
            ideaId: targetIdeaId,
            title: response.suggested_title || undefined,
            description: mergedDescription,
          },
        });
        activeIdeaIdRef.current = targetIdeaId;
        return targetIdeaId;
      }
      const result = await createIdea({
        variables: {
          title: buildDraftIdeaTitle(response.suggested_title, response.transcript),
          description: mergedDescription,
        },
      });
      const newId = result.data?.createIdea?.ideaId || null;
      if (newId) {
        activeIdeaIdRef.current = newId;
      }
      return newId;
    } catch (error) {
      log.error('Realtime idea persistence failed', error);
      return activeIdeaIdRef.current;
    }
  }, [
    createIdea,
    currentIdeaId,
    landingOnboarding,
    routeIdeaId,
    updateIdea,
    voiceApiOnboarding,
  ]);

  const finalize = useCallback(async (): Promise<string | null> => {
    if (finalizedRef.current) {
      return activeIdeaIdRef.current;
    }
    finalizedRef.current = true;
    sessionActiveRef.current = false;
    teardownConnection();
    const ideaId = await persistConversation();
    setState(prev => ({ ...prev, activeIdeaId: ideaId }));
    return ideaId;
  }, [persistConversation, teardownConnection]);

  const handleServerEvent = useCallback(
    (event: Record<string, unknown>) => {
      transcriptRef.current = reduceRealtimeEvent(transcriptRef.current, event);
      syncTranscriptToState();
    },
    [syncTranscriptToState],
  );

  const startSession = useCallback(async () => {
    if (sessionActiveRef.current) {
      return;
    }
    sessionActiveRef.current = true;
    finalizedRef.current = false;
    transcriptRef.current = createRealtimeTranscriptState();
    setState({ ...INITIAL_STATE, isActive: true, isProcessing: true });

    let micStream: MediaStream;
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: VOICE_AUDIO_CONSTRAINTS });
    } catch (error) {
      log.error('Microphone permission denied', error);
      sessionActiveRef.current = false;
      setState(prev => ({
        ...prev,
        isActive: false,
        isProcessing: false,
        error: 'Microphone access is required for voice mode.',
      }));
      return;
    }
    micStreamRef.current = micStream;

    let session;
    try {
      session = await fetchRealtimeSession({
        idea_id: activeIdeaIdRef.current || currentIdeaId || routeIdeaId,
        onboarding_mode: voiceApiOnboarding,
        landing_onboarding: landingOnboarding,
      });
    } catch (error) {
      log.error('Realtime session mint failed', error);
      session = { enabled: false } as const;
    }

    if (!session.enabled || !session.client_secret || !audioRef.current) {
      stopMic();
      sessionActiveRef.current = false;
      setState(prev => ({
        ...prev,
        isActive: false,
        isProcessing: false,
        error: 'Realtime voice is unavailable right now.',
      }));
      return;
    }

    try {
      const connection = await connectRealtimeVoice({
        clientSecret: session.client_secret,
        model: session.model || 'gpt-4o-realtime-preview',
        baseUrl: session.base_url || undefined,
        micStream,
        audioEl: audioRef.current,
        onEvent: handleServerEvent,
        onOpen: () => {
          connection.sendEvent({
            type: 'response.create',
            response: { instructions: GREETING_INSTRUCTION },
          });
        },
        onError: error => log.error('Realtime data channel error', error),
      });
      connectionRef.current = connection;
      setState(prev => ({
        ...prev,
        isActive: true,
        isProcessing: false,
        voiceMode: 'ai',
      }));
    } catch (error) {
      log.error('Realtime WebRTC connection failed', error);
      teardownConnection();
      sessionActiveRef.current = false;
      setState(prev => ({
        ...prev,
        isActive: false,
        isProcessing: false,
        error: 'Could not connect to realtime voice.',
      }));
    }
  }, [
    currentIdeaId,
    handleServerEvent,
    landingOnboarding,
    routeIdeaId,
    stopMic,
    teardownConnection,
    voiceApiOnboarding,
  ]);

  const endSession = useCallback(() => {
    void finalize();
    setState(prev => ({
      ...INITIAL_STATE,
      activeIdeaId: prev.activeIdeaId || activeIdeaIdRef.current,
    }));
  }, [finalize]);

  const startListening = useCallback(() => {
    connectionRef.current?.setMicEnabled(true);
  }, []);

  const stopListening = useCallback(() => {
    connectionRef.current?.setMicEnabled(false);
  }, []);

  const interruptAndStartListening = useCallback(() => {
    connectionRef.current?.interrupt();
    connectionRef.current?.setMicEnabled(true);
  }, []);

  const openWorkspace = useCallback(async () => {
    const ideaId = await finalize();
    const target = ideaId || currentIdeaId || routeIdeaId;
    navigate(target ? `/ideas/${target}/description` : '/ideas');
  }, [currentIdeaId, finalize, navigate, routeIdeaId]);

  useEffect(() => {
    return () => {
      sessionActiveRef.current = false;
      teardownConnection();
    };
  }, [teardownConnection]);

  return {
    audioRef,
    state,
    startSession,
    endSession,
    startListening,
    stopListening,
    interruptAndStartListening,
    openWorkspace,
  };
}

export type RealtimeVoiceSessionApi = ReturnType<typeof useRealtimeVoiceSession>;
