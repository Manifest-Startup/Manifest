/**
 * Where a document's claim came from, shown in the idea note itself (ADR 0010).
 *
 * `?cite=p3` highlights that sentence of the note; `?mark=<Concept>` highlights every place
 * the founder wrote that concept. A citation of an interview answer (`?cite=a2`) can't be
 * highlighted in the note, so its words are quoted above it.
 */
import React from "react";
import { useSearchParams } from "react-router-dom";
import type { KnowledgeGraph } from "./wikiLinks";
import type { HighlightTarget } from "./sourceHighlight";

const lastSegment = (path: string) => path.split("/").pop() || path;

export function sourceTargets(
  graph: KnowledgeGraph | null | undefined,
  params: URLSearchParams,
): HighlightTarget[] {
  const targets: HighlightTarget[] = [];
  const cite = params.get("cite");
  if (cite && graph) {
    for (const id of cite.split(",")) {
      const passage = graph.passages.find((p) => p.id === id && p.kind === "note");
      if (passage) targets.push({ text: passage.text });
    }
  }
  const mark = params.get("mark");
  if (mark) {
    const concept = graph?.concepts.find(
      (c) => lastSegment(c.path).toLowerCase() === mark.toLowerCase(),
    );
    const names = concept
      ? [concept.label, ...(concept.aliases ?? []).filter((a) => a.includes(" "))]
      : [mark];
    targets.push(...names.map((text) => ({ text, phrase: true })));
  }
  return targets;
}

/** A cited interview answer, quoted above the note (it isn't part of the note's text). */
export const InterviewQuote: React.FC<{ graph: KnowledgeGraph | null | undefined }> = ({ graph }) => {
  const [params, setParams] = useSearchParams();
  const id = params.get("cite");
  const answer = id ? graph?.passages.find((p) => p.id === id && p.kind === "answer") : undefined;
  if (!answer) return null;
  const close = () => {
    const next = new URLSearchParams(params);
    next.delete("cite");
    setParams(next, { replace: true });
  };
  return (
    <figure className="manifest-source-quote" aria-label="Cited interview answer">
      <blockquote>
        <mark className="manifest-source-mark">{answer.text}</mark>
      </blockquote>
      <figcaption>
        Your words from the qualification interview.
        <button type="button" onClick={close} aria-label="Hide quote">
          Hide
        </button>
      </figcaption>
    </figure>
  );
};
