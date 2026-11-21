import React, { useEffect, useRef } from "react";
import { hasMod, isApple, isTypingTarget, requestListFocus } from "../utils/noteFocus";

/**
 * Every keyboard shortcut in Manifest, in one sheet (⌘/ or ? anywhere in the app).
 * Navigation follows Apple Notes and Notion; writing follows Google Docs and the editor
 * (Tiptap) defaults, so the keys people already know work here.
 */
type Row = [keys: string, what: string];

export function shortcutGroups(apple = isApple()): { title: string; rows: Row[] }[] {
  const mod = apple ? "⌘" : "Ctrl";
  const alt = apple ? "⌥" : "Alt";
  const shift = apple ? "⇧" : "Shift";
  const join = (...keys: string[]) => keys.join(apple ? "" : "+");
  return [
    {
      title: "Everywhere",
      rows: [
        [join(mod, "K"), "Search everything"],
        [join(alt, mod, "V"), "Talk to Manifest (voice)"],
        [join(mod, ","), "Account and settings"],
        [join(mod, "/") + "  ?", "Show these shortcuts"],
        ["Esc", "Close a dialog, voice or search"],
      ],
    },
    {
      title: "Move around",
      rows: [
        ["↑  ↓", "Previous or next idea (in the ideas list)"],
        ["Home  End", "First or last idea"],
        ["Return", "Open the note, where you left off"],
        ["Esc", "Back to the ideas list"],
        ["→  ←", "Show or hide an idea's documents"],
        [join(mod, "["), "Back"],
        [join(mod, "]"), "Forward"],
      ],
    },
    {
      title: "Ideas",
      rows: [
        [join(alt, mod, "N"), "New idea"],
        [join(mod, "S"), "Save now (it also saves as you type)"],
        [join(mod, "\\"), "Show or hide the ideas list"],
        [join(mod, shift, "F"), "Focus mode"],
        [join(alt, mod, "D"), "Dictate into the note (Esc stops)"],
      ],
    },
    {
      title: "Write",
      rows: [
        [join(mod, "B"), "Bold"],
        [join(mod, "I"), "Italic"],
        [join(mod, "U"), "Underline"],
        [join(mod, shift, "S"), "Strikethrough"],
        [join(mod, "E"), "Inline code"],
        [join(mod, alt, "1–3"), "Heading 1–3"],
        [join(mod, alt, "0"), "Plain text"],
        [join(mod, shift, "7"), "Numbered list"],
        [join(mod, shift, "8"), "Bulleted list"],
        [join(mod, shift, "B"), "Quote"],
        ["Tab  " + join(shift, "Tab"), "Indent or outdent a list item"],
        [join(mod, "Z"), "Undo"],
        [join(mod, shift, "Z"), "Redo"],
        [join(mod, "A"), "Select all"],
      ],
    },
  ];
}

export const ShortcutsDialog: React.FC<{ open: boolean; onClose: () => void }> = ({ open, onClose }) => {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      previous?.focus?.();
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="manifest-modal-backdrop" onClick={onClose}>
      <div
        className="manifest-modal manifest-shortcuts"
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcuts-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="manifest-modal-header">
          <h2 id="shortcuts-title" className="text-2xl font-semibold tracking-[-0.03em]">
            Keyboard shortcuts
          </h2>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close" className="manifest-shortcuts-close">
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="manifest-modal-body manifest-shortcuts-body">
          {shortcutGroups().map((group) => (
            <section key={group.title} aria-label={group.title}>
              <h3>{group.title}</h3>
              <dl>
                {group.rows.map(([keys, what]) => (
                  <div key={what}>
                    <dt>{what}</dt>
                    <dd>
                      {keys.split("  ").map((k) => (
                        <kbd key={k}>{k}</kbd>
                      ))}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
};

export default ShortcutsDialog;

/**
 * The ideas workspace's own shortcuts, rendered once on the ideas page; `onToggleLibrary`
 * shows or hides the ideas list. The sheet itself (⌘/ or ?) is app-wide: AppShortcuts.
 */
export const WorkspaceShortcuts: React.FC<{
  onToggleLibrary?: () => void;
  onNewIdea: () => void;
}> = ({ onToggleLibrary, onNewIdea }) => {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      const mod = hasMod(event);
      const key = event.key.toLowerCase();
      if (mod && event.altKey && !event.shiftKey && (key === "n" || event.code === "KeyN")) {
        event.preventDefault();
        onNewIdea();
        return;
      }
      if (mod && !event.altKey && key === "\\" && onToggleLibrary) {
        event.preventDefault();
        onToggleLibrary();
        return;
      }
      if (isTypingTarget(event.target) || mod || event.altKey) return;
      // Arrows with nothing focused go to the ideas list, so they always walk the notes.
      if ((event.key === "ArrowDown" || event.key === "ArrowUp") && document.activeElement === document.body) {
        event.preventDefault();
        requestListFocus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onNewIdea, onToggleLibrary]);
  return null;
};
