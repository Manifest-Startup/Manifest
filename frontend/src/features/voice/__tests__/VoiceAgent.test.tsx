import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";
import { BrowserRouter } from "react-router-dom";

import { sidebarVar, userVar } from "../../core/apollo/localState";
import { GET_IDEAS } from "../../core/apollo/queries";
import VoiceAgent from "../VoiceAgent";

const mockFetch = jest.fn();

const mockSpeechSynthesis = {
  addEventListener: jest.fn(),
  cancel: jest.fn(),
  getVoices: jest.fn().mockReturnValue([]),
  removeEventListener: jest.fn(),
  speak: jest.fn(),
};

const mockSpeechRecognition = jest.fn();
const speechRecognitionInstances: Array<{
  abort: jest.Mock;
  stop: jest.Mock;
}> = [];
const mockGetUserMedia = jest.fn();
const mockMediaRecorder = jest.fn();

const createMockStream = () =>
  ({
    getTracks: () => [
      {
        stop: jest.fn(),
      },
    ],
  }) as unknown as MediaStream;

class MockSpeechRecognition {
  abort = jest.fn(() => this.onend?.({} as Event));
  continuous = false;
  interimResults = false;
  lang = "";
  maxAlternatives = 1;
  onend: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onresult: ((event: Event) => void) | null = null;
  onstart: ((event: Event) => void) | null = null;
  start = jest.fn(() => this.onstart?.({} as Event));
  stop = jest.fn(() => this.onend?.({} as Event));

  constructor() {
    mockSpeechRecognition();
    speechRecognitionInstances.push(this);
  }
}

class MockMediaRecorder {
  static isTypeSupported = jest.fn(() => true);

  mimeType: string;
  ondataavailable: ((event: BlobEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onstart: ((event: Event) => void) | null = null;
  onstop: ((event: Event) => void) | null = null;
  start = jest.fn(() => {
    this.state = "recording";
    this.onstart?.({} as Event);
  });
  state: RecordingState = "inactive";
  stop = jest.fn(() => {
    this.state = "inactive";
    this.onstop?.({} as Event);
  });

  constructor(_stream: MediaStream, options?: MediaRecorderOptions) {
    this.mimeType = options?.mimeType || "audio/webm";
    mockMediaRecorder();
  }
}

Object.defineProperty(window, "speechSynthesis", {
  configurable: true,
  value: mockSpeechSynthesis,
  writable: true,
});

Object.defineProperty(window, "SpeechRecognition", {
  configurable: true,
  value: MockSpeechRecognition,
  writable: true,
});

Object.defineProperty(window, "webkitSpeechRecognition", {
  configurable: true,
  value: MockSpeechRecognition,
  writable: true,
});

Object.defineProperty(window.navigator, "mediaDevices", {
  configurable: true,
  value: { getUserMedia: mockGetUserMedia },
  writable: true,
});

Object.defineProperty(window, "MediaRecorder", {
  configurable: true,
  value: MockMediaRecorder,
  writable: true,
});

global.MediaRecorder = MockMediaRecorder as typeof MediaRecorder;

global.SpeechSynthesisUtterance = jest.fn().mockImplementation(() => ({
  onend: null,
  onerror: null,
  onstart: null,
  pitch: 1,
  rate: 1,
  voice: null,
  volume: 1,
}));

const mockAnalyser = {
  context: { sampleRate: 48000 },
  disconnect: jest.fn(),
  fftSize: 2048,
  frequencyBinCount: 1024,
  smoothingTimeConstant: 0.55,
  connect: jest.fn(),
  getByteTimeDomainData: (arr: Uint8Array) => {
    arr.fill(128);
  },
  getByteFrequencyData: (arr: Uint8Array) => {
    arr.fill(2);
  },
};

global.AudioContext = jest.fn().mockImplementation(
  () =>
    ({
      destination: {},
      state: "running",
      sampleRate: 48000,
      resume: jest.fn(() => Promise.resolve()),
      createMediaElementSource: jest.fn(() => ({ connect: jest.fn(), disconnect: jest.fn() })),
      createMediaStreamSource: jest.fn(() => ({ connect: jest.fn(), disconnect: jest.fn() })),
      createAnalyser: jest.fn(() => mockAnalyser),
      close: jest.fn(() => Promise.resolve()),
    }) as unknown as AudioContext,
);

Object.defineProperty(window, "AudioContext", {
  configurable: true,
  value: global.AudioContext,
  writable: true,
});

const mocks = [
  {
    request: {
      query: GET_IDEAS,
    },
    result: {
      data: {
        ideas: [],
      },
    },
  },
];

const renderVoiceAgent = () =>
  render(
    <MockedProvider addTypename={false} mocks={mocks}>
      <BrowserRouter>
        <VoiceAgent />
      </BrowserRouter>
    </MockedProvider>,
  );

describe("VoiceAgent Component", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    speechRecognitionInstances.length = 0;
    mockGetUserMedia.mockResolvedValue(createMockStream());
    mockFetch.mockRejectedValue(new Error("offline"));
    global.fetch = mockFetch as unknown as typeof fetch;
    Object.defineProperty(window, "SpeechRecognition", {
      configurable: true,
      value: MockSpeechRecognition,
      writable: true,
    });
    Object.defineProperty(window, "webkitSpeechRecognition", {
      configurable: true,
      value: MockSpeechRecognition,
      writable: true,
    });
    localStorage.setItem("access_token", "test-token");
    userVar({ isLoggedIn: true, userData: { userId: "user-1", email: "hello@manifeststartup.com" } });
    sidebarVar({ currentIdeaAspect: "description", currentIdeaId: null, allIdeaIds: [] });
  });

