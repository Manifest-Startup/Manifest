import React from "react";

import IdeaPublishBadge, { IdeaPublishBadgeProps } from "./IdeaPublishBadge";

/** @deprecated Prefer `IdeaPublishBadge`; kept for stable imports. */
const VerifiedBadge: React.FC<IdeaPublishBadgeProps> = (props) => <IdeaPublishBadge {...props} />;

export default VerifiedBadge;
