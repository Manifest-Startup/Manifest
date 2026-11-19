import React from "react";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { KnowledgeGraphView } from "../knowledge/KnowledgeGraphView";
import type { KnowledgeGraph } from "../knowledge/wikiLinks";

const concept = (label: string, role: string, roleLabel: string, extra: Partial<KnowledgeGraph["concepts"][number]> = {}) => ({
  label,
  path: `Manifest/Concepts/${label.replace(/\b\w/g, (c) => c.toUpperCase())}`,
  passageIds: ["p1"],
  documentTypes: [],
  ideas: [],
  role,
  roleLabel,
  aliases: [],
  parent: null,
  weight: 2,
  why: `You wrote it 2× (p1). About ${label}.`,
  ...extra,
});

const graph: KnowledgeGraph = {
  ideaId: "n1",
  ideaPath: "Manifest/Ideas/Nurse Meals",
  passages: [
    { id: "p1", kind: "note", text: "Night-shift nurses skip meals or eat vending machine food." },
    { id: "p3", kind: "note", text: "Hospitals could pay for meal plans as a staff wellness benefit." },
  ],
  concepts: [
    concept("nurse", "who", "Who it's for"),
    concept("vending machine food", "problem", "Problem"),
    concept("meal plan", "solution", "Solution", { aliases: ["plan"], passageIds: ["p3"] }),
    concept("staff wellness benefit", "business", "Business", { passageIds: ["p3"] }),
    concept("shift", "context", "Context"),
  ],
  relations: [
    { source: "nurse", target: "vending machine food", label: "struggles with", passageIds: ["p1"], weight: 1 },
  ],
  related: [
    {
      ideaId: "s1",
      title: "Sleep coach for shift workers",
      path: "Manifest/Ideas/Sleep coach",
      concepts: ["shift"],
      reason: "Both are about shift (context).",
    },
  ],
  documents: [],
};

const renderAt = (url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/ideas/:id/:aspect" element={<KnowledgeGraphView graph={graph} loading={false} ideaTitle="Nurse Meals" />} />
      </Routes>
    </MemoryRouter>,
  );

describe("knowledge graph view", () => {
  it("sorts concepts into the parts of the idea and lists the connections", () => {
    renderAt("/ideas/n1/knowledge-graph");
    const map = screen.getByRole("img", { name: /Idea map: 4 concepts in 4 parts, 1 connections/ });
    expect(within(map).getByText("Who it's for")).toBeInTheDocument();
    expect(within(map).getByText("Business")).toBeInTheDocument();
    const connects = screen.getByRole("region", { name: "How it connects" });
    expect(within(connects).getByText("struggles with")).toBeInTheDocument();
    expect(within(connects).getByRole("link", { name: "p1" })).toHaveAttribute("href", "/ideas/n1/description?cite=p1");
    expect(screen.getByText("Both are about shift (context).")).toBeInTheDocument();
    expect(screen.getByText("Themes")).toBeInTheDocument();
  });

  it("explains how a selected concept was found and highlights it in the founder's words", () => {
    renderAt("/ideas/n1/knowledge-graph?concept=Meal%20Plan");
    const focus = screen.getByRole("region", { name: "Concept: Meal Plan" });
    expect(within(focus).getByText("Solution")).toBeInTheDocument();
    expect(within(focus).getByText(/You wrote it 2×/)).toBeInTheDocument();
    expect(within(focus).getByText("meal plans", { selector: "mark" })).toBeInTheDocument();
  });
});