  describe("Initial State", () => {
    test("renders start session button when inactive", async () => {
      renderVoiceAgent();

      expect(await screen.findByRole("button", { name: /start conversation/i })).toBeInTheDocument();
    });

    test("uses the calmer voice-first landing copy", async () => {
      renderVoiceAgent();

      expect(await screen.findByText(/talk your idea through/i)).toBeInTheDocument();
      expect(screen.getByText(/nothing records until/i)).toBeInTheDocument();
    });

    test("shows the Manifest Voice brand", async () => {
      renderVoiceAgent();

      await waitFor(() => {
        expect(screen.getAllByText(/manifest voice/i).length).toBeGreaterThan(0);
      });
    });
  });

  describe("Session Start", () => {
    test("clicking start button begins session and shows end control", async () => {
      renderVoiceAgent();

      fireEvent.click(await screen.findByRole("button", { name: /start conversation/i }));

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /end voice session/i })).toBeInTheDocument();
      });
    });

    test("starts listening without a spoken greeting when the opening message is empty", async () => {
      renderVoiceAgent();

      fireEvent.click(await screen.findByRole("button", { name: /start conversation/i }));

      await waitFor(() => {
        expect(mockSpeechSynthesis.speak).not.toHaveBeenCalled();
        expect(mockSpeechRecognition).toHaveBeenCalled();
      });
    });

    test("session details panel opens from header control", async () => {
      renderVoiceAgent();

      fireEvent.click(await screen.findByRole("button", { name: /start conversation/i }));

      const details = await screen.findByRole("button", { name: /session details/i });
      fireEvent.click(details);

      expect(screen.getByText(/create a new idea/i)).toBeInTheDocument();
    });
  });

  describe("Session End", () => {
    test("clicking end session returns to initial state", async () => {
      renderVoiceAgent();

      fireEvent.click(await screen.findByRole("button", { name: /start conversation/i }));

      const endButton = await screen.findByRole("button", { name: /end voice session/i });
      fireEvent.click(endButton);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /start conversation/i })).toBeInTheDocument();
      });
    });

    test("ending session cancels speech synthesis", async () => {
      renderVoiceAgent();

      fireEvent.click(await screen.findByRole("button", { name: /start conversation/i }));

      const endButton = await screen.findByRole("button", { name: /end voice session/i });
      fireEvent.click(endButton);

      expect(mockSpeechSynthesis.cancel).toHaveBeenCalled();
    });
  });

  describe("Accessibility", () => {
    test("start button is a proper button element", async () => {
      renderVoiceAgent();

      expect((await screen.findByRole("button", { name: /start conversation/i })).tagName).toBe("BUTTON");
    });

    test("shows status during session", async () => {
      const { container } = renderVoiceAgent();

      fireEvent.click(await screen.findByRole("button", { name: /start conversation/i }));

      await waitFor(() => {
        expect(container.querySelector(".voice-energy-orb")).not.toBeInTheDocument();
        expect(screen.getByTestId("voice-mode-surface")).toBeInTheDocument();
      });
    });
  });

  describe("UI Elements", () => {
    test("keeps idle UI free of decorative animation", async () => {
      const { container } = renderVoiceAgent();

      await waitFor(() => {
        expect(container.querySelector(".voice-energy-orb")).not.toBeInTheDocument();
        expect(screen.getByTestId("voice-mode-surface")).toBeInTheDocument();
      });
    });
  });
});

