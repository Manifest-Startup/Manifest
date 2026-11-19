/**
 * Highlights where a document's claim came from, right in the idea note (ADR 0010).
 *
 * A citation in a document opens the note with `?cite=p3` and a concept link with
 * `?mark=<concept>`; the note shows that sentence, or every place the concept is written,
 * with a reading highlight and scrolls to the first one. Decorations only: the note's text
 * and the shared live document are never changed.
 */
import { Extension } from "@tiptap/core";
import type { Node as PMNode } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

export const sourceHighlightKey = new PluginKey<DecorationSet>("manifestSourceHighlight");

export interface HighlightTarget {
  /** Text to find: a whole sentence, or a concept phrase. */
  text: string;
  /** A phrase also matches its plural/-ing/-ed forms and hyphenated spelling. */
  phrase?: boolean;
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function patternFor(target: HighlightTarget): RegExp | null {
  const words = target.text.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return null;
  if (target.phrase) {
    const body = words.map(escape).join("[\\s\\u00a0-]+");
    return new RegExp(`(?<![\\w-])${body}(?:s|es|ies|ing|ed)?(?![\\w-])`, "giu");
  }
  // Sentences: tolerate any whitespace, curly quotes and a trailing full stop.
  const body = words
    .map((w) => escape(w).replace(/['’]/g, "['’]").replace(/["“”]/g, "[\"“”]"))
    .join("[\\s\\u00a0]+");
  return new RegExp(body, "giu");
}

/** Inline ranges in `doc` matching any target (each textblock is searched on its own). */
export function findHighlights(doc: PMNode, targets: HighlightTarget[]): { from: number; to: number }[] {
  const patterns = targets.map(patternFor).filter((p): p is RegExp => Boolean(p));
  if (!patterns.length) return [];
  const ranges: { from: number; to: number }[] = [];
  doc.descendants((node, pos) => {
    if (!node.isTextblock) return true;
    // Leaf nodes (hard breaks) count as one character, matching their document size.
    const text = node.textBetween(0, node.content.size, undefined, "￼");
    for (const pattern of patterns) {
      pattern.lastIndex = 0;
      for (const match of text.matchAll(pattern)) {
        if (!match[0]) continue;
        const from = pos + 1 + (match.index ?? 0);
        ranges.push({ from, to: from + match[0].length });
      }
    }
    return false;
  });
  return ranges.sort((a, b) => a.from - b.from);
}

/** Dispatch on the editor after the targets change, to re-highlight and scroll. */
export const REFRESH_HIGHLIGHTS = "refresh";

export const SourceHighlight = Extension.create<{ getTargets: () => HighlightTarget[] }>({
  name: "manifestSourceHighlight",
  addOptions() {
    return { getTargets: () => [] };
  },
  addProseMirrorPlugins() {
    const { getTargets } = this.options;
    let scrolled = false;
    const build = (doc: PMNode) =>
      DecorationSet.create(
        doc,
        findHighlights(doc, getTargets()).map(({ from, to }) =>
          Decoration.inline(from, to, { class: "manifest-source-mark" }),
        ),
      );
    return [
      new Plugin<DecorationSet>({
        key: sourceHighlightKey,
        state: {
          init: (_, state) => build(state.doc),
          // Re-find after remote or local changes so the highlight follows the text.
          apply: (tr, old) => {
            if (tr.getMeta(sourceHighlightKey) === REFRESH_HIGHLIGHTS) {
              scrolled = false; // a new source: bring it into view
              return build(tr.doc);
            }
            return tr.docChanged ? build(tr.doc) : old;
          },
        },
        props: {
          decorations: (state) => sourceHighlightKey.getState(state),
        },
        view: (view) => {
          const scroll = () => {
            if (scrolled) return;
            const first = view.dom.querySelector(".manifest-source-mark");
            if (!first) return;
            scrolled = true;
            first.scrollIntoView({ block: "center", behavior: "smooth" });
          };
          window.setTimeout(scroll, 60);
          return { update: scroll };
        },
      }),
    ];
  },
});
