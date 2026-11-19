import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { LiveNoteSession, LiveSnapshot } from "./liveNoteSession";

const IDLE: LiveSnapshot = {
  status: "offline",
  canEdit: false,
  ready: false,
  self: null,
  peers: [],
  external: [],
  error: null,
};
const noop = () => () => undefined;

/**
 * Joins the idea note's live room while `enabled` (the idea is shared with someone).
 * A new session (and a fresh editor, keyed by `session`) is made whenever the room
 * has to start again from the saved note.
 */
export function useLiveNote(
  ideaId: string | null,
  enabled: boolean,
  onReset?: (html?: string) => void
) {
  const [generation, setGeneration] = useState(0);
  const [session, setSession] = useState<LiveNoteSession | null>(null);
  const onResetRef = useRef(onReset);
  onResetRef.current = onReset;

  useEffect(() => {
    if (!ideaId || !enabled) {
      setSession(null);
      return;
    }
    const next = new LiveNoteSession(ideaId);
    const stopReset = next.onResetRequired((html) => {
      onResetRef.current?.(html);
      setGeneration((g) => g + 1);
    });
    setSession(next);
    return () => {
      stopReset();
      next.destroy();
    };
  }, [ideaId, enabled, generation]);

  const snapshot = useSyncExternalStore(
    session ? session.subscribe : noop,
    session ? session.getSnapshot : () => IDLE,
    () => IDLE
  );

  return { session, snapshot };
}
