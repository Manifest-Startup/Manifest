/**
 * Spots statements in a note that contradict each other, so people writing together see
 * where they disagree (e.g. "Each room holds 400 crates." vs "A room holds 250 crates.").
 *
 * Deterministic and local: no model, no key, runs as people type. Three signals, each only
 * between two sentences about the same thing (they share at least two content words):
 *   - the same unit with different numbers   400 crates ↔ 250 crates, $5 ↔ $8, 10% ↔ 20%
 *   - one denies what the other states        "is free" ↔ "is not free"
 *   - opposite words                          rent ↔ buy, monthly ↔ yearly, B2B ↔ B2C
 * It flags, it never edits; the highlight is a decoration on the note.
 */
import { Extension } from "@tiptap/core";
import type { Node as PMNode } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

export interface NoteSentence {
  text: string;
  /** Position of the sentence in the editor document. */
  from: number;
  to: number;
}

export interface Contradiction {
  a: NoteSentence;
  b: NoteSentence;
  /** Short, plain reason: "400 vs 250 crates". */
  reason: string;
}

const STOP = new Set(
  (
    "a an the and or but if of to in on at by for with from into onto per as is are was were be been being it its " +
    "this that these those there their they them we our us you your he she his her i me my do does did will would " +
    "can could should may might must shall have has had so than then just also only very about over under up down " +
    "each every any some all most more less much many few one which who whom what when where why how not no never " +
    "n't without cannot isn't aren't wasn't weren't don't doesn't didn't won't can't shouldn't wouldn't"
  ).split(" "),
);
const NEGATIONS = new Set([
  "not", "no", "never", "without", "cannot", "can't", "won't", "isn't", "aren't", "wasn't", "weren't",
  "don't", "doesn't", "didn't", "shouldn't", "wouldn't", "none", "nobody", "nothing",
]);
const OPPOSITES: [string, string][] = [
  // Pairs that can't both hold for the same thing. ("free" vs "fee" is left out: a free first
  // month and a fee per crate is a plan, not a contradiction.)
  ["free", "paid"], ["cheap", "expensive"], ["rent", "buy"], ["lease", "buy"],
  ["increase", "decrease"], ["rise", "fall"],
  ["more", "fewer"], ["higher", "lower"], ["faster", "slower"], ["b2b", "b2c"], ["online", "offline"],
  ["always", "never"], ["monthly", "yearly"], ["monthly", "annual"], ["monthly", "annually"], ["daily", "weekly"],
  ["profitable", "unprofitable"], ["possible", "impossible"], ["legal", "illegal"], ["include", "exclude"],
  ["urban", "rural"], ["before", "after"], ["first", "last"], ["early", "late"],
  ["subscription", "one-time"], ["open-source", "proprietary"], ["public", "private"], ["start", "stop"],
];
const OPPOSITE = new Map<string, Set<string>>();
for (const [x, y] of OPPOSITES) {
  if (!OPPOSITE.has(x)) OPPOSITE.set(x, new Set());
  if (!OPPOSITE.has(y)) OPPOSITE.set(y, new Set());
  OPPOSITE.get(x)!.add(y);
  OPPOSITE.get(y)!.add(x);
}
const IRREGULAR: Record<string, string> = { bought: "buy", sold: "sell", rose: "rise", fell: "fall", began: "start" };

/** A word's plain form, for matching opposites: rented → rent, buying → buy, increases → increase. */
function lemma(word: string): string {
  if (IRREGULAR[word]) return IRREGULAR[word];
  if (OPPOSITE.has(word)) return word;
  for (const [suffix, back] of [["ying", "y"], ["ing", ""], ["ied", "y"], ["ed", ""], ["ies", "y"], ["es", "e"], ["s", ""]] as const) {
    if (word.endsWith(suffix) && word.length - suffix.length >= 3) {
      const base = word.slice(0, -suffix.length) + back;
      if (OPPOSITE.has(base)) return base;
      if (OPPOSITE.has(base + "e")) return base + "e";
    }
  }
  return word;
}

const NUMBER_WORDS: Record<string, number> = {
  one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
  eleven: 11, twelve: 12, twenty: 20, thirty: 30, fifty: 50, hundred: 100, thousand: 1000,
};

