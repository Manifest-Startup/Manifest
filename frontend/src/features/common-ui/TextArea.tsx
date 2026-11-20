import React, { useEffect, useRef } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import { createDocument } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import Collaboration, { isChangeOrigin } from "@tiptap/extension-collaboration";
import CollaborationCaret from "@tiptap/extension-collaboration-caret";
import { prosemirrorToYXmlFragment } from "@tiptap/y-tiptap";
import type { LiveExternalEdit, LiveNoteSession } from "features/collaboration/live/liveNoteSession";
import {
  ExternalCaret,
  applyHtmlChange,
  buildCaretElement,
  changedEnd,
  markExternalCaret,
} from "features/collaboration/live/externalEdits";
import {
  REFRESH_HIGHLIGHTS,
  SourceHighlight,
  sourceHighlightKey,
  type HighlightTarget,
} from "features/ideas/knowledge/sourceHighlight";
import {
  onNoteFocusRequest,
  readNoteCursor,
  requestListFocus,
  saveNoteCursor,
} from "features/ideas/utils/noteFocus";
import { DictationHighlight, registerDictationTarget } from "features/ideas/utils/noteDictation";
import { ContradictionHighlight, contradictionKey } from "features/ideas/knowledge/contradictions";

interface TextAreaProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  editable?: boolean;
  autoFocus?: boolean;
  focusKey?: string;
  rows?: number;
  disabled?: boolean;
  /**
   * Live notes (ADR 0008): edit together with everyone in this session. The shared
   * document replaces `value`, which is only used to fill an empty room. `onChange`
   * fires for this person's own edits, never for other people's.
   */
  live?: LiveNoteSession | null;
  /** Live: the saved note, fetched fresh, used to fill an empty room (defaults to `value`). */
  loadSavedNote?: () => Promise<string>;
  /** Text to highlight in place, e.g. the sentence a document cites (ADR 0010). */
  highlights?: HighlightTarget[];
  /**
   * Remember the cursor, selection and scroll position under this key (one per note) and
   * put them back when the note opens again. Esc moves focus back to the ideas list.
   */
  noteKey?: string;
  /** This is the open note: the voice orb writes dictation into it (at the cursor). */
  dictationTarget?: boolean;
}

