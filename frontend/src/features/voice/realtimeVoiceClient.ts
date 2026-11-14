/**
 * Low-level WebRTC connector for OpenAI's Realtime (speech-to-speech) API.
 *
 * The browser connects directly to OpenAI for the lowest latency and native
 * barge-in. Authentication uses a short-lived ephemeral client secret minted
 * server-side (see backend realtime_voice_service) — the platform API key is
 * never exposed to the browser.
 *
 * Flow: create RTCPeerConnection → attach mic track → open the `oai-events`
 * data channel → POST our SDP offer to the Realtime endpoint with the
 * ephemeral secret → apply the SDP answer. Remote audio is piped to the
 * supplied <audio> element.
 */

export interface RealtimeConnectOptions {
  clientSecret: string;
  model: string;
  baseUrl?: string;
  micStream: MediaStream;
  audioEl: HTMLAudioElement;
  onEvent: (event: Record<string, unknown>) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: unknown) => void;
}

export interface RealtimeConnection {
  /** Send a client event over the data channel (e.g. response.create). */
  sendEvent: (event: Record<string, unknown>) => void;
  /** Mute/unmute the outgoing mic track without tearing down the connection. */
  setMicEnabled: (enabled: boolean) => void;
  /** Cancel the assistant's in-flight spoken response (manual interrupt). */
  interrupt: () => void;
  close: () => void;
}

const DEFAULT_REALTIME_BASE_URL = 'https://api.openai.com/v1/realtime';

function isRtcSupported(): boolean {
  return typeof window !== 'undefined' && typeof window.RTCPeerConnection !== 'undefined';
}

export async function connectRealtimeVoice(
  options: RealtimeConnectOptions,
): Promise<RealtimeConnection> {
  const { clientSecret, model, micStream, audioEl, onEvent, onOpen, onClose, onError } = options;
  const baseUrl = options.baseUrl || DEFAULT_REALTIME_BASE_URL;

  if (!isRtcSupported()) {
    throw new Error('Realtime voice requires WebRTC, which is unavailable in this browser.');
  }
  if (!clientSecret) {
    throw new Error('Realtime voice is missing an ephemeral session secret.');
  }

  const pc = new RTCPeerConnection();
  let dataChannel: RTCDataChannel | null = null;
  let closed = false;

  const close = () => {
    if (closed) {
      return;
    }
    closed = true;
    try {
      dataChannel?.close();
    } catch {
      /* ignore */
    }
    try {
      pc.getSenders().forEach(sender => sender.track?.stop());
    } catch {
      /* ignore */
    }
    try {
      pc.close();
    } catch {
      /* ignore */
    }
    onClose?.();
  };

  pc.ontrack = event => {
    const [remoteStream] = event.streams;
    if (remoteStream) {
      audioEl.srcObject = remoteStream;
      void audioEl.play?.().catch(() => undefined);
    }
  };

  pc.onconnectionstatechange = () => {
    if (pc.connectionState === 'failed' || pc.connectionState === 'closed') {
      close();
    }
  };

  // Outgoing microphone audio.
  micStream.getAudioTracks().forEach(track => pc.addTrack(track, micStream));

  dataChannel = pc.createDataChannel('oai-events');
  dataChannel.onopen = () => onOpen?.();
  dataChannel.onmessage = message => {
    try {
      onEvent(JSON.parse(message.data));
    } catch (error) {
      onError?.(error);
    }
  };

  const sendEvent = (event: Record<string, unknown>) => {
    if (dataChannel && dataChannel.readyState === 'open') {
      dataChannel.send(JSON.stringify(event));
    }
  };

  try {
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    const response = await fetch(`${baseUrl}?model=${encodeURIComponent(model)}`, {
      method: 'POST',
      body: offer.sdp,
      headers: {
        Authorization: `Bearer ${clientSecret}`,
        'Content-Type': 'application/sdp',
        'OpenAI-Beta': 'realtime=v1',
      },
    });

    if (!response.ok) {
      throw new Error(`Realtime SDP exchange failed: ${response.status}`);
    }

    const answerSdp = await response.text();
    await pc.setRemoteDescription({ type: 'answer', sdp: answerSdp });
  } catch (error) {
    close();
    throw error;
  }

  return {
    sendEvent,
    setMicEnabled: (enabled: boolean) => {
      micStream.getAudioTracks().forEach(track => {
        track.enabled = enabled;
      });
    },
    interrupt: () => sendEvent({ type: 'response.cancel' }),
    close,
  };
}
