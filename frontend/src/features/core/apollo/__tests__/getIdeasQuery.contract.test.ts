import { print } from "graphql";

import { GET_IDEAS } from "features/core/apollo/queries";

describe("GetIdeas query contract", () => {
  it("does not request heavy generated-document fields (list uses IdeaSummary)", () => {
    const doc = print(GET_IDEAS);
    expect(doc).toMatch(/fragment IdeaSummaryFields on IdeaSummary/);
    expect(doc).toMatch(/generatedAssetCount/);
    expect(doc).not.toMatch(/pitchDeck/);
    expect(doc).not.toMatch(/productRequirementsDocument/);
    expect(doc).not.toMatch(/provisionalPatent/);
    expect(doc).not.toMatch(/businessModelCanvas/);
    expect(doc).not.toMatch(/similarIdeas/);
  });
});
