import React from "react";
import { act, render, waitFor } from "@testing-library/react";
import TextArea from "features/common-ui/TextArea";
import { readNoteCursor, requestNoteFocus, saveNoteCursor } from "../utils/noteFocus";

const NOTE = "<p>First paragraph of the note.</p><p>Second paragraph, where I stopped writing.</p>";

describe("where you left off in a note", () => {
  beforeEach(() => localStorage.clear());

  it("keeps a bounded, per-note memory", () => {
    saveNoteCursor("note:a", { anchor: 5, head: 9, scrollTop: 120 });
    expect(readNoteCursor("note:a")).toMatchObject({ anchor: 5, head: 9, scrollTop: 120 });
    expect(readNoteCursor("note:b")).toBeNull();
    localStorage.setItem("manifest.noteCursor.v1", "{broken");
    expect(readNoteCursor("note:a")).toBeNull();
  });

  it("puts the cursor and selection back when the note is focused again", async () => {
    saveNoteCursor("note:x", { anchor: 49, head: 54, scrollTop: 0 });
    const { container } = render(<TextArea value={NOTE} onChange={() => undefined} noteKey="note:x" />);
    await waitFor(() => expect(container.querySelector(".ProseMirror")).not.toBeNull());
    act(() => requestNoteFocus());
    await waitFor(() => {
      const selection = window.getSelection()?.toString();
      expect(selection).toBe("where");
    });
  });
});
