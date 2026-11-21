import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";
import { BrowserRouter } from "react-router-dom";

import { userVar } from "../../core/apollo/localState";
import { GET_IDEAS } from "../../core/apollo/queries";
import FloatingVoiceButton from "../FloatingVoiceButton";
import { VOICE_FULL_AUTO_OPEN_SESSION_KEY, VOICE_MODE_STORAGE_KEY } from "../voiceLandingStorage";
import * as voiceAgentApi from "../voiceAgentApi";

const mockFetch = jest.fn();

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useLocation: () => ({ pathname: "/ideas" }),
  useNavigate: () => mockNavigate,
}));

const mockSpeechSynthesis = {
  cancel: jest.fn(),
  getVoices: jest.fn().mockReturnValue([]),
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

global.SpeechSynthesisUtterance = jest.fn().mockImplementation(() => ({
  onend: null,
  onerror: null,
  onstart: null,
  pitch: 1,
  rate: 1,
  voice: null,
  volume: 1,
}));

const mocks = [
  {
    request: { query: GET_IDEAS },
    result: { data: { ideas: [] } },
  },
];

const renderComponent = (isLoggedIn = true) => {
  userVar({ isLoggedIn, userData: isLoggedIn ? { id: "user-1" } : null });

  return render(
    <MockedProvider addTypename={false} mocks={mocks}>
      <BrowserRouter>
        <FloatingVoiceButton />
      </BrowserRouter>
    </MockedProvider>,
  );
};

describe("FloatingVoiceButton Component", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    speechRecognitionInstances.length = 0;
    window.sessionStorage.clear();
    window.localStorage.removeItem(VOICE_MODE_STORAGE_KEY);
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
    userVar({ isLoggedIn: true, userData: { id: "user-1" } });
  });

  test("auto-opens voice once per tab session when manifest_voice_mode is full on /ideas", async () => {
    window.localStorage.setItem(VOICE_MODE_STORAGE_KEY, "full");

    const postSpy = jest.spyOn(voiceAgentApi, "postVoiceAgentJson").mockResolvedValue({
      messages: [],
      response: { message: "", is_qualified: false },
    } as never);

    renderComponent(true);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /close voice mode/i })).toBeInTheDocument();
    });

    expect(window.sessionStorage.getItem(VOICE_FULL_AUTO_OPEN_SESSION_KEY)).toBe("1");
    expect(postSpy).toHaveBeenCalled();
    const startCalls = postSpy.mock.calls.filter(call => String(call[0]).includes("/api/voice-agent/start"));
    expect(startCalls.length).toBeGreaterThan(0);
    postSpy.mockRestore();
  });

  test("workspace control switches to standard mode and closes overlay", async () => {
    window.localStorage.setItem(VOICE_MODE_STORAGE_KEY, "full");

    renderComponent(true);

    await screen.findByRole("button", { name: /close voice mode/i });

    // The engine probe and session start are async; wait for the live session controls.
    fireEvent.click(await screen.findByRole("button", { name: /session details/i }));
    const workspaceButton = screen.getByRole("button", {
      name: /continue in workspace without voice next time/i,
    });
    fireEvent.click(workspaceButton);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /start voice conversation/i })).toBeInTheDocument();
    });

    expect(window.localStorage.getItem(VOICE_MODE_STORAGE_KEY)).toBe("standard");
    expect(window.sessionStorage.getItem(VOICE_FULL_AUTO_OPEN_SESSION_KEY)).toBeNull();
  });

  describe("Visibility", () => {
    test("renders floating button when user is logged in", () => {
      renderComponent(true);

      expect(screen.getByRole("button", { name: /start voice conversation/i })).toBeInTheDocument();
    });

    test("does not render when user is not logged in", () => {
      renderComponent(false);

      expect(screen.queryByRole("button", { name: /start voice conversation/i })).not.toBeInTheDocument();
    });
  });

  describe("Button Styling", () => {
    test("has proper fixed positioning classes", () => {
      renderComponent();

      const button = screen.getByRole("button", { name: /start voice conversation/i });
      expect(button).toHaveClass("fixed", "manifest-voice-launcher");
      expect(button.className).toMatch(/bottom-\[max/);
      expect(button.className).toMatch(/end-\[max|sm:end-6/);
    });

    test("uses a simple microphone launcher", () => {
      const { container } = renderComponent();

      expect(container.querySelector(".voice-launcher__orb")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /start voice conversation/i })).toHaveTextContent("Voice");
    });
  });

  describe("Overlay Interaction", () => {
    test("opens compact panel when button is clicked", async () => {
      renderComponent();

      fireEvent.click(screen.getByRole("button", { name: /start voice conversation/i }));

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /close voice mode/i })).toBeInTheDocument();
      });
    });

    test("keeps the overlay shell click-through outside the panel", async () => {
      renderComponent();

      fireEvent.click(screen.getByRole("button", { name: /start voice conversation/i }));

      const overlayShell = await screen.findByTestId("voice-mode-overlay-shell");
      expect(overlayShell).toHaveClass("pointer-events-none");
    });

    test("shows session details control in overlay", async () => {
      renderComponent();

      fireEvent.click(screen.getByRole("button", { name: /start voice conversation/i }));

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /session details/i })).toBeInTheDocument();
      });
    });

    test("ending a minimized session shows the start action again", async () => {
      renderComponent();
      fireEvent.click(screen.getByRole("button", { name: /start voice conversation/i }));
      fireEvent.click(await screen.findByRole("button", { name: "Minimize voice panel" }));
      fireEvent.click(screen.getByRole("button", { name: "End", exact: true }));
      expect(await screen.findByRole("button", { name: "Start conversation" })).toBeInTheDocument();
    });

    test("closes overlay when close button is clicked", async () => {
      renderComponent();

      fireEvent.click(screen.getByRole("button", { name: /start voice conversation/i }));

      const closeButton = await screen.findByRole("button", { name: /close voice mode/i });
      fireEvent.click(closeButton);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /start voice conversation/i })).toBeInTheDocument();
      });
    });

    test("closes overlay on escape", async () => {
      renderComponent();

      fireEvent.click(screen.getByRole("button", { name: /start voice conversation/i }));

      await screen.findByRole("button", { name: /close voice mode/i });
      fireEvent.keyDown(window, { key: "Escape" });

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /start voice conversation/i })).toBeInTheDocument();
      });
    });
  });

});