const TextArea: React.FC<TextAreaProps> = ({
  value,
  onChange,
  placeholder,
  className = "",
  editable = true,
  autoFocus = false,
  focusKey,
  disabled = false,
  rows = 10,
  live = null,
  loadSavedNote,
  highlights,
  noteKey,
  dictationTarget = false,
}) => {
  const noteKeyRef = useRef(noteKey);
  noteKeyRef.current = noteKey;
  // The note whose saved position has been put back; saving waits for it so opening a
  // note never overwrites where you left off.
  const restoredRef = useRef<string | null>(null);
  const highlightsRef = useRef<HighlightTarget[]>(highlights ?? []);
  highlightsRef.current = highlights ?? [];
  const highlightKey = JSON.stringify(highlights ?? []);
  const liveRef = useRef(live);
  liveRef.current = live;
  const valueRef = useRef(value);
  valueRef.current = value;
  const pendingExternalRef = useRef<{ edit: LiveExternalEdit; until: number } | null>(null);
  const loadRef = useRef(loadSavedNote);
  loadRef.current = loadSavedNote;
  const liveWritable = (snapshot = live?.getSnapshot()) => !snapshot || (snapshot.canEdit && snapshot.ready);
  const canEdit = editable && !disabled && (!live || liveWritable());

  const editor = useEditor(
    {
      // Create the editor after commit so suspended renders cannot retain a disposed instance.
      immediatelyRender: false,
      extensions: [
        // Collaboration brings its own shared undo history.
        live ? StarterKit.configure({ undoRedo: false }) : StarterKit,
        Placeholder.configure({
          placeholder: placeholder || "Write something...",
        }),
        SourceHighlight.configure({ getTargets: () => highlightsRef.current }),
        DictationHighlight,
        // Where people writing together disagree (shared notes only).
        ContradictionHighlight.configure({ enabled: () => Boolean(liveRef.current) }),
        ...(live
          ? [
              Collaboration.configure({ fragment: live.fragment }),
              CollaborationCaret.configure({
                provider: { awareness: live.awareness },
                user: {},
                render: (user: Record<string, unknown>) =>
                  buildCaretElement({
                    name: String(user.name || "Someone"),
                    color: String(user.color || "#2563eb"),
                    avatarUrl: (user.avatarUrl as string | null) || null,
                  }),
              }),
              ExternalCaret,
            ]
          : []),
      ],
      content: live ? undefined : value,
      editable: canEdit,
      onUpdate: ({ editor, transaction }) => {
        if (live) {
          if (isChangeOrigin(transaction)) {
            // Someone else's edit. If it is the agent/CLI edit we were told about, show its caret.
            const pending = pendingExternalRef.current;
            if (pending && pending.until > Date.now()) {
              const pos = changedEnd(transaction.before, transaction.doc);
              if (pos != null) {
                pendingExternalRef.current = null;
                markExternalCaret(editor, pos, pending.edit.by);
              }
            }
            return;
          }
          if (live.seeding) return;
        }
        onChange(editor.getHTML());
      },
      editorProps: {
        handleKeyDown: (_view, event) => {
          if (event.key === "Escape" && noteKeyRef.current) {
            event.preventDefault();
            requestListFocus();
            return true;
          }
          return false;
        },
        attributes: {
          class:
            "manifest-reading focus:outline-none",
        },
      },
    },
    [live]
  );

  // Live: fill an empty room from the saved note, and merge agent/CLI edits.
  useEffect(() => {
    if (!editor || editor.isDestroyed || !live) return;
    live.setSeeder({
      load: () => (loadRef.current ? loadRef.current() : Promise.resolve(valueRef.current || "")),
      write: (html) => {
        prosemirrorToYXmlFragment(createDocument(html, editor.schema), live.fragment);
      },
    });
    const stopExternal = live.onExternalEdit((edit) => {
      if (!edit.apply) {
        pendingExternalRef.current = { edit, until: Date.now() + 10000 };
        return;
      }
      const pos = applyHtmlChange(editor, edit.html);
      if (pos != null) markExternalCaret(editor, pos, edit.by);
    });
    const stopStatus = live.subscribe((snapshot) => {
      const shouldEdit = editable && !disabled && liveWritable(snapshot);
      if (!editor.isDestroyed && editor.isEditable !== shouldEdit) editor.setEditable(shouldEdit, false);
    });
    return () => {
      live.setSeeder(null);
      stopExternal();
      stopStatus();
    };
  }, [editor, live, editable, disabled]);

  useEffect(() => {
    if (!editor || editor.isDestroyed) {
      return;
    }

    if (editor.isEditable !== canEdit) {
      editor.setEditable(canEdit, false);
    }

    if (!live && editor.getHTML() !== value) {
      editor.commands.setContent(value, { emitUpdate: false });
    }
  }, [value, canEdit, editor, live]);

  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    editor.view.dispatch(editor.state.tr.setMeta(sourceHighlightKey, REFRESH_HIGHLIGHTS));
  }, [editor, highlightKey]);

  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    editor.view.dispatch(editor.state.tr.setMeta(contradictionKey, true));
  }, [editor, live]);

  // -- Where you left off (cursor, selection, scroll) ----------------------------------
  const scroller = () => {
    let node = editor?.view.dom.parentElement ?? null;
    while (node && node !== document.body) {
      const { overflowY } = window.getComputedStyle(node);
      if ((overflowY === "auto" || overflowY === "scroll") && node.scrollHeight > node.clientHeight) {
        return node;
      }
      node = node.parentElement;
    }
    return null;
  };

  const restorePosition = () => {
    const key = noteKeyRef.current;
    if (!editor || editor.isDestroyed || !key || restoredRef.current === key) return;
    if (editor.state.doc.textContent.length === 0) return; // wait for the note to load
    restoredRef.current = key;
    const saved = readNoteCursor(key);
    if (!saved) return;
    const max = editor.state.doc.content.size;
    const clamp = (n: number) => Math.max(0, Math.min(n, max));
    try {
      editor.commands.setTextSelection({ from: clamp(saved.anchor), to: clamp(saved.head) });
    } catch {
      // A position that no longer exists in an edited note: keep the default.
    }
    const box = scroller();
    if (box) box.scrollTop = saved.scrollTop;
  };

  const focusNote = () => {
    if (!editor || editor.isDestroyed || !editable || disabled) return;
    restorePosition();
    const key = noteKeyRef.current;
    const hasSaved = Boolean(key && readNoteCursor(key));
    // Keep the restored cursor; a note without one starts at the end, ready to continue.
    editor.commands.focus(hasSaved ? undefined : "end", { scrollIntoView: !hasSaved });
  };

  useEffect(() => {
    restoredRef.current = null; // a different note: restore its own position
  }, [noteKey]);

  // The open note is where the voice orb writes what the person says.
  useEffect(() => {
    if (!editor || editor.isDestroyed || !dictationTarget) return;
    return registerDictationTarget(editor);
  }, [editor, dictationTarget]);

  useEffect(() => {
    if (!editor || editor.isDestroyed || !noteKey) return;
    const save = () => {
      const key = noteKeyRef.current;
      if (!key || restoredRef.current !== key || editor.isDestroyed) return;
      const { anchor, head } = editor.state.selection;
      saveNoteCursor(key, { anchor, head, scrollTop: scroller()?.scrollTop ?? 0 });
    };
    const attempt = () => restorePosition();
    editor.on("selectionUpdate", save);
    editor.on("blur", save);
    editor.on("update", attempt);
    attempt();
    const box = scroller();
    let frame = 0;
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(save);
    };
    box?.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("pagehide", save);
    const stopFocus = onNoteFocusRequest(focusNote);
    return () => {
      save();
      editor.off("selectionUpdate", save);
      editor.off("blur", save);
      editor.off("update", attempt);
      box?.removeEventListener("scroll", onScroll);
      window.removeEventListener("pagehide", save);
      cancelAnimationFrame(frame);
      stopFocus();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- helpers read refs
  }, [editor, noteKey, value]);

  useEffect(() => {
    // Focusing would jump away: when showing a source, let the reader stay on it.
    if (highlightsRef.current.length) return;
    if (!editor || editor.isDestroyed || !autoFocus || !editable || disabled) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      // Don't pull focus out of the ideas list or another control the person is using.
      const active = document.activeElement;
      const elsewhere = active && active !== document.body && !editor.view.dom.contains(active);
      if (!elsewhere) focusNote();
    }, 40);
    return () => window.clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- focusNote reads refs
  }, [autoFocus, disabled, editable, editor, focusKey]);

  return (
    <div className={`manifest-rich-editor ${className}`} style={{ minHeight: `${Math.max(rows * 1.6, 14)}rem` }}>
      <EditorContent editor={editor} />
    </div>
  );
};

export default TextArea;
