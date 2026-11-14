import { print } from "graphql";

import { GET_IDEA_CORE, GET_IDEA_DOCUMENTS } from "features/core/apollo/queries";

describe("idea workspace performance queries", () => {
  it("loads the editor with core idea fields only", () => {
    const query = print(GET_IDEA_CORE);

    expect(query).toContain("description");
    expect(query).not.toContain("pitchDeck");
    expect(query).not.toContain("productRequirementsDocument");
    expect(query).not.toContain("provisionalPatent");
    expect(query).not.toContain("businessModelCanvas");
  });

  it("keeps generated artifacts in the lazy document payload", () => {
    const query = print(GET_IDEA_DOCUMENTS);

    expect(query).toContain("pitchDeck");
    expect(query).toContain("productRequirementsDocument");
    expect(query).toContain("provisionalPatent");
    expect(query).toContain("businessModelCanvas");
  });
});
