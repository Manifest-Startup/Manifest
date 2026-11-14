import { __resetVoiceMicForTests, acquireVoiceMic, releaseVoiceMic } from "../voiceMicStream";

interface MockTrack {
  stop: jest.Mock;
}

interface MockStream {
  tracks: MockTrack[];
  getTracks: () => MockTrack[];
}

interface MockContext {
  state: AudioContextState;
  resume: jest.Mock;
  close: jest.Mock;
}

const buildMockStream = (): MockStream => {
  const tracks: MockTrack[] = [{ stop: jest.fn() }];
  return { tracks, getTracks: () => tracks };
};

const buildMockContext = (): MockContext => ({
  state: "running",
  resume: jest.fn(() => Promise.resolve()),
  close: jest.fn(() => Promise.resolve()),
});

describe("voiceMicStream", () => {
  let mockGetUserMedia: jest.Mock;
  let activeStreams: MockStream[];
  let activeContexts: MockContext[];
  let originalGetUserMedia: MediaDevices["getUserMedia"] | undefined;
  let originalAudioContext: typeof AudioContext | undefined;

  beforeEach(() => {
    activeStreams = [];
    activeContexts = [];
    mockGetUserMedia = jest.fn(async () => {
      const stream = buildMockStream();
      activeStreams.push(stream);
      return stream as unknown as MediaStream;
    });

    if (!window.navigator.mediaDevices) {
      Object.defineProperty(window.navigator, "mediaDevices", {
        configurable: true,
        value: {},
        writable: true,
      });
    }
    originalGetUserMedia = window.navigator.mediaDevices.getUserMedia?.bind(window.navigator.mediaDevices);
    Object.defineProperty(window.navigator.mediaDevices, "getUserMedia", {
      configurable: true,
      value: mockGetUserMedia,
      writable: true,
    });

    originalAudioContext = window.AudioContext;
    const ContextCtor = jest.fn(() => {
      const ctx = buildMockContext();
      activeContexts.push(ctx);
      return ctx as unknown as AudioContext;
    });
    Object.defineProperty(window, "AudioContext", {
      configurable: true,
      value: ContextCtor,
      writable: true,
    });

    __resetVoiceMicForTests();
  });

  afterEach(() => {
    if (originalGetUserMedia) {
      Object.defineProperty(window.navigator.mediaDevices, "getUserMedia", {
        configurable: true,
        value: originalGetUserMedia,
        writable: true,
      });
    }
    if (originalAudioContext) {
      Object.defineProperty(window, "AudioContext", {
        configurable: true,
        value: originalAudioContext,
        writable: true,
      });
    }
    __resetVoiceMicForTests();
  });

  test("two acquires share one MediaStream and one AudioContext", async () => {
    const a = await acquireVoiceMic();
    const b = await acquireVoiceMic();

    expect(mockGetUserMedia).toHaveBeenCalledTimes(1);
    expect(activeStreams).toHaveLength(1);
    expect(activeContexts).toHaveLength(1);
    expect(a.stream).toBe(b.stream);
    expect(a.context).toBe(b.context);
  });

  test("releases stream + context only when refcount hits zero", async () => {
    await acquireVoiceMic();
    await acquireVoiceMic();

    releaseVoiceMic();

    expect(activeStreams[0]?.tracks[0]?.stop).not.toHaveBeenCalled();
    expect(activeContexts[0]?.close).not.toHaveBeenCalled();

    releaseVoiceMic();

    expect(activeStreams[0]?.tracks[0]?.stop).toHaveBeenCalledTimes(1);
    expect(activeContexts[0]?.close).toHaveBeenCalledTimes(1);
  });

  test("acquire after full release re-creates the stream", async () => {
    await acquireVoiceMic();
    releaseVoiceMic();

    await acquireVoiceMic();

    expect(mockGetUserMedia).toHaveBeenCalledTimes(2);
    expect(activeStreams).toHaveLength(2);
  });

  test("concurrent acquires resolve to the same singleton", async () => {
    const [first, second] = await Promise.all([acquireVoiceMic(), acquireVoiceMic()]);

    expect(mockGetUserMedia).toHaveBeenCalledTimes(1);
    expect(first.stream).toBe(second.stream);

    releaseVoiceMic();
    expect(activeStreams[0]?.tracks[0]?.stop).not.toHaveBeenCalled();

    releaseVoiceMic();
    expect(activeStreams[0]?.tracks[0]?.stop).toHaveBeenCalledTimes(1);
  });
});
