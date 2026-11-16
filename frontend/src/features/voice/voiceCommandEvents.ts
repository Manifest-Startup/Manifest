export const VOICE_SEARCH_EVENT = 'manifest:voice-search-command';
export const VOICE_WORKSPACE_LAYOUT_EVENT = 'manifest:voice-workspace-layout-command';
export const VOICE_COLLABORATION_EVENT = 'manifest:voice-collaboration-command';
export const VOICE_SHORTS_EVENT = 'manifest:voice-shorts-command';

export interface VoiceSearchCommandDetail {
  query?: string;
}

export type VoiceWorkspaceLayoutAction =
  | 'enable_focus_mode'
  | 'disable_focus_mode'
  | 'collapse_library'
  | 'expand_library'
  | 'collapse_context'
  | 'expand_context';

export interface VoiceWorkspaceLayoutDetail {
  action: VoiceWorkspaceLayoutAction;
}

export interface VoiceCollaborationDetail {
  ideaId: string;
  target: 'share' | 'history';
}

export type VoiceShortsAction =
  | 'next'
  | 'previous'
  | 'toggle_like'
  | 'toggle_reshare'
  | 'toggle_follow'
  | 'open_comments'
  | 'open_invest'
  | 'close_comments'
  | 'share'
  | 'open_workspace'
  | 'mute'
  | 'unmute'
  | 'comment';

export interface VoiceShortsDetail {
  action: VoiceShortsAction;
  body?: string;
}

function dispatchWindowEvent<T>(eventName: string, detail: T) {
  if (typeof window === 'undefined') {
    return;
  }

  window.dispatchEvent(new CustomEvent<T>(eventName, { detail }));
}

function subscribeWindowEvent<T>(eventName: string, listener: (detail: T) => void) {
  if (typeof window === 'undefined') {
    return () => undefined;
  }

  const wrappedListener = (event: Event) => {
    const customEvent = event as CustomEvent<T>;
    listener(customEvent.detail);
  };

  window.addEventListener(eventName, wrappedListener as EventListener);
  return () => window.removeEventListener(eventName, wrappedListener as EventListener);
}

export const dispatchVoiceSearchCommand = (detail: VoiceSearchCommandDetail) => {
  dispatchWindowEvent(VOICE_SEARCH_EVENT, detail);
};

export const dispatchVoiceWorkspaceLayoutCommand = (detail: VoiceWorkspaceLayoutDetail) => {
  dispatchWindowEvent(VOICE_WORKSPACE_LAYOUT_EVENT, detail);
};

export const dispatchVoiceCollaborationCommand = (detail: VoiceCollaborationDetail) => {
  dispatchWindowEvent(VOICE_COLLABORATION_EVENT, detail);
};

export const dispatchVoiceShortsCommand = (detail: VoiceShortsDetail) => {
  dispatchWindowEvent(VOICE_SHORTS_EVENT, detail);
};

export const subscribeToVoiceSearchCommand = (listener: (detail: VoiceSearchCommandDetail) => void) =>
  subscribeWindowEvent(VOICE_SEARCH_EVENT, listener);

export const subscribeToVoiceWorkspaceLayoutCommand = (listener: (detail: VoiceWorkspaceLayoutDetail) => void) =>
  subscribeWindowEvent(VOICE_WORKSPACE_LAYOUT_EVENT, listener);

export const subscribeToVoiceCollaborationCommand = (listener: (detail: VoiceCollaborationDetail) => void) =>
  subscribeWindowEvent(VOICE_COLLABORATION_EVENT, listener);

export const subscribeToVoiceShortsCommand = (listener: (detail: VoiceShortsDetail) => void) =>
  subscribeWindowEvent(VOICE_SHORTS_EVENT, listener);
