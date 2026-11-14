import { ApolloCache } from "@apollo/client";

import { GET_IDEA, GET_IDEAS } from "features/core/apollo/queries";

interface CachedIdea {
  __typename?: string;
  ideaId: string;
  title: string;
  description?: string | null;
  generatedAssetCount?: number | null;
  pitchDeck?: string | null;
  productRequirementsDocument?: string | null;
  provisionalPatent?: string | null;
  businessModelCanvas?: string | null;
  similarIdeas?: string | null;
  isPublished?: boolean | null;
}

interface CachedIdeasQuery {
  ideas: CachedIdea[];
}

interface CachedIdeaQuery {
  idea: CachedIdea | null;
}

export const syncIdeaTitleInCache = (
  cache: Pick<ApolloCache, "readQuery" | "writeQuery">,
  ideaId: string | null,
  nextTitle: string
) => {
  if (!ideaId) {
    return;
  }

  const ideasData = cache.readQuery<CachedIdeasQuery>({
    query: GET_IDEAS,
  });

  if (ideasData?.ideas?.length) {
    cache.writeQuery<CachedIdeasQuery>({
      query: GET_IDEAS,
      data: {
        ideas: ideasData.ideas.map((idea) =>
          idea.ideaId === ideaId
            ? {
                ...idea,
                title: nextTitle,
              }
            : idea
        ),
      },
    });
  }

  const ideaData = cache.readQuery<CachedIdeaQuery>({
    query: GET_IDEA,
    variables: { ideaId },
  });

  if (ideaData?.idea) {
    cache.writeQuery<CachedIdeaQuery>({
      query: GET_IDEA,
      variables: { ideaId },
      data: {
        idea: {
          ...ideaData.idea,
          title: nextTitle,
        },
      },
    });
  }
};
