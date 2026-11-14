import React, { useEffect } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";

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
}) => {
  const editor = useEditor({
    // Create the editor after commit so suspended renders cannot retain a disposed instance.
    immediatelyRender: false,
    extensions: [
      StarterKit,
      Placeholder.configure({
        placeholder: placeholder || "Write something...",
      }),
    ],
    content: value,
    editable: editable && !disabled,
    onUpdate: ({ editor }) => {
      onChange(editor.getHTML());
    },
    editorProps: {
      attributes: {
        class:
          "font-sans prose prose-sm max-w-none text-neutral900 dark:prose-invert dark:text-white focus:outline-none",
      },
    },
  });

  useEffect(() => {
    if (!editor || editor.isDestroyed) {
      return;
    }

    if (editor.isEditable !== (editable && !disabled)) {
      editor.setEditable(editable && !disabled, false);
    }

    if (editor.getHTML() !== value) {
      editor.commands.setContent(value, { emitUpdate: false });
    }
  }, [value, editable, disabled, editor]);

  useEffect(() => {
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
