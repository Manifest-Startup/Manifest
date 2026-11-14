import {
  createRealtimeTranscriptState,
  reduceRealtimeEvent,
} from "../realtimeEvents";

describe("reduceRealtimeEvent", () => {
  it("starts idle with no messages", () => {
    const state = createRealtimeTranscriptState();
    expect(state.phase).toBe("idle");
    expect(state.messages).toHaveLength(0);
  });

  it("marks listening when the user starts speaking (native barge-in)", () => {
    const state = reduceRealtimeEvent(createRealtimeTranscriptState(), {
      type: "input_audio_buffer.speech_started",
    });
    expect(state.phase).toBe("listening");
  });

  it("captures a finalized user utterance as a message", () => {
    const state = reduceRealtimeEvent(createRealtimeTranscriptState(), {
      type: "conversation.item.input_audio_transcription.completed",
      transcript: "I want to build a CRM",
    });
    expect(state.phase).toBe("thinking");
    expect(state.messages).toEqual([{ role: "user", content: "I want to build a CRM" }]);
    expect(state.userText).toBe("");
  });

  it("ignores an empty finalized user transcript", () => {
    const state = reduceRealtimeEvent(createRealtimeTranscriptState(), {
      type: "conversation.item.input_audio_transcription.completed",
      transcript: "   ",
    });
    expect(state.messages).toHaveLength(0);
  });

  it("accumulates assistant transcript deltas then commits on done", () => {
    let state = createRealtimeTranscriptState();
    state = reduceRealtimeEvent(state, { type: "response.created" });
    state = reduceRealtimeEvent(state, {
      type: "response.output_audio_transcript.delta",
      delta: "Let's ",
    });
    state = reduceRealtimeEvent(state, {
      type: "response.output_audio_transcript.delta",
      delta: "narrow it.",
    });
    expect(state.phase).toBe("speaking");
    expect(state.assistantText).toBe("Let's narrow it.");

    state = reduceRealtimeEvent(state, {
      type: "response.output_audio_transcript.done",
    });
    expect(state.assistantText).toBe("");
    expect(state.messages).toEqual([{ role: "assistant", content: "Let's narrow it." }]);
  });

  it("supports the legacy response.audio_transcript event names", () => {
    let state = createRealtimeTranscriptState();
    state = reduceRealtimeEvent(state, {
      type: "response.audio_transcript.delta",
      delta: "Hi there",
    });
    state = reduceRealtimeEvent(state, {
      type: "response.audio_transcript.done",
      transcript: "Hi there, founder",
    });
    expect(state.messages).toEqual([{ role: "assistant", content: "Hi there, founder" }]);
  });

  it("returns to idle when the response completes", () => {
    let state = createRealtimeTranscriptState();
    state = reduceRealtimeEvent(state, { type: "response.created" });
    state = reduceRealtimeEvent(state, { type: "response.done" });
    expect(state.phase).toBe("idle");
  });

  it("captures an error message", () => {
    const fromObject = reduceRealtimeEvent(createRealtimeTranscriptState(), {
      type: "error",
      error: { message: "rate limited" },
    });
    expect(fromObject.error).toBe("rate limited");

    const fromString = reduceRealtimeEvent(createRealtimeTranscriptState(), {
      type: "error",
      error: "boom",
    });
    expect(fromString.error).toBe("boom");
  });

  it("ignores unknown event types without mutating state", () => {
    const initial = createRealtimeTranscriptState();
    const next = reduceRealtimeEvent(initial, { type: "something.unhandled" });
    expect(next).toBe(initial);
  });

  it("builds an ordered multi-turn conversation", () => {
    let state = createRealtimeTranscriptState();
    state = reduceRealtimeEvent(state, {
      type: "conversation.item.input_audio_transcription.completed",
      transcript: "Hello",
    });
    state = reduceRealtimeEvent(state, {
      type: "response.output_audio_transcript.done",
      transcript: "Hi, what are we building?",
    });
    expect(state.messages).toEqual([
      { role: "user", content: "Hello" },
      { role: "assistant", content: "Hi, what are we building?" },
    ]);
  });
});
