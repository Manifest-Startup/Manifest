import React from "react";
import { render, screen, within } from "@testing-library/react";
import { MarkdownDisplay } from "../MarkdownDisplay";
import {
  CostStructureDisplay,
  extractCostStructure,
} from "../CostStructureDisplay";

describe("standard document formats", () => {
  it("renders PRD requirements as a real table and preserves every introductory paragraph", () => {
    render(
      <MarkdownDisplay
        variant="prd"
        title="Product Requirements Document"
        fallbackMessage="Empty"
        content={`# Product Requirements Document
A full introduction that must be preserved.

Second paragraph with a decision.

## Functional Requirements
| ID | Requirement | Priority | Acceptance criteria |
| --- | --- | --- | --- |
| FR-001 | Save a note | Must | Reload shows saved text |

## Risks
Needs user validation.`}
      />,
    );
    expect(
      screen.getByText("Second paragraph with a decision."),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("table")).getByRole("cell", { name: "FR-001" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Acceptance criteria" }),
    ).toBeInTheDocument();
  });

  it("keeps repeated headings addressable and fenced headings out of the contents", () => {
    const { container } = render(
      <MarkdownDisplay
        fallbackMessage="Empty"
        content={
          "# Draft\n## Scope\nOne\n\n```md\n# Example only\n```\n\n## Scope\nTwo"
        }
      />,
    );
    const anchors = within(
      screen.getByRole("navigation", {
        name: "Document contents",
        hidden: true,
      }),
    ).getAllByRole("link", { hidden: true });
    expect(anchors).toHaveLength(2);
    const targets = anchors.map((link) => link.getAttribute("href")!.slice(1));
    expect(new Set(targets).size).toBe(2);
    targets.forEach((id) =>
      expect(
        Array.from(container.querySelectorAll("[id]")).some(
          (node) => node.id === id,
        ),
      ).toBe(true),
    );
  });

  it("preserves worksheet cadence, unknowns, currency and notes without merging unlike totals", () => {
    render(
      <CostStructureDisplay
        cost={
          "Currency: EUR. Planning horizon: 3 months (assumption).\n\n| Cost driver | Estimate | Cadence | Basis |\n| --- | --- | --- | --- |\n| Hosting | €30 | Monthly | Illustrative |\n| Tooling | TBD | One-time | Quote needed |\n\nOne-time subtotal incomplete."
        }
      />,
    );
    expect(
      screen.getByRole("columnheader", { name: "Cadence" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Monthly" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "TBD" })).toBeInTheDocument();
    expect(
      screen.getByText("One-time subtotal incomplete."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Currency: EUR/)).toBeInTheDocument();
  });

  it("extracts only cost content regardless of the next canvas block order", () => {
    expect(
      extractCostStructure(
        "# Cost Structure\nMVP assumptions\n## Monthly\nHosting\n# Key Partners\nPrivate partner note",
      ),
    ).toBe("MVP assumptions\n## Monthly\nHosting");
  });
});