describe("FloatingVoiceButton Speech Integration", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    speechRecognitionInstances.length = 0;
    window.sessionStorage.clear();
    window.localStorage.removeItem(VOICE_MODE_STORAGE_KEY);
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
    userVar({ isLoggedIn: true, userData: { id: "user-1" } });
  });

  test("starts listening when overlay opens without opening TTS", async () => {
    renderComponent();

    fireEvent.click(screen.getByRole("button", { name: /start voice conversation/i }));

    await waitFor(() => {
      expect(mockSpeechRecognition).toHaveBeenCalled();
    });

    expect(mockSpeechSynthesis.speak).not.toHaveBeenCalled();
  });

  test("pause releases recognition and resume keeps the conversation", async () => {
    const postSpy = jest.spyOn(voiceAgentApi, "postVoiceAgentJson").mockResolvedValue({
      messages: [], response: { message: "", is_qualified: false },
    } as never);
    renderComponent();
    fireEvent.click(screen.getByRole("button", { name: /start voice conversation/i }));
    await waitFor(() => expect(mockSpeechRecognition).toHaveBeenCalled());
    const recognition = speechRecognitionInstances[speechRecognitionInstances.length - 1];
    const starts = postSpy.mock.calls.filter(call => String(call[0]).endsWith("/start")).length;
    fireEvent.click(screen.getByRole("button", { name: /pause voice conversation/i }));
    expect(recognition.abort).toHaveBeenCalled();
    expect(mockSpeechSynthesis.cancel).toHaveBeenCalled();
    expect(screen.getByText("Paused · microphone off")).toBeInTheDocument();
    const recognitions = mockSpeechRecognition.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: /resume voice conversation/i }));
    await waitFor(() => expect(mockSpeechRecognition.mock.calls.length).toBeGreaterThan(recognitions));
    expect(postSpy.mock.calls.filter(call => String(call[0]).endsWith("/start"))).toHaveLength(starts);
    postSpy.mockRestore();
  });

  test("cancels speech when overlay closes", async () => {
    renderComponent();

    fireEvent.click(screen.getByRole("button", { name: /start voice conversation/i }));

    const closeButton = await screen.findByRole("button", { name: /close voice mode/i });
    fireEvent.click(closeButton);

    expect(mockSpeechSynthesis.cancel).toHaveBeenCalled();
  });

  test("falls back to recorded transcription when overlay opens in a browser without speech recognition", async () => {
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

    renderComponent();

    fireEvent.click(screen.getByRole("button", { name: /start voice conversation/i }));

    await waitFor(() => {
      expect(mockSpeechSynthesis.speak).not.toHaveBeenCalled();
      expect(mockGetUserMedia).toHaveBeenCalled();
      expect(mockMediaRecorder).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByText(/recording your answer and will transcribe it/i)).toBeInTheDocument();
    });
  });
});

