import React from "react";

import IdeaPublishBadge, { IdeaPublishBadgeProps } from "./IdeaPublishBadge";

/** @deprecated Prefer `IdeaPublishBadge`; kept for stable imports (e.g. iOS ideas list). */
const PublishTick: React.FC<IdeaPublishBadgeProps> = (props) => <IdeaPublishBadge {...props} />;

export default PublishTick;
