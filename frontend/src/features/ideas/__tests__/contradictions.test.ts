import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";

import { ContradictionHighlight, contradictionBetween, findContradictions } from "../knowledge/contradictions";

describe("contradictions in a shared note", () => {
  it.each([
    ["Each room holds 400 crates.", "A cold room holds 250 crates.", "400 crates vs 250 crates"],
    ["The fee is $5 per crate per day.", "The fee per crate is $8 a day.", "$5 vs $8"],
    ["Farmers rent the cold room by the crate.", "Farmers buy the cold room outright.", "rent vs buy"],
    ["Cold rooms for smallholder farmers, rented by the crate.", "Farmers buy the cold room outright.", "rent vs buy"],
    ["Customers pay a monthly subscription for the app.", "Customers pay a yearly subscription for the app.", "monthly vs yearly"],
  ])("flags %s ↔ %s", (a, b, reason) => {
    expect(contradictionBetween(a, b)).toBe(reason);
  });

  it("flags a statement and its denial", () => {
    expect(contradictionBetween("The cold room needs grid power.", "The cold room does not need grid power.")).toMatch(/isn't/);
  });

  it.each([
    ["Each room holds 400 crates.", "Farmers lose a third of their harvest."], // different subjects
    ["Each room holds 400 crates.", "Each room holds 400 crates of mangoes."], // agree
    ["Pricing is per crate per day.", "Payment is by mobile money."],
  ])("leaves %s ↔ %s alone", (a, b) => {
    expect(contradictionBetween(a, b)).toBeNull();
  });

  it("highlights both sentences in the editor only when the note is shared", () => {
    let shared = false;
    const element = document.createElement("div");
    const editor = new Editor({
      element,
      extensions: [StarterKit, ContradictionHighlight.configure({ enabled: () => shared })],
      content: "<p>Each room holds 400 crates. Pricing is per crate.</p><p>A cold room holds 250 crates.</p>",
    });
    expect(element.querySelectorAll(".manifest-contradiction")).toHaveLength(0);
    shared = true;
    editor.commands.insertContentAt(editor.state.doc.content.size, "<p>Payment is by mobile money.</p>");
    const marked = [...element.querySelectorAll(".manifest-contradiction")];
    expect(marked.map(m => m.textContent)).toEqual(["Each room holds 400 crates.", "A cold room holds 250 crates."]);
    expect(marked[0].getAttribute("title")).toBe("Disagrees with “A cold room holds 250 crates.” (400 crates vs 250 crates)");
    expect(findContradictions(editor.state.doc)).toHaveLength(1);
    editor.destroy();
  });
});
