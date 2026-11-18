import {
  citedFor,
  citedPassageId,
  makeResolver,
  stripCitations,
  wikiLinksToMarkdown,
  type KnowledgeGraph,
} from "../knowledge/wikiLinks";

const graph: KnowledgeGraph = {
  ideaId: "i1",
  ideaPath: "Manifest/Ideas/TideLine",
  passages: [{ id: "p1", kind: "note", text: "Coastal streets flood." }],
  concepts: [
    {
      label: "sensor",
      path: "Manifest/Concepts/Sensor",
      passageIds: ["p1"],
      documentTypes: ["pitch_deck"],
      ideas: [{ ideaId: "i2", title: "Sensor Rent", path: "Manifest/Ideas/Sensor Rent", concepts: [] }],
    },
  ],
  related: [],
  documents: [
    {
      documentType: "pitch_deck",
      markdown: "# Slide 1\nCheap [[Manifest/Concepts/Sensor|sensors]] warn streets. [[Manifest/Ideas/TideLine#^p1|↩]]",
    },
  ],
};

describe("wiki links", () => {
  const resolve = makeResolver(graph);

  it("turns citations, concepts, ideas and documents into app routes", () => {
    expect(resolve?.("Manifest/Ideas/TideLine", "^p1")).toBe("/ideas/i1/description?cite=p1");
    expect(resolve?.("Manifest/Ideas/Sensor Rent")).toBe("/ideas/i2/description");
    expect(resolve?.("Manifest/Concepts/Sensor")).toBe("/ideas/i1/knowledge-graph?concept=Sensor");
    expect(resolve?.("Manifest/Documents/TideLine/Pitch Deck")).toBe("/ideas/i1/pitch-deck");
    expect(resolve?.("Manifest/Skills/Sales")).toBeNull();
  });

  it("renders links as Markdown and unresolved ones as plain text", () => {
    expect(wikiLinksToMarkdown("See [[Manifest/Ideas/TideLine#^p1|↩]] and [[Manifest/Skills/Sales|Sales]]", resolve)).toBe(
      "See [↩](</ideas/i1/description?cite=p1>) and Sales",
    );
    expect(wikiLinksToMarkdown("No graph: [[Manifest/Ideas/TideLine|TideLine]]")).toBe("No graph: TideLine");
  });

  it("uses the cited copy only while it matches the stored document", () => {
    const stored = "# Slide 1\nCheap sensors warn streets.";
    expect(stripCitations(graph.documents[0].markdown)).toBe(stored);
    expect(citedFor(graph, "pitch_deck", stored)).toContain("[[Manifest/Ideas/TideLine#^p1|↩]]");
    expect(citedFor(graph, "pitch_deck", stored + "\nEdited.")).toBeNull();
    expect(citedFor(null, "pitch_deck", stored)).toBeNull();
  });

  it("reads the cited passage from a link", () => {
    expect(citedPassageId("/ideas/i1/description?cite=a2")).toBe("a2");
    expect(citedPassageId("/ideas/i1/description")).toBeNull();
  });
});
