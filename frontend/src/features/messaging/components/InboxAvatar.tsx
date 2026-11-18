import React, { useState } from "react";

import { resolveBackendAssetUrl } from "features/core/network/urls";

interface InboxAvatarProps {
  name: string;
  initials: string;
  url?: string | null;
  small?: boolean;
}

/** Open Media's avatar: a 48px circle with the picture, or initials on the chrome fill. */
const InboxAvatar: React.FC<InboxAvatarProps> = ({ name, initials, url, small }) => {
  const [failed, setFailed] = useState(false);
  return (
    <span className={`om-avatar${small ? " om-avatar-small" : ""}`} aria-hidden="true">
      {url && !failed ? (
        <img src={resolveBackendAssetUrl(url)} alt="" onError={() => setFailed(true)} />
      ) : (
        initials || name.slice(0, 1).toUpperCase() || "?"
      )}
    </span>
  );
};

export default InboxAvatar;
