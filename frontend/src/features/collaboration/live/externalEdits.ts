/**
 * Edits made outside the live session (AI agent plugin, CLI, iOS) reach the room as
 * HTML. One editor merges only the changed range into the shared document, so
 * people typing elsewhere in the note keep their work; everyone sees a caret with
 * the author's photo and "via AI agent" / "via CLI" where the text changed.
 */
import { Editor, Extension, createDocument } from "@tiptap/core";
import type { Node as PMNode } from "@tiptap/pm/model";
import { Plugin, PluginKey, TextSelection } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { LiveExternalEditor } from "./liveNoteSession";

export const EXTERNAL_CARET_MS = 8000;

interface ChangedRange {
  start: number;
  endA: number;
  endB: number;
}

/** The range that differs between two documents (`endA` in `before`, `endB` in `after`), or null. */
export function changedRange(before: PMNode, after: PMNode): ChangedRange | null {
  const start = before.content.findDiffStart(after.content);
  if (start == null) return null;
  const end = before.content.findDiffEnd(after.content);
  let endA = end ? end.a : before.content.size;
  let endB = end ? end.b : after.content.size;
  // A shared suffix can overlap the start (e.g. "this." → "this.</p><p>agent."): push it back.
  const overlap = start - Math.min(endA, endB);
  if (overlap > 0) {
    endA += overlap;
    endB += overlap;
  }
  return { start, endA, endB };
}

/** Where `after` stops differing from `before` (a position in `after`), or null if equal. */
export function changedEnd(before: PMNode, after: PMNode): number | null {
  const range = changedRange(before, after);
  return range ? Math.min(range.endB, after.content.size) : null;
}

/** Replace only what changed between the editor's note and `html`. Returns the caret position. */
export function applyHtmlChange(editor: Editor, html: string): number | null {
  const next = createDocument(html, editor.schema);
  const range = changedRange(editor.state.doc, next);
  if (!range) return null;
  const tr = editor.state.tr.replace(range.start, range.endA, next.slice(range.start, range.endB));
  tr.setMeta("addToHistory", false);
  editor.view.dispatch(tr);
  return Math.min(range.endB, tr.doc.content.size);
}

const externalCaretKey = new PluginKey<ExternalCaretState>("manifestExternalCaret");

interface ExternalCaretState {
  pos: number;
  by: LiveExternalEditor;
}

export function caretLabel(by: Pick<LiveExternalEditor, "name" | "via" | "viaLabel">): string {
  return by.via === "app" ? by.name : `${by.name} · via ${by.viaLabel}`;
}

export function buildCaretElement(user: {
  name: string;
  color: string;
  avatarUrl?: string | null;
  label?: string;
}): HTMLElement {
  const caret = document.createElement("span");
  caret.className = "manifest-live-caret";
  caret.style.borderColor = user.color;
  const label = document.createElement("span");
  label.className = "manifest-live-caret__label";
  label.style.backgroundColor = user.color;
  if (user.avatarUrl) {
    const img = document.createElement("img");
    img.src = user.avatarUrl;
    img.alt = "";
    img.referrerPolicy = "no-referrer";
    img.className = "manifest-live-caret__avatar";
    label.appendChild(img);
  }
  label.appendChild(document.createTextNode(user.label || user.name));
  caret.appendChild(label);
  return caret;
}

/** Show `by`'s caret at `pos` for a few seconds. */
export function markExternalCaret(editor: Editor, pos: number, by: LiveExternalEditor): void {
  if (editor.isDestroyed) return;
  const doc = editor.state.doc;
  const $pos = doc.resolve(Math.max(0, Math.min(pos, doc.content.size)));
  // Between blocks: sit at the end of the text just before, where the edit ended.
  const at = $pos.parent.inlineContent ? $pos.pos : TextSelection.near($pos, -1).from;
  editor.view.dispatch(editor.state.tr.setMeta(externalCaretKey, { pos: at, by }));
  window.setTimeout(() => {
    if (editor.isDestroyed) return;
    const current = externalCaretKey.getState(editor.state);
    if (current?.by === by) editor.view.dispatch(editor.state.tr.setMeta(externalCaretKey, null));
  }, EXTERNAL_CARET_MS);
}

export const ExternalCaret = Extension.create({
  name: "manifestExternalCaret",
  addProseMirrorPlugins() {
    return [
      new Plugin<ExternalCaretState | null>({
        key: externalCaretKey,
        state: {
          init: () => null,
          apply(tr, value) {
            const meta = tr.getMeta(externalCaretKey);
            if (meta !== undefined) return meta;
            if (!value) return value;
            return { ...value, pos: Math.min(tr.mapping.map(value.pos), tr.doc.content.size) };
          },
        },
        props: {
          decorations(state) {
            const value = externalCaretKey.getState(state);
            if (!value) return null;
            const element = buildCaretElement({
              name: value.by.name,
              color: value.by.color,
              avatarUrl: value.by.avatarUrl,
              label: caretLabel(value.by),
            });
            element.classList.add("manifest-live-caret--external");
            return DecorationSet.create(state.doc, [
              Decoration.widget(value.pos, element, { key: `external-${value.by.userId}-${value.by.until}` }),
            ]);
          },
        },
      }),
    ];
  },
});
