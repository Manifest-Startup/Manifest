import { Extension, type Editor } from "@tiptap/core";
import { Plugin, PluginKey, type Transaction } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

/**
 * Dictation into the open note: spoken words are written at the cursor as they arrive.
 *
 * The note editor registers itself as the target; the voice orb asks for a writer and
 * feeds it transcript pieces. Words still being heard (`interim`) show in a lighter colour
 * and are replaced once the sentence is final (`commit`). Other people's edits (live notes)
 * move the dictation point along with them.
 */
export interface DictationWriter {
  /** The words heard so far in the current sentence (replaces the previous interim text). */
  interim: (text: string) => void;
  /** The final text of the current sentence. */
  commit: (text: string) => void;
  /** Stop; any interim text stays as typed. */
  end: () => void;
}

type Range = { from: number; to: number };

const dictationKey = new PluginKey<Range | null>("manifestDictation");
const OURS = "manifestDictation";

/** Shows the words still being heard in a lighter colour. */
export const DictationHighlight = Extension.create({
  name: "dictationHighlight",
  addProseMirrorPlugins() {
    return [
      new Plugin<Range | null>({
        key: dictationKey,
        state: {
          init: () => null,
          apply: (tr, value) => {
            const meta = tr.getMeta(dictationKey) as Range | null | undefined;
            if (meta !== undefined) return meta;
            if (!value) return null;
            return { from: tr.mapping.map(value.from, -1), to: tr.mapping.map(value.to, 1) };
          },
        },
        props: {
          decorations: (state) => {
            const range = dictationKey.getState(state);
            if (!range || range.to <= range.from) return null;
            return DecorationSet.create(state.doc, [
              Decoration.inline(range.from, range.to, { class: "manifest-dictation-interim" }),
            ]);
          },
        },
      }),
    ];
  },
});

/** Join a new sentence to the text before it with exactly one space. */
export function joinToPrevious(before: string, text: string): string {
  const trimmed = text.replace(/\s+/g, " ").trim();
  if (!trimmed) return "";
  return before && !/\s$/.test(before) ? ` ${trimmed}` : trimmed;
}

let target: Editor | null = null;
const listeners = new Set<(available: boolean) => void>();

function announce(): void {
  listeners.forEach((listener) => listener(Boolean(target)));
}

/** The note editor offers itself as the place dictation writes into. */
export function registerDictationTarget(editor: Editor): () => void {
  target = editor;
  announce();
  return () => {
    if (target === editor) {
      target = null;
      announce();
    }
  };
}

export function onDictationTargetChange(listener: (available: boolean) => void): () => void {
  listeners.add(listener);
  listener(Boolean(target));
  return () => listeners.delete(listener);
}

/** A writer at the note's cursor, or null when no note is open for editing. */
export function startDictation(): DictationWriter | null {
  const editor = target;
  if (!editor || editor.isDestroyed || !editor.isEditable) return null;

  let segment: Range = (() => {
    const { to } = editor.state.selection;
    return { from: to, to };
  })();
  let ended = false;

  // Keep our range where it belongs when someone else edits the note meanwhile.
  const follow = ({ transaction }: { transaction: Transaction }) => {
    if (transaction.getMeta(OURS) || !transaction.docChanged) return;
    segment = {
      from: transaction.mapping.map(segment.from, -1),
      to: transaction.mapping.map(segment.to, 1),
    };
  };
  editor.on("transaction", follow);

  const write = (text: string, final: boolean) => {
    if (ended || editor.isDestroyed || !editor.isEditable) return;
    const { state } = editor;
    const from = Math.min(segment.from, state.doc.content.size);
    const to = Math.min(Math.max(segment.to, from), state.doc.content.size);
    const before = state.doc.textBetween(Math.max(0, from - 1), from, "\n", "\n");
    const piece = joinToPrevious(before, text);
    const tr = state.tr.insertText(piece, from, to).setMeta(OURS, true);
    const end = from + piece.length;
    tr.setMeta(dictationKey, final || !piece ? null : { from, to: end });
    tr.setMeta("addToHistory", final);
    editor.view.dispatch(tr.scrollIntoView());
    segment = final ? { from: end, to: end } : { from, to: end };
  };

  return {
    interim: (text) => write(text, false),
    commit: (text) => write(text, true),
    end: () => {
      if (ended) return;
      ended = true;
      editor.off("transaction", follow);
      if (!editor.isDestroyed) editor.view.dispatch(editor.state.tr.setMeta(dictationKey, null));
    },
  };
}
