import { InMemoryCache } from "@apollo/client";

import { GET_IDEA, GET_IDEAS } from "features/core/apollo/queries";

import { syncIdeaTitleInCache } from "../syncIdeaTitleCache";

const buildIdeaSummary = (overrides: Record<string, unknown> = {}) => ({
  __typename: "IdeaSummary",
  ideaId: "idea-1",
  userId: "user-1",
  title: "Brand New Idea",
  hasDescription: true,
  description: "Initial description",
  createdAt: "2024-01-01T00:00:00.000Z",
  isPublished: false,
  generatedAssetCount: 0,
  ...overrides,
});

const buildIdeaDetail = (overrides: Record<string, unknown> = {}) => ({
  __typename: "Idea",
  ideaId: "idea-1",
  title: "Brand New Idea",
  description: "Initial description",
  pitchDeck: "",
  productRequirementsDocument: "",
  provisionalPatent: "",
  businessModelCanvas: "",
  similarIdeas: "",
  isPublished: false,
  requiredSkills: [],
  ...overrides,
});

describe("syncIdeaTitleInCache", () => {
  it("updates both the library query and the active idea query immediately", () => {
    const cache = new InMemoryCache();

    cache.writeQuery({
      query: GET_IDEAS,
      data: {
        ideas: [
          buildIdeaSummary(),
          buildIdeaSummary({ ideaId: "idea-2", title: "Second Idea" }),
        ],
      },
    });

    cache.writeQuery({
      query: GET_IDEA,
      variables: { ideaId: "idea-1" },
      data: {
        idea: buildIdeaDetail(),
      },
    });

    syncIdeaTitleInCache(cache, "idea-1", "AquaChain");

    expect(
      cache.readQuery<{ ideas: Array<{ title: string }> }>({
        query: GET_IDEAS,
      })?.ideas[0]?.title
    ).toBe("AquaChain");

    expect(
      cache.readQuery<{ ideas: Array<{ title: string }> }>({
        query: GET_IDEAS,
      })?.ideas[1]?.title
    ).toBe("Second Idea");

    expect(
      cache.readQuery<{ idea: { title: string } }>({
        query: GET_IDEA,
        variables: { ideaId: "idea-1" },
      })?.idea.title
    ).toBe("AquaChain");
  });

  it("does nothing when the cache does not have the idea queries yet", () => {
    const cache = new InMemoryCache();

    expect(() => syncIdeaTitleInCache(cache, "idea-1", "AquaChain")).not.toThrow();
  });
});
