import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { MarkdownDisplay } from "../components/display/MarkdownDisplay";
import { WikiLinksProvider } from "../knowledge/WikiLinkContext";
import { makeResolver, type KnowledgeGraph } from "../knowledge/wikiLinks";

const stored = "# PRD\n\nCheap sensors warn coastal streets early.";
const graph: KnowledgeGraph = {
  ideaId: "i1",
  ideaPath: "Manifest/Ideas/TideLine",
  passages: [{ id: "p1", kind: "note", text: "Coastal streets flood block by block." }],
  concepts: [],
  related: [],
  documents: [
    {
      documentType: "product_requirements_document",
      markdown:
        "# PRD\n\nCheap [[Manifest/Concepts/Sensor|sensors]] warn coastal streets early. [[Manifest/Ideas/TideLine#^p1|↩]]",
    },
  ],
};

const renderDoc = (value: { graph?: KnowledgeGraph | null }) =>
  render(
    <MemoryRouter>
      <WikiLinksProvider value={{ graph: value.graph, resolve: makeResolver(value.graph) }}>
        <MarkdownDisplay
          content={stored}
          fallbackMessage="none"
          variant="prd"
          documentType="product_requirements_document"
        />
      </WikiLinksProvider>
    </MemoryRouter>,
  );

describe("cited documents in the app", () => {
  it("shows citations back to the idea note and concept links", () => {
    renderDoc({ graph });
    const cite = screen.getByRole("link", { name: /Source, your idea note/ });
    expect(cite).toHaveAttribute("href", "/ideas/i1/description?cite=p1");
    expect(cite).toHaveTextContent("p1");
    expect(screen.getByRole("link", { name: "sensors" })).toHaveAttribute(
      "href",
      "/ideas/i1/knowledge-graph?concept=Sensor",
    );
  });

  it("never shows raw [[brackets]], even without a graph", () => {
    render(
      <MemoryRouter>
        <MarkdownDisplay content={"See [[Manifest/Ideas/TideLine|TideLine]]."} fallbackMessage="none" />
      </MemoryRouter>,
    );
    expect(screen.getByText(/See TideLine\./)).toBeInTheDocument();
    expect(screen.queryByText(/\[\[/)).toBeNull();
  });
});
