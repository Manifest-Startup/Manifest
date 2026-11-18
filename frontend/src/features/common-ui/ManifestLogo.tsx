import React from "react";

// The Manifest mark: a geometric M whose right stroke rises above the left
// (an idea climbing into a plan). Same geometry as public/brand/manifest-mark.svg,
// the favicons and the app icons; change them together.
export const MANIFEST_MARK_PATH = "M25 78V35L50 60L75 26V78";

interface ManifestLogoProps {
  /** Rendered size in pixels (square). */
  size?: number;
  className?: string;
  /** Accessible name; omit when a visible "Manifest" label sits next to it. */
  title?: string;
}

const ManifestLogo: React.FC<ManifestLogoProps> = ({ size = 32, className = "", title }) => (
  <svg
    viewBox="0 0 100 100"
    width={size}
    height={size}
    className={`shrink-0 ${className}`}
    role={title ? "img" : undefined}
    aria-label={title}
    aria-hidden={title ? undefined : true}
    focusable="false"
  >
    {title ? <title>{title}</title> : null}
    <rect width="100" height="100" rx="23" className="fill-neutral900 dark:fill-white" />
    <path
      d={MANIFEST_MARK_PATH}
      fill="none"
      strokeWidth={size < 24 ? 12 : 11}
      strokeLinejoin="miter"
      strokeMiterlimit={10}
      className="stroke-white dark:stroke-neutral900"
    />
  </svg>
);

export default ManifestLogo;
