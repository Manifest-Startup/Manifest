import React, { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { hasMod, isTypingTarget } from "features/ideas/utils/noteFocus";

const ShortcutsDialog = lazy(() => import("features/ideas/components/ShortcutsDialog"));

/**
 * Shortcuts that work on every page, following the platform conventions people already know:
 * ⌘/ (or ?) lists every shortcut, ⌘, opens account settings. Search (⌘K) lives in
 * UniversalSearch and voice (⌥⌘V) in FloatingVoiceButton; the sheet loads only when opened.
 */
const AppShortcuts: React.FC<{ signedIn: boolean }> = ({ signedIn }) => {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      const mod = hasMod(event);
      if (mod && !event.altKey && !event.shiftKey && event.key === "/") {
        event.preventDefault();
        setOpen((value) => !value);
        return;
      }
      if (mod && !event.altKey && !event.shiftKey && event.key === "," && signedIn) {
        event.preventDefault();
        navigate("/account");
        return;
      }
      if (!mod && !event.altKey && event.key === "?" && !isTypingTarget(event.target)) {
        event.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate, signedIn]);

  if (!open) return null;
  return (
    <Suspense fallback={null}>
      <ShortcutsDialog open onClose={close} />
    </Suspense>
  );
};

export default AppShortcuts;
