# Supporting document formats

Verified against source guidance on September 12, 2026. These are conventional working formats, not a universal standard shared by every organization.

| Document | Manifest format | Reference |
| --- | --- | --- |
| Business Model Canvas | Nine linked blocks in the conventional canvas arrangement on wide screens; stacked blocks in narrow panels. Concise hypotheses, with missing blocks explicitly marked. | [Strategyzer](https://www.strategyzer.com/library/the-business-model-canvas) |
| Cost Structure | Cost worksheet with currency, planning horizon, estimate, cadence and basis. Separate setup and recurring subtotals. Unknown amounts are TBD, not zero. | [SBA startup costs](https://www.sba.gov/business-guide/plan-your-business/calculate-your-startup-costs) |
| Pitch Deck | Twelve short, widescreen slides covering purpose, problem, solution, timing, market, product, model, distribution, competition, traction, financials/milestones and team/ask. Editable PowerPoint export preserves table headers and empty cells. | [Sequoia](https://sequoiacap.com/article/writing-a-business-plan) |
| Product Requirements Document | Plain working specification with document control, goals/non-goals, users, prioritized requirements, acceptance criteria, measurable quality targets, metrics, dependencies and open decisions. | [Atlassian PRDs](https://www.atlassian.com/agile/product-management/requirements) |
| Provisional Patent | U.S. provisional specification draft with technical disclosure, proposed embodiments, drawing descriptions, optional draft claims and abstract. Letter-size PDF with readable 12-point body text, 1.5 line spacing, page numbers and separate claims/abstract pages. | [USPTO provisional applications](https://www.uspto.gov/patents/basics/apply/provisional-application) |

## Existing documents and generation

The viewer immediately applies the new presentation to saved Markdown. Existing text is preserved, including old cost bullets and JSON. GFM tables render as tables; long tables scroll horizontally inside the document. The contents list is collapsed by default. The canvas layout adapts to its actual panel width, not only the browser width.

Updated prompts apply on the next normal generation or requested regeneration. This release does not regenerate saved documents, overwrite notes or replace previously generated PDFs. Those files keep their existing formatting until explicitly regenerated. No new AI request, model, dependency, or generation trigger is introduced. Outputs continue to use the existing persisted document workflow; opening a document performs no generation call. Deck output is bounded to short slides to reduce visual density and generation volume.

Figures, traction, ownership and filing details must not be fabricated. Estimated costs and targets carry an assumption label; incomplete subtotals remain labeled incomplete. A provisional draft is not a filed application or a complete filing packet. Claims and an abstract are optional for a provisional application. Suggested figure descriptions do not substitute for necessary actual drawings, and cover-sheet placeholders still require review. This update retains the existing U.S. provisional scope.

The adapted Business Model Canvas layout credits Strategyzer and links its CC BY-SA 3.0 license. Canvas adaptations retain that attribution and license.
