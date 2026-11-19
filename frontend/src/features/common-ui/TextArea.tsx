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
}) => {
  const highlightsRef = useRef<HighlightTarget[]>(highlights ?? []);
  highlightsRef.current = highlights ?? [];
  const highlightKey = JSON.stringify(highlights ?? []);
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
    // Focusing would jump to the top: when showing a source, let the reader stay on it.
    if (highlightsRef.current.length) return;
    if (!editor || editor.isDestroyed || !autoFocus || !editable || disabled) {
      return;
    }

    const focusEditor = () => {
      if (!editor.isDestroyed) editor.commands.focus('start');
    };

    const timeoutId = window.setTimeout(focusEditor, 40);
    return () => window.clearTimeout(timeoutId);
  }, [autoFocus, disabled, editable, editor, focusKey]);

  return (
    <div className={`manifest-rich-editor ${className}`} style={{ minHeight: `${Math.max(rows * 1.6, 14)}rem` }}>
      <EditorContent editor={editor} />
    </div>
  );
};

export default TextArea;
