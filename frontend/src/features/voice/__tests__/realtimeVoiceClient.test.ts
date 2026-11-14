import { connectRealtimeVoice } from "../realtimeVoiceClient";

interface FakeChannel {
  readyState: string;
  onopen: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  send: jest.Mock;
  close: jest.Mock;
}

class FakeRTCPeerConnection {
  static lastInstance: FakeRTCPeerConnection | null = null;

  ontrack: ((event: { streams: MediaStream[] }) => void) | null = null;
  onconnectionstatechange: (() => void) | null = null;
  connectionState = "connected";
  channel: FakeChannel | null = null;
  localDescription: unknown = null;
  remoteDescription: unknown = null;
  tracks: unknown[] = [];

  constructor() {
    FakeRTCPeerConnection.lastInstance = this;
  }

  addTrack(track: unknown) {
    this.tracks.push(track);
  }

  createDataChannel(): FakeChannel {
    this.channel = {
      readyState: "open",
      onopen: null,
      onmessage: null,
      send: jest.fn(),
      close: jest.fn(),
    };
    return this.channel;
  }

  async createOffer() {
    return { type: "offer", sdp: "OFFER_SDP" };
  }

  async setLocalDescription(desc: unknown) {
    this.localDescription = desc;
  }

  async setRemoteDescription(desc: unknown) {
    this.remoteDescription = desc;
  }

  getSenders() {
    return this.tracks.map(track => ({ track }));
  }

  close = jest.fn();
}

const makeMicStream = () =>
  ({
    getAudioTracks: () => [{ enabled: true, stop: jest.fn() }],
  }) as unknown as MediaStream;

const makeAudioEl = () =>
  ({ srcObject: null, play: jest.fn(() => Promise.resolve()) }) as unknown as HTMLAudioElement;

describe("connectRealtimeVoice", () => {
  const originalRtc = (window as { RTCPeerConnection?: unknown }).RTCPeerConnection;
  const originalFetch = global.fetch;

  beforeEach(() => {
    FakeRTCPeerConnection.lastInstance = null;
    (window as unknown as { RTCPeerConnection: unknown }).RTCPeerConnection =
      FakeRTCPeerConnection as unknown;
    global.fetch = jest.fn(() =>
      Promise.resolve({ ok: true, text: () => Promise.resolve("ANSWER_SDP") }),
    ) as unknown as typeof fetch;
  });

  afterEach(() => {
    (window as unknown as { RTCPeerConnection: unknown }).RTCPeerConnection = originalRtc;
    global.fetch = originalFetch;
    jest.clearAllMocks();
  });

  it("performs the SDP handshake with the ephemeral secret and resolves a handle", async () => {
    const onOpen = jest.fn();
    const connection = await connectRealtimeVoice({
      clientSecret: "ek_secret",
      model: "gpt-4o-realtime-preview",
      micStream: makeMicStream(),
      audioEl: makeAudioEl(),
      onEvent: jest.fn(),
      onOpen,
    });

    const fetchMock = global.fetch as jest.Mock;
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("model=gpt-4o-realtime-preview");
    expect(init.headers.Authorization).toBe("Bearer ek_secret");
    expect(init.body).toBe("OFFER_SDP");

    const pc = FakeRTCPeerConnection.lastInstance!;
    expect(pc.remoteDescription).toEqual({ type: "answer", sdp: "ANSWER_SDP" });
    expect(pc.tracks).toHaveLength(1);
    expect(connection).toHaveProperty("sendEvent");
  });

  it("forwards parsed data-channel events and supports sendEvent", async () => {
    const onEvent = jest.fn();
    const connection = await connectRealtimeVoice({
      clientSecret: "ek_secret",
      model: "m",
      micStream: makeMicStream(),
      audioEl: makeAudioEl(),
      onEvent,
    });

    const channel = FakeRTCPeerConnection.lastInstance!.channel!;
    channel.onmessage?.({ data: JSON.stringify({ type: "response.done" }) });
    expect(onEvent).toHaveBeenCalledWith({ type: "response.done" });

    connection.sendEvent({ type: "response.create" });
    expect(channel.send).toHaveBeenCalledWith(JSON.stringify({ type: "response.create" }));

    connection.interrupt();
    expect(channel.send).toHaveBeenCalledWith(JSON.stringify({ type: "response.cancel" }));
  });

  it("throws and cleans up when the SDP exchange fails", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({ ok: false, status: 401, text: () => Promise.resolve("") }),
    ) as unknown as typeof fetch;

    await expect(
      connectRealtimeVoice({
        clientSecret: "ek_secret",
        model: "m",
        micStream: makeMicStream(),
        audioEl: makeAudioEl(),
        onEvent: jest.fn(),
      }),
    ).rejects.toThrow(/SDP exchange failed/);

    expect(FakeRTCPeerConnection.lastInstance!.close).toHaveBeenCalled();
  });

  it("rejects when WebRTC is unavailable", async () => {
    (window as unknown as { RTCPeerConnection: unknown }).RTCPeerConnection = undefined;
    await expect(
      connectRealtimeVoice({
        clientSecret: "ek_secret",
        model: "m",
        micStream: makeMicStream(),
        audioEl: makeAudioEl(),
        onEvent: jest.fn(),
      }),
    ).rejects.toThrow(/WebRTC/);
  });
});