describe("hasNoteOrb", () => {
  const { hasNoteOrb } = jest.requireActual("../FloatingVoiceButton") as typeof import("../FloatingVoiceButton");
  test("the corner pill steps aside only on an idea's note, where the orb is", () => {
    expect(hasNoteOrb("/ideas/abc123/description")).toBe(true);
    expect(hasNoteOrb("/ideas/abc123")).toBe(true);
    expect(hasNoteOrb("/ideas/abc123/pitch-deck")).toBe(false);
    expect(hasNoteOrb("/ideas/qualify")).toBe(false);
    expect(hasNoteOrb("/ideas")).toBe(false);
  });
});

describe("chooseEngine in a vault (installed Chrome app with a local folder)", () => {
  const { chooseEngine } = jest.requireActual("../FloatingVoiceButton") as typeof import("../FloatingVoiceButton");
  beforeEach(() => jest.requireActual("../liveVoice").forgetLiveVoiceStatus());
  const respond = (status: number, body: unknown = {}) =>
    jest.fn().mockResolvedValue({ status, ok: status < 400, json: async () => body });

  test("uses live voice through the account and never hides voice", async () => {
    global.fetch = respond(200, { available: true }) as unknown as typeof fetch;
    await expect(chooseEngine(false, true)).resolves.toEqual({ kind: "live", blocked: null });
  });

  test("asks to sign in instead of falling back to the cloud-only interview", async () => {
    global.fetch = respond(401) as unknown as typeof fetch;
    const engine = await chooseEngine(false, true);
    expect(engine).toMatchObject({ kind: "live", blocked: { kind: "sign_in" } });
  });
});

describe("chooseEngine without an OpenAI key", () => {
  const { chooseEngine } = jest.requireActual("../FloatingVoiceButton") as typeof import("../FloatingVoiceButton");
  beforeEach(() => jest.requireActual("../liveVoice").forgetLiveVoiceStatus());

  test("uses Claude Code / Codex on this computer when `manifest bridge` runs", async () => {
    Object.defineProperty(window, "speechSynthesis", { configurable: true, value: { getVoices: () => [] } });
    Object.defineProperty(window, "webkitSpeechRecognition", { configurable: true, writable: true, value: class {} });
    global.fetch = jest.fn(async (url: string) =>
      String(url).includes("127.0.0.1")
        ? { ok: true, status: 200, json: async () => ({ ok: true, agent: "Claude Code" }) }
        : { ok: true, status: 200, json: async () => ({ available: false, reason: "no_api_key" }) },
    ) as unknown as typeof fetch;
    await expect(chooseEngine(false, false)).resolves.toEqual({ kind: "local" });
  });

  test("otherwise says how to use a key or a local agent", async () => {
    global.fetch = jest.fn(async (url: string) => {
      if (String(url).includes("127.0.0.1")) throw new TypeError("Failed to fetch");
      return { ok: true, status: 200, json: async () => ({ available: false, reason: "no_api_key" }) };
    }) as unknown as typeof fetch;
    const engine = await chooseEngine(false, false);
    expect(engine).toMatchObject({ kind: "live", blocked: { kind: "no_api_key" } });
    expect((engine as { blocked: { message: string } }).blocked.message).toContain("voice.sh");
  });
});

describe("chooseEngine with the bridge's natural local voice", () => {
  const { chooseEngine } = jest.requireActual("../FloatingVoiceButton") as typeof import("../FloatingVoiceButton");
  beforeEach(() => jest.requireActual("../liveVoice").forgetLiveVoiceStatus());

  test("uses Pipecat on this Mac (Whisper + Kokoro + Claude Code) when the bridge offers it", async () => {
    global.fetch = jest.fn(async (url: string) =>
      String(url).includes("127.0.0.1")
        ? { ok: true, status: 200, json: async () => ({ ok: true, agent: "Claude Code", voice: "ws://127.0.0.1:47822" }) }
        : { ok: true, status: 200, json: async () => ({ available: false, reason: "no_api_key" }) },
    ) as unknown as typeof fetch;
    await expect(chooseEngine(false, false)).resolves.toEqual({ kind: "live", blocked: null, wsUrl: "ws://127.0.0.1:47822" });
  });

  test("ignores a voice address that isn't this computer", async () => {
    global.fetch = jest.fn(async (url: string) =>
      String(url).includes("127.0.0.1")
        ? { ok: true, status: 200, json: async () => ({ ok: true, agent: "x", voice: "wss://evil.example/voice" }) }
        : { ok: true, status: 200, json: async () => ({ available: false, reason: "no_api_key" }) },
    ) as unknown as typeof fetch;
    const engine = await chooseEngine(false, false);
    expect(engine).not.toHaveProperty("wsUrl");
  });
});