describe("VoiceAgent Speech Integration", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    speechRecognitionInstances.length = 0;
    mockGetUserMedia.mockResolvedValue(createMockStream());
    mockFetch.mockRejectedValue(new Error("offline"));
    global.fetch = mockFetch as unknown as typeof fetch;
    Object.defineProperty(window, "SpeechRecognition", {
      configurable: true,
      value: MockSpeechRecognition,
      writable: true,
    });
    Object.defineProperty(window, "webkitSpeechRecognition", {
      configurable: true,
      value: MockSpeechRecognition,
      writable: true,
    });
    localStorage.setItem("access_token", "test-token");
    userVar({ isLoggedIn: true, userData: { userId: "user-1", email: "hello@manifeststartup.com" } });
  });

  test("starts speech recognition immediately on session start without opening TTS", async () => {
    renderVoiceAgent();

    fireEvent.click(await screen.findByRole("button", { name: /start conversation/i }));

    await waitFor(() => {
      expect(mockSpeechRecognition).toHaveBeenCalled();
    });

    expect(mockSpeechSynthesis.speak).not.toHaveBeenCalled();
  });

  test("falls back to recorded transcription when browser speech recognition is unavailable", async () => {
    Object.defineProperty(window, "SpeechRecognition", {
      configurable: true,
      value: undefined,
      writable: true,
    });
    Object.defineProperty(window, "webkitSpeechRecognition", {
      configurable: true,
      value: undefined,
      writable: true,
    });

    renderVoiceAgent();

    fireEvent.click(await screen.findByRole("button", { name: /start conversation/i }));

    await waitFor(() => {
      expect(mockSpeechSynthesis.speak).not.toHaveBeenCalled();
      expect(mockGetUserMedia).toHaveBeenCalled();
      expect(mockMediaRecorder).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByText(/recording your answer and will transcribe it/i)).toBeInTheDocument();
    });
  });

  test("executes app commands directly from the transcript before calling the idea strategist", async () => {
    window.history.replaceState({}, "", "/ideas");
    renderVoiceAgent();

    fireEvent.click(await screen.findByRole("button", { name: /start conversation/i }));

    await waitFor(() => {
      expect(mockSpeechRecognition).toHaveBeenCalled();
    });

    const recognition = speechRecognitionInstances[0] as MockSpeechRecognition;

    await act(async () => {
      recognition.onresult?.({
        resultIndex: 0,
        results: [
          {
            0: { transcript: "Open account" },
            isFinal: true,
            length: 1,
          },
        ],
      } as unknown as Event);
    });

    await waitFor(() => {
      expect(screen.getByText(/opening account/i)).toBeInTheDocument();
    });

    expect(window.location.pathname).toBe("/account");
    expect(mockSpeechSynthesis.speak).toHaveBeenCalledTimes(1);
  });
});
