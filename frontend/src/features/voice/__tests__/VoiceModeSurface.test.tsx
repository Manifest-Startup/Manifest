import React, { createRef } from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import VoiceModeSurface from "../VoiceModeSurface";
import type { VoiceSessionState } from "../useVoiceIdeaSession";
import type { VoiceAgentResponse } from "../voiceAgentApi";

const baseResponse: VoiceAgentResponse = {
  message: "Ready when you are.",
  is_qualified: false,
  summary: null,
  suggested_title: null,
  transcript: null,
  voice_note_html: null,
  covered_topics: [],
  missing_topics: ["problem", "target_customer"],
  qualification_confidence: 0.1,
  context: {},
};

const assistantHistoryContent = JSON.stringify({
  message: baseResponse.message,
  is_qualified: false,
  summary: null,
  suggested_title: null,
  covered_topics: [],
  missing_topics: baseResponse.missing_topics,
  qualification_confidence: 0.1,
});

const buildState = (overrides: Partial<VoiceSessionState> = {}): VoiceSessionState => ({
  isActive: true,
  isListening: false,
  isSpeaking: false,
  isProcessing: false,
  error: null,
  voiceWarning: null,
  voiceMode: null,
  currentResponse: baseResponse,
  currentMessage: baseResponse.message,
  interimTranscript: "",
  isQualified: false,
  activeIdeaId: "idea-1",
  conversationMessages: [{ role: "assistant", content: assistantHistoryContent }],
  ...overrides,
});

const renderSurface = (stateOverrides: Partial<VoiceSessionState> = {}) => {
  const props = {
    audioRef: createRef<HTMLAudioElement>(),
    hasConversationDraft: Boolean(stateOverrides.currentResponse?.transcript),
    mode: "overlay" as const,
    onDismiss: jest.fn(),
    onEndSession: jest.fn(),
    onOpenWorkspace: jest.fn(),
    onStartSession: jest.fn(),
    onSwitchToWorkspaceMode: jest.fn(),
    state: buildState(stateOverrides),
  };

  render(<VoiceModeSurface {...props} />);

  return props;
};

describe("VoiceModeSurface", () => {
  test("landing layout shows opt-in before microphone when session is inactive", () => {
    const props = {
      audioRef: createRef<HTMLAudioElement>(),
      hasConversationDraft: false,
      mode: "page" as const,
      landingLayout: true,
      onEndSession: jest.fn(),
      onOpenWorkspace: jest.fn(),
      onStartSession: jest.fn(),
      state: buildState({ isActive: false, conversationMessages: [], currentResponse: null, currentMessage: "" }),
    };

    render(<VoiceModeSurface {...props} />);

    expect(screen.getByRole("button", { name: /use microphone and start/i })).toBeInTheDocument();
    expect(screen.getByText(/nothing records until you choose to start/i)).toBeInTheDocument();
  });

  test("minimizing preserves audio and keeps end controls available", () => {
    const props = renderSurface();
    const audio = props.audioRef.current;
    fireEvent.click(screen.getByRole("button", { name: "Minimize voice panel" }));
    expect(screen.queryByTestId("voice-live-transcript")).not.toBeInTheDocument();
    expect(props.audioRef.current).toBe(audio);
    expect(props.onEndSession).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "End" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Expand voice panel" }));
    expect(screen.getByTestId("voice-live-transcript")).toBeInTheDocument();
  });

  test("errors remain visible before starting", () => {
    renderSurface({ isActive: false, error: "Microphone access is required." });
    expect(screen.getByRole("alert")).toHaveTextContent("Microphone access is required.");
  });

  test("renders live transcript from conversation messages and parsed assistant text", () => {
    renderSurface({
      conversationMessages: [
        { role: "assistant", content: assistantHistoryContent },
        { role: "user", content: "We automate lease renewals for mid-size landlords." },
        {
          role: "assistant",
          content: JSON.stringify({
            message: "What’s the clearest pain landlords feel today?",
            is_qualified: false,
            summary: null,
            suggested_title: null,
            covered_topics: [],
            missing_topics: ["problem"],
            qualification_confidence: 0.2,
          }),
        },
      ],
    });

    expect(screen.getByTestId("voice-live-transcript")).toBeInTheDocument();
    expect(screen.getByText(/We automate lease renewals/i)).toBeInTheDocument();
    expect(screen.getByText(/What’s the clearest pain landlords feel today/i)).toBeInTheDocument();
  });

  test("shows and wires the workspace shortcut once the conversation is qualified", () => {
    const props = renderSurface({
      isQualified: true,
      currentResponse: {
        ...baseResponse,
        is_qualified: true,
        summary: "Qualified enough to take back into the workspace.",
      },
    });

    fireEvent.click(screen.getByRole("button", { name: /open idea/i }));

    expect(props.onOpenWorkspace).toHaveBeenCalledTimes(1);
  });

  test("keeps the workspace shortcut available when a transcript draft exists", () => {
    renderSurface({
      currentResponse: {
        ...baseResponse,
        transcript: "Founder described a workflow gap for apartment buying clubs.",
      },
    });

    expect(screen.getByRole("button", { name: /open idea/i })).toBeInTheDocument();
  });

  test("shows open idea when an active idea id exists even without transcript", () => {
    renderSurface({
      activeIdeaId: "idea-placeholder",
      currentResponse: {
        ...baseResponse,
        transcript: null,
        voice_note_html: null,
        summary: null,
      },
    });

    expect(screen.getByRole("button", { name: /open idea/i })).toBeInTheDocument();
  });
});
