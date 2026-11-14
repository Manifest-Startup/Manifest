import React from "react";

interface IconProps {
  className?: string;
  strokeWidth?: number;
}

const baseSvgProps = {
  fill: "none",
  stroke: "currentColor",
  viewBox: "0 0 24 24",
  "aria-hidden": "true" as const,
};

export const SidebarLeftIcon: React.FC<IconProps> = ({ className = "h-5 w-5", strokeWidth = 1.9 }) => (
  <svg className={className} {...baseSvgProps}>
    <rect x="3.75" y="4.75" width="16.5" height="14.5" rx="2.5" strokeWidth={strokeWidth} />
    <path d="M9 4.75v14.5" strokeWidth={strokeWidth} />
  </svg>
);

export const SidebarRightIcon: React.FC<IconProps> = ({ className = "h-5 w-5", strokeWidth = 1.9 }) => (
  <svg className={className} {...baseSvgProps}>
    <rect x="3.75" y="4.75" width="16.5" height="14.5" rx="2.5" strokeWidth={strokeWidth} />
    <path d="M15 4.75v14.5" strokeWidth={strokeWidth} />
  </svg>
);

export const ChevronLeftIcon: React.FC<IconProps> = ({ className = "h-5 w-5", strokeWidth = 2.2 }) => (
  <svg
    className={className}
    height="24"
    width="24"
    style={{ flexShrink: 0, height: "1.5rem", minHeight: "1.5rem", minWidth: "1.5rem", width: "1.5rem" }}
    {...baseSvgProps}
  >
    <path d="m14.5 6-6 6 6 6" strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth} />
  </svg>
);

export const ChevronRightIcon: React.FC<IconProps> = ({ className = "h-5 w-5", strokeWidth = 2.2 }) => (
  <svg
    className={className}
    height="24"
    width="24"
    style={{ flexShrink: 0, height: "1.5rem", minHeight: "1.5rem", minWidth: "1.5rem", width: "1.5rem" }}
    {...baseSvgProps}
  >
    <path d="m9.5 6 6 6-6 6" strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth} />
  </svg>
);

export const PlusIcon: React.FC<IconProps> = ({ className = "h-5 w-5", strokeWidth = 2 }) => (
  <svg className={className} {...baseSvgProps}>
    <path d="M12 5v14M5 12h14" strokeLinecap="round" strokeWidth={strokeWidth} />
  </svg>
);

export const FocusIcon: React.FC<IconProps> = ({ className = "h-5 w-5", strokeWidth = 1.9 }) => (
  <svg className={className} {...baseSvgProps}>
    <path d="M9 4.75H6.75a2 2 0 0 0-2 2V9" strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth} />
    <path d="M15 4.75h2.25a2 2 0 0 1 2 2V9" strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth} />
    <path d="M9 19.25H6.75a2 2 0 0 1-2-2V15" strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth} />
    <path d="M15 19.25h2.25a2 2 0 0 0 2-2V15" strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth} />
  </svg>
);

export const HistoryIcon: React.FC<IconProps> = ({ className = "h-5 w-5", strokeWidth = 1.9 }) => (
  <svg className={className} {...baseSvgProps}>
    <path d="M4 5v4h4" strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth} />
    <path d="M4.8 12a7.2 7.2 0 1 0 2.1-5.1L4 9" strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth} />
    <path d="M12 8.5V12l2.4 1.6" strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth} />
  </svg>
);

export const ShareIcon: React.FC<IconProps> = ({ className = "h-5 w-5", strokeWidth = 1.9 }) => (
  <svg className={className} {...baseSvgProps}>
    <path d="M12 15V4.5" strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth} />
    <path d="m8.5 8 3.5-3.5L15.5 8" strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth} />
    <path d="M7.5 11.5v5A2.5 2.5 0 0 0 10 19h4a2.5 2.5 0 0 0 2.5-2.5v-5" strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth} />
  </svg>
);

export const RelatedIdeasIcon: React.FC<IconProps> = ({ className = "h-5 w-5", strokeWidth = 1.9 }) => (
  <svg className={className} {...baseSvgProps}>
    <rect x="4.75" y="5.25" width="7.5" height="7.5" rx="1.75" strokeWidth={strokeWidth} />
    <rect x="11.75" y="11.25" width="7.5" height="7.5" rx="1.75" strokeWidth={strokeWidth} />
  </svg>
);
