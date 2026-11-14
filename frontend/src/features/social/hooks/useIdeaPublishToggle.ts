import { useMutation } from "@apollo/client/react";
import { useCallback, useEffect, useRef, useState } from "react";

import { GET_IDEAS, TOGGLE_PUBLISH_IDEA } from "features/core/apollo/queries";
import { useMessage } from "features/notifications/context/MessageContext";
import { emitIdeaPublished } from "features/ideas/events/ideaPublishEvents";

export interface UseIdeaPublishToggleOptions {
  onToggle?: (isPublished: boolean) => void;
}

export interface UseIdeaPublishToggleResult {
  published: boolean;
  loading: boolean;
  onPress: (e?: React.MouseEvent) => Promise<void>;
  /** True briefly after a successful publish for entrance animation */
  justPublishedBurst: boolean;
}

/**
 * Centralized publish toggle: optimistic UI, refetch ideas, optional callback.
 */
export function useIdeaPublishToggle(
  ideaId: string,
  initialPublished: boolean,
  options?: UseIdeaPublishToggleOptions,
): UseIdeaPublishToggleResult {
  const [published, setPublished] = useState(initialPublished);
  const [justPublishedBurst, setJustPublishedBurst] = useState(false);
  const onToggleRef = useRef(options?.onToggle);
  onToggleRef.current = options?.onToggle;

  const { setMessage } = useMessage();

  useEffect(() => {
    setPublished(initialPublished);
  }, [initialPublished]);

  const [togglePublish, { loading }] = useMutation(TOGGLE_PUBLISH_IDEA, {
    refetchQueries: [{ query: GET_IDEAS }],
    onCompleted: (data) => {
      const v = data?.togglePublishIdea?.isPublished;
      if (typeof v === "boolean") {
        setPublished(v);
        onToggleRef.current?.(v);
      }
    },
  });

  const onPress = useCallback(
    async (e?: React.MouseEvent) => {
      e?.stopPropagation();
      if (loading) return;
      const prev = published;
      const next = !prev;
      setPublished(next);
      onToggleRef.current?.(next);
      try {
        await togglePublish({ variables: { ideaId } });
        if (next) {
          emitIdeaPublished(ideaId);
          window.setTimeout(() => {
            setJustPublishedBurst(true);
            window.setTimeout(() => setJustPublishedBurst(false), 700);
          }, 0);
          setMessage(
            "Your pitch reel is generating — it will be ready in Pitch Reels in a few minutes.",
            "success",
            8000,
            { url: "/pitch-reels", label: "Go to Pitch Reels" },
          );
        } else {
          setMessage("Pitch reel hidden from the feed.", "info", 3000);
        }
      } catch {
        setPublished(prev);
        onToggleRef.current?.(prev);
      }
    },
    [ideaId, loading, published, togglePublish, setMessage],
  );

  return { published, loading, onPress, justPublishedBurst };
}
