/** Answers are only ever spoken in the natural voice (Kokoro or Cartesia via the bridge). */
import { createBridgeSpeaker, createSilentSpeaker } from '../localAgent';

class FakeContext {
  state = 'running';
  destination = {};
  resume = jest.fn();
  createAnalyser() {
    return { fftSize: 0, connect: jest.fn(), getFloatTimeDomainData: jest.fn() };
  }
  createBuffer(_c: number, length: number) {
    return { length, getChannelData: () => new Float32Array(length) };
  }
  createBufferSource() {
    const source = { buffer: null, connect: jest.fn(), onended: null as null | (() => void), stop: jest.fn(), start: () => setTimeout(() => source.onended?.(), 0) };
    played.push(source);
    return source;
  }
}
const played: unknown[] = [];
const speak = jest.fn();

beforeAll(() => {
  (window as unknown as { AudioContext: unknown }).AudioContext = FakeContext;
  (window as unknown as { speechSynthesis: unknown }).speechSynthesis = { speak, cancel: jest.fn(), getVoices: () => [] };
});

const audio = () => ({
  ok: true,
  headers: { get: () => '24000' },
  arrayBuffer: async () => new Int16Array([1, 2, 3]).buffer,
});

it('waits for a voice that is still loading instead of using the browser voice', async () => {
  jest.useFakeTimers();
  const fetchMock = jest
    .fn()
    .mockResolvedValueOnce({ ok: false, status: 503 })
    .mockRejectedValueOnce(new TypeError('busy'))
    .mockResolvedValue(audio());
  global.fetch = fetchMock as unknown as typeof fetch;
  const speaking: boolean[] = [];
  const speaker = createBridgeSpeaker(on => speaking.push(on));
  speaker.say('Hello there.');
  for (let i = 0; i < 6; i++) await jest.advanceTimersByTimeAsync(2000);
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(played).toHaveLength(1);
  expect(speak).not.toHaveBeenCalled();
  expect(speaking).toEqual([true, false]);
  jest.useRealTimers();
});

it('leaves a piece unspoken rather than reading it in the browser voice', async () => {
  jest.useFakeTimers();
  global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 503 }) as unknown as typeof fetch;
  const speaking: boolean[] = [];
  const speaker = createBridgeSpeaker(on => speaking.push(on));
  speaker.say('Hello again.');
  await jest.advanceTimersByTimeAsync(35000);
  expect(speak).not.toHaveBeenCalled();
  expect(speaking).toEqual([true, false]);
  jest.useRealTimers();
});

it('the text-only speaker never makes a sound', () => {
  const speaker = createSilentSpeaker();
  speaker.say('Shown, not spoken.');
  expect(speaker.speaking).toBe(false);
  expect(speaker.recent).toContain('Shown');
  expect(speak).not.toHaveBeenCalled();
});
