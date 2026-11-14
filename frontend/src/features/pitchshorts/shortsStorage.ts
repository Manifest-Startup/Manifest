import type { PersistentShortsState, ShortComment } from "./types";

const STORAGE_KEY = "manifest.pitch-shorts.state.v1";

export const DEFAULT_SHORTS_STATE: PersistentShortsState = {
  muted: true,
  likedClipIds: [],
  savedClipIds: [],
  followedCreatorIds: [],
  commentsByClipId: {},
};

const isShortCommentArray = (value: unknown): value is ShortComment[] =>
  Array.isArray(value) &&
  value.every(
    (item) =>
      item &&
      typeof item === "object" &&
      typeof (item as ShortComment).id === "string" &&
      typeof (item as ShortComment).clipId === "string" &&
      typeof (item as ShortComment).author === "string" &&
      typeof (item as ShortComment).body === "string" &&
      typeof (item as ShortComment).createdAt === "string"
  );

const sanitizeState = (value: unknown): PersistentShortsState => {
  if (!value || typeof value !== "object") {
    return DEFAULT_SHORTS_STATE;
  }

  const candidate = value as Partial<PersistentShortsState>;
  const commentsByClipId =
    candidate.commentsByClipId && typeof candidate.commentsByClipId === "object"
      ? Object.entries(candidate.commentsByClipId).reduce<Record<string, ShortComment[]>>(
          (acc, [clipId, comments]) => {
            if (isShortCommentArray(comments)) {
              acc[clipId] = comments;
            }
            return acc;
          },
          {}
        )
      : {};

  return {
    muted: typeof candidate.muted === "boolean" ? candidate.muted : DEFAULT_SHORTS_STATE.muted,
    likedClipIds: Array.isArray(candidate.likedClipIds)
      ? candidate.likedClipIds.filter((item): item is string => typeof item === "string")
      : [],
    savedClipIds: Array.isArray(candidate.savedClipIds)
      ? candidate.savedClipIds.filter((item): item is string => typeof item === "string")
      : [],
    followedCreatorIds: Array.isArray(candidate.followedCreatorIds)
      ? candidate.followedCreatorIds.filter((item): item is string => typeof item === "string")
      : [],
    commentsByClipId,
  };
};

export const loadShortsState = (): PersistentShortsState => {
  if (typeof window === "undefined") {
    return DEFAULT_SHORTS_STATE;
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return DEFAULT_SHORTS_STATE;
    }

    return sanitizeState(JSON.parse(raw));
  } catch {
    return DEFAULT_SHORTS_STATE;
  }
};

export const persistShortsState = (state: PersistentShortsState) => {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
};
