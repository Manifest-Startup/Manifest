import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@apollo/client/react";

import { trackEvent } from "features/analytics/projectAnalytics";
import { CREATE_IDEA, GET_IDEAS } from "features/core/apollo/queries";
import { createLogger } from "features/core/logError";
import { useMessage } from "features/notifications/context/MessageContext";

const logger = createLogger("useCreateIdea");

/** Creates a blank idea and opens it. Shared by the ideas sidebar and the empty workspace. */
export const useCreateIdea = () => {
  const navigate = useNavigate();
  const { setMessage } = useMessage();
  const [createIdea] = useMutation(CREATE_IDEA, {
    refetchQueries: [{ query: GET_IDEAS }],
  });

  const createAndOpen = useCallback(
    async (surface: string): Promise<string | null> => {
      try {
        const { data } = await createIdea({ variables: { title: "Brand New Idea" } });
        const ideaId = data?.createIdea?.ideaId;
        if (!ideaId) {
          return null;
        }
        trackEvent("idea_created", { creation_surface: surface });
        navigate(`/ideas/${ideaId}/description`);
        return ideaId;
      } catch (creationError) {
        setMessage("Failed to create new idea. Please try again.", "error");
        logger.error("Error saving new idea:", creationError);
        return null;
      }
    },
    [createIdea, navigate, setMessage]
  );

  return { createIdea, createAndOpen };
};
