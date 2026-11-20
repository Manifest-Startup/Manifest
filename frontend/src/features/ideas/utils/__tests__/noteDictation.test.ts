import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";

import {
  DictationHighlight,
  joinToPrevious,
  onDictationTargetChange,
  registerDictationTarget,
  startDictation,
} from "../noteDictation";

function makeEditor(html = "<p>Cold chain</p>") {
  const element = document.createElement("div");
  document.body.appendChild(element);
  return new Editor({ element, extensions: [StarterKit, DictationHighlight], content: html });
}

describe("note dictation", () => {
  it("joins sentences with exactly one space", () => {
    expect(joinToPrevious("n", " for  farmers ")).toBe(" for farmers");
    expect(joinToPrevious(" ", "for")).toBe("for");
    expect(joinToPrevious("", "for")).toBe("for");
    expect(joinToPrevious("n", "   ")).toBe("");
  });

  it("writes interim words in place, then the final sentence, at the cursor", () => {
    const editor = makeEditor();
    const stop = registerDictationTarget(editor);
    editor.commands.setTextSelection(editor.state.doc.content.size - 1); // end of "Cold chain"
    const writer = startDictation()!;

    writer.interim("for solar");
    expect(editor.getText()).toBe("Cold chain for solar");
    expect(editor.view.dom.querySelector(".manifest-dictation-interim")?.textContent).toBe(" for solar");

    writer.interim("for solar farmers");
    writer.commit("For solar farmers.");
    expect(editor.getText()).toBe("Cold chain For solar farmers.");
    expect(editor.view.dom.querySelector(".manifest-dictation-interim")).toBeNull();

    writer.commit("Next one.");
    expect(editor.getText()).toBe("Cold chain For solar farmers. Next one.");
    writer.end();
    writer.commit("ignored");
    expect(editor.getText()).toBe("Cold chain For solar farmers. Next one.");
    stop();
    editor.destroy();
  });

  it("follows edits made elsewhere in the note while dictating", () => {
    const editor = makeEditor("<p>B</p>");
    const stop = registerDictationTarget(editor);
    editor.commands.setTextSelection(2);
    const writer = startDictation()!;
    writer.interim("hello");
    editor.commands.insertContentAt(1, "A "); // someone types before us
    writer.commit("Hello.");
    expect(editor.getText()).toBe("A B Hello.");
    writer.end();
    stop();
    editor.destroy();
  });

  it("only offers a writer while a note is registered", () => {
    const seen: boolean[] = [];
    const off = onDictationTargetChange((available) => seen.push(available));
    expect(startDictation()).toBeNull();
    const editor = makeEditor();
    const stop = registerDictationTarget(editor);
    stop();
    expect(seen).toEqual([false, true, false]);
    off();
    editor.destroy();
  });
});
