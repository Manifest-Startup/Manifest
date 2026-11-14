/** Shared layout tokens for idea publish / verified control (X/Instagram-scale, professional). */

export type PublishBadgeSize = "sm" | "md" | "lg" | "xl";

const buttonSize: Record<PublishBadgeSize, string> = {
  sm: "h-[22px] w-[22px] min-h-[22px] min-w-[22px]",
  md: "h-[26px] w-[26px] min-h-[26px] min-w-[26px]",
  lg: "h-8 w-8 min-h-8 min-w-8",
  xl: "h-10 w-10 min-h-10 min-w-10",
};

const iconBox: Record<PublishBadgeSize, string> = {
  sm: "h-[13px] w-[13px]",
  md: "h-4 w-4",
  lg: "h-[18px] w-[18px]",
  xl: "h-5 w-5",
};

export function publishBadgeButtonSizeClass(size: PublishBadgeSize): string {
  return buttonSize[size] ?? buttonSize.md;
}

export function publishBadgeIconBoxClass(size: PublishBadgeSize): string {
  return iconBox[size] ?? iconBox.md;
}

export const publishBadgeButtonBaseClass = `
  flex shrink-0 items-center justify-center rounded-full
  transition-transform duration-200 ease-out
  focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2
  dark:focus-visible:ring-offset-neutral900
`.replace(/\s+/g, " ").trim();

export const publishBadgePublishedClass = `
  bg-blue-500 text-white shadow-sm
  ring-[1.5px] ring-white/90 dark:ring-neutral-900/90
  hover:bg-blue-600 active:scale-95
`.replace(/\s+/g, " ").trim();

export const publishBadgeDraftClass = `
  bg-neutral-300 text-neutral-600
  ring-[1.5px] ring-white/70 dark:bg-neutral-600 dark:text-neutral-200 dark:ring-neutral-800/80
  hover:bg-neutral-400 dark:hover:bg-neutral-500 active:scale-95
`.replace(/\s+/g, " ").trim();
