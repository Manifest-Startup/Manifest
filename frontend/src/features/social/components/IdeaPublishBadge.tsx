import React from "react";

import { useIdeaPublishToggle } from "features/social/hooks/useIdeaPublishToggle";
import type { PublishBadgeSize } from "features/social/publish/publishBadgeStyles";
import {
  publishBadgeButtonBaseClass,
  publishBadgeButtonSizeClass,
  publishBadgeDraftClass,
  publishBadgeIconBoxClass,
  publishBadgePublishedClass,
} from "features/social/publish/publishBadgeStyles";

export interface IdeaPublishBadgeProps {
  ideaId: string;
  isPublished: boolean;
  size?: PublishBadgeSize;
  onToggle?: (isPublished: boolean) => void;
  className?: string;
}

/**
 * Single control for publish / verified state: platform-scale blue badge with white check when live.
 */
const IdeaPublishBadge: React.FC<IdeaPublishBadgeProps> = ({
  ideaId,
  isPublished: initialPublished,
  size = "md",
  onToggle,
  className = "",
}) => {
  const { published, loading, onPress, justPublishedBurst } = useIdeaPublishToggle(
    ideaId,
    initialPublished,
    { onToggle },
  );

  const title = published
    ? "Published — visible in discovery and pitch reels. Click to unpublish."
    : "Not published. Click to publish for discovery and pitch reels.";

  const sizeCls = publishBadgeButtonSizeClass(size);
  const iconCls = publishBadgeIconBoxClass(size);
  const stateCls = published ? publishBadgePublishedClass : publishBadgeDraftClass;
  const burstCls = justPublishedBurst ? "manifest-publish-pop" : "";

  return (
    <button
      type="button"
      data-testid="idea-publish-badge"
      onClick={(e) => void onPress(e)}
      disabled={loading}
      title={title}
      aria-label={title}
      aria-pressed={published}
      className={`
        ${publishBadgeButtonBaseClass}
        ${sizeCls}
        ${stateCls}
        ${burstCls}
        ${loading ? "cursor-wait opacity-70 motion-safe:animate-pulse" : "cursor-pointer"}
        ${className}
      `.replace(/\s+/g, " ").trim()}
    >
      <svg viewBox="0 0 24 24" fill="none" className={iconCls} aria-hidden>
        {published ? (
          <path
            d="M9 12.5 11.2 14.5 15.5 9.5"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ) : (
          <>
            <path
              d="M12 8.5v7M8.5 12h7"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
            />
          </>
        )}
      </svg>
    </button>
  );
};

export default IdeaPublishBadge;
