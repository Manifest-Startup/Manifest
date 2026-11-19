import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { findHighlights, SourceHighlight } from "../knowledge/sourceHighlight";
import { sourceTargets } from "../knowledge/sources";
import type { KnowledgeGraph } from "../knowledge/wikiLinks";

const NOTE =
  "<p>Night-shift nurses skip meals because the cafeteria closes at 8pm.</p>" +
  "<p>The app plans meal plans around each nurse’s shift. Meal-plans sync with schedules.</p>";

const graph = {
  ideaId: "n1",
  ideaPath: "Manifest/Ideas/Nurse Meals",
  passages: [
    { id: "p1", kind: "note", text: "Night-shift nurses skip meals because the cafeteria closes at 8pm." },
    { id: "p2", kind: "note", text: "The app plans meal plans around each nurse's shift." },
    { id: "a1", kind: "answer", text: "I've worked nights for six years." },
  ],
  concepts: [
    { label: "meal plan", path: "Manifest/Concepts/Meal Plan", passageIds: ["p2"], documentTypes: [], ideas: [], aliases: ["plan"] },
  ],
  related: [],
  documents: [],
} as KnowledgeGraph;

const textOf = (editor: Editor, ranges: { from: number; to: number }[]) =>
  ranges.map(({ from, to }) => editor.state.doc.textBetween(from, to));

describe("source highlights in the note", () => {
  it("finds a cited sentence even with curly quotes, and a concept in all its forms", () => {
    const editor = new Editor({ extensions: [StarterKit], content: NOTE });
    const cited = findHighlights(editor.state.doc, sourceTargets(graph, new URLSearchParams("cite=p2")));
    expect(textOf(editor, cited)).toEqual(["The app plans meal plans around each nurse’s shift."]);

    const concept = findHighlights(editor.state.doc, sourceTargets(graph, new URLSearchParams("mark=Meal%20Plan")));
    expect(textOf(editor, concept)).toEqual(["meal plans", "Meal-plans"]);
    editor.destroy();
  });

  it("never highlights a one-word fragment or an interview answer inside the note", () => {
    const targets = sourceTargets(graph, new URLSearchParams("cite=a1&mark=Meal%20Plan"));
    expect(targets.map((t) => t.text)).toEqual(["meal plan"]);
  });

  it("decorates without changing the note", () => {
    let targets = sourceTargets(graph, new URLSearchParams("cite=p1"));
    const editor = new Editor({
      extensions: [StarterKit, SourceHighlight.configure({ getTargets: () => targets })],
      content: NOTE,
    });
    const before = editor.getHTML();
    expect(editor.view.dom.querySelectorAll(".manifest-source-mark")).toHaveLength(1);
    expect(editor.getHTML()).toBe(before);
    targets = [];
    editor.commands.insertContentAt(1, "A ");
    expect(editor.view.dom.querySelectorAll(".manifest-source-mark")).toHaveLength(0);
    editor.destroy();
  });
});
