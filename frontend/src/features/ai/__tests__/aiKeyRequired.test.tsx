import React from "react";
import { act, render } from "@testing-library/react";

import AiKeyRequiredNotice from "../AiKeyRequiredNotice";
import { AI_KEY_SETTINGS_PATH, announceAiKeyRequired, isAiKeyRequiredMessage } from "../aiKeyRequired";
import { MessageContext } from "features/notifications/context/MessageContext";

describe("AI key required notice", () => {
  it("recognises the backend's missing-key message only", () => {
    expect(isAiKeyRequiredMessage("Add your OpenAI API key in Account → AI settings to use AI features.")).toBe(true);
    expect(isAiKeyRequiredMessage("Invalid email or password")).toBe(false);
    expect(isAiKeyRequiredMessage(undefined)).toBe(false);
  });

  it("shows a banner that links to the key settings", () => {
    const setMessage = jest.fn();
    render(
      <MessageContext.Provider value={{ message: { text: null, type: "info" }, setMessage, clearMessage: jest.fn() }}>
        <AiKeyRequiredNotice />
      </MessageContext.Provider>,
    );
    act(() => announceAiKeyRequired());
    expect(setMessage).toHaveBeenCalledWith(
      expect.stringContaining("your own OpenAI API key"),
      "info",
      expect.any(Number),
      { url: AI_KEY_SETTINGS_PATH, label: "Add your key" },
    );
  });
});