const words = (text: string) => text.toLowerCase().match(/[a-z0-9$%][a-z0-9'’$%.-]*/g)?.map(w => w.replace(/’/g, "'").replace(/[.]+$/, "")) ?? [];

/** Content words, singular-ish, without numbers: what a sentence is about. */
function topics(tokens: string[]): Set<string> {
  const out = new Set<string>();
  for (const t of tokens) {
    if (STOP.has(t) || NEGATIONS.has(t) || /\d/.test(t) || t in NUMBER_WORDS || t.length < 3) continue;
    out.add(t.replace(/(ies)$/, "y").replace(/(?<=[^s])s$/, ""));
  }
  return out;
}

interface Quantity {
  value: number;
  unit: string;
  shown: string;
}

/** "400 crates", "$5", "20%", "two weeks" (the unit is the word after, or $ / %). */
function quantities(tokens: string[]): Quantity[] {
  const out: Quantity[] = [];
  tokens.forEach((t, i) => {
    const money = t.match(/^\$(\d[\d,]*(?:\.\d+)?)(k|m)?$/);
    const percent = t.match(/^(\d+(?:\.\d+)?)%$/);
    const plain = t.match(/^(\d[\d,]*(?:\.\d+)?)(k|m)?$/);
    const scale = (s?: string) => (s === "k" ? 1e3 : s === "m" ? 1e6 : 1);
    if (money) out.push({ value: parseFloat(money[1].replace(/,/g, "")) * scale(money[2]), unit: "$", shown: t });
    else if (percent) out.push({ value: parseFloat(percent[1]), unit: "%", shown: t });
    else if (plain || t in NUMBER_WORDS) {
      const value = plain ? parseFloat(plain[1].replace(/,/g, "")) * scale(plain[2]) : NUMBER_WORDS[t];
      const next = tokens[i + 1];
      if (next && !STOP.has(next) && !/\d/.test(next)) {
        const unit = next.replace(/(?<=[^s])s$/, "");
        out.push({ value, unit, shown: `${t} ${next}` });
      }
    }
  });
  return out;
}

const negated = (tokens: string[]) => tokens.some(t => NEGATIONS.has(t) || t.endsWith("n't"));

function shared(a: Set<string>, b: Set<string>): number {
  let n = 0;
  for (const x of a) if (b.has(x)) n += 1;
  return n;
}

/** The reason two sentences contradict, or null. */
export function contradictionBetween(first: string, second: string): string | null {
  const ta = words(first);
  const tb = words(second);
  const topicsA = topics(ta);
  const topicsB = topics(tb);
  const common = shared(topicsA, topicsB);
  if (common < 2) return null; // not about the same thing

  for (const qa of quantities(ta)) {
    for (const qb of quantities(tb)) {
      if (qa.unit === qb.unit && qa.value !== qb.value) {
        return qa.unit === "$" || qa.unit === "%" ? `${qa.shown} vs ${qb.shown}` : `${qa.shown} vs ${qb.shown}`;
      }
    }
  }

  const overlap = common / Math.max(1, Math.min(topicsA.size, topicsB.size));
  if (negated(ta) !== negated(tb) && overlap >= 0.6) {
    return negated(ta) ? "one says it isn't, the other says it is" : "one says it is, the other says it isn't";
  }

  const lemmasA = new Set(ta.map(lemma));
  const lemmasB = new Set(tb.map(lemma));
  for (const w of lemmasA) {
    const opposite = OPPOSITE.get(w);
    if (!opposite) continue;
    for (const o of opposite) if (lemmasB.has(o) && !lemmasA.has(o) && !lemmasB.has(w)) return `${w} vs ${o}`;
  }
  return null;
}

/** Sentences of each paragraph with their document positions. */
export function noteSentences(doc: PMNode): NoteSentence[] {
  const out: NoteSentence[] = [];
  doc.descendants((node, pos) => {
    if (!node.isTextblock) return true;
    const text = node.textBetween(0, node.content.size, undefined, "￼");
    for (const match of text.matchAll(/[^.!?]+[.!?]*/g)) {
      const raw = match[0];
      const lead = raw.length - raw.trimStart().length;
      const sentence = raw.trim();
      if (sentence.length < 8) continue;
      const from = pos + 1 + (match.index ?? 0) + lead;
      out.push({ text: sentence, from, to: from + sentence.length });
    }
    return false;
  });
  return out;
}

/** Every contradicting pair in the note (each sentence pairs with at most its nearest rival). */
export function findContradictions(doc: PMNode, limit = 200): Contradiction[] {
  const sentences = noteSentences(doc).slice(0, limit);
  const found: Contradiction[] = [];
  for (let i = 0; i < sentences.length; i++) {
    for (let j = i + 1; j < sentences.length; j++) {
      const reason = contradictionBetween(sentences[i].text, sentences[j].text);
      if (reason) found.push({ a: sentences[i], b: sentences[j], reason });
    }
  }
  return found;
}

export const contradictionKey = new PluginKey<DecorationSet>("manifestContradictions");

const quote = (text: string) => (text.length > 90 ? `${text.slice(0, 87)}…` : text);

function decorate(doc: PMNode): DecorationSet {
  const decorations: Decoration[] = [];
  for (const { a, b, reason } of findContradictions(doc)) {
    for (const [mine, other] of [[a, b], [b, a]] as const) {
      decorations.push(
        Decoration.inline(mine.from, mine.to, {
          class: "manifest-contradiction",
          title: `Disagrees with “${quote(other.text)}” (${reason})`,
          "data-contradiction": reason,
          // Shown in the hover card (CSS), so people see what it disagrees with at once.
          "data-disagrees": `Disagrees with “${quote(other.text)}” · ${reason}`,
        }),
      );
    }
  }
  return DecorationSet.create(doc, decorations);
}

/**
 * Highlights contradicting sentences in the note. `enabled()` is read on every change, so
 * it switches on when the note becomes shared without rebuilding the editor.
 */
export const ContradictionHighlight = Extension.create<{ enabled: () => boolean }>({
  name: "contradictionHighlight",
  addOptions() {
    return { enabled: () => false };
  },
  addProseMirrorPlugins() {
    const enabled = () => this.options.enabled();
    return [
      new Plugin<DecorationSet>({
        key: contradictionKey,
        state: {
          init: (_config, state) => (enabled() ? decorate(state.doc) : DecorationSet.empty),
          apply: (tr, value, _old, state) => {
            if (!enabled()) return DecorationSet.empty;
            // Re-scan only when the text changes or the switch flips, not on cursor moves.
            if (!tr.docChanged && !tr.getMeta(contradictionKey)) return value;
            return decorate(state.doc);
          },
        },
        props: { decorations: state => contradictionKey.getState(state) },
      }),
    ];
  },
});
