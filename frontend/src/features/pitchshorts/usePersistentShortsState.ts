import { useEffect, useMemo, useState } from "react";

import { DEFAULT_SHORTS_STATE, loadShortsState, persistShortsState } from "./shortsStorage";
import type { PersistentShortsState, ShortComment } from "./types";

const toggleId = (ids: string[], targetId: string) =>
  ids.includes(targetId) ? ids.filter((id) => id !== targetId) : [...ids, targetId];

const createCommentId = () =>
  `comment-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

export const usePersistentShortsState = () => {
  const [state, setState] = useState<PersistentShortsState>(loadShortsState);

  useEffect(() => {
    persistShortsState(state);
  }, [state]);

  const likedClipIds = useMemo(() => new Set(state.likedClipIds), [state.likedClipIds]);
  const savedClipIds = useMemo(() => new Set(state.savedClipIds), [state.savedClipIds]);
  const followedCreatorIds = useMemo(
    () => new Set(state.followedCreatorIds),
    [state.followedCreatorIds]
  );

  const toggleLike = (clipId: string) => {
    setState((current) => ({
      ...current,
      likedClipIds: toggleId(current.likedClipIds, clipId),
    }));
  };

  const toggleSave = (clipId: string) => {
    setState((current) => ({
      ...current,
      savedClipIds: toggleId(current.savedClipIds, clipId),
    }));
  };

  const toggleFollow = (creatorId: string) => {
    setState((current) => ({
      ...current,
      followedCreatorIds: toggleId(current.followedCreatorIds, creatorId),
    }));
  };

  const setMuted = (muted: boolean) => {
    setState((current) => ({
      ...current,
      muted,
    }));
  };

  const addComment = (clipId: string, body: string) => {
    const normalizedBody = body.trim();
    if (!normalizedBody) {
      return null;
    }

    const nextComment: ShortComment = {
      id: createCommentId(),
      clipId,
      author: "You",
      body: normalizedBody,
      createdAt: new Date().toISOString(),
    };

    setState((current) => ({
      ...current,
      commentsByClipId: {
        ...current.commentsByClipId,
        [clipId]: [...(current.commentsByClipId[clipId] || []), nextComment],
      },
    }));

    return nextComment;
  };

  const reset = () => setState(DEFAULT_SHORTS_STATE);

  return {
    state,
    likedClipIds,
    savedClipIds,
    followedCreatorIds,
    toggleLike,
    toggleSave,
    toggleFollow,
    setMuted,
    addComment,
    reset,
  };
};
