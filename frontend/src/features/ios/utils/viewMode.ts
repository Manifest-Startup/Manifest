/**
 * View mode management for switching between desktop and iOS views
 */

export type ViewMode = 'desktop' | 'ios' | 'auto';

const VIEW_MODE_KEY = 'manifest_view_mode';

/**
 * Get the current view mode from localStorage or default to 'auto'
 */
export const getViewMode = (): ViewMode => {
  if (typeof window === 'undefined') return 'auto';
  const stored = localStorage.getItem(VIEW_MODE_KEY);
  return (stored as ViewMode) || 'auto';
};

/**
 * Set the view mode and save to localStorage
 */
export const setViewMode = (mode: ViewMode): void => {
  if (typeof window === 'undefined') return;
  localStorage.setItem(VIEW_MODE_KEY, mode);
};

/**
 * Determine if iOS view should be shown based on view mode and device
 */
export const shouldShowIOSView = (viewMode: ViewMode, isIOSDevice: boolean): boolean => {
  if (viewMode === 'ios') return true;
  if (viewMode === 'desktop') return false;
  // auto mode: show iOS view on iOS devices
  return isIOSDevice;
};

