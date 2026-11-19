/**
 * Obsidian-style [[wiki-links]] in Manifest documents (ADR 0006).
 *
 * The backend cites every document line back to the idea note with
 * `[[Manifest/Ideas/<idea>#^p3|↩]]` and links concepts with
 * `[[Manifest/Concepts/<concept>|text]]`; the local vault shows the same links.
 * Here they become in-app routes, so the app and the Markdown files agree.
 */
import type { IdeaKnowledgeGraphData } from "features/core/apollo/queries";

export type KnowledgeGraph = NonNullable<IdeaKnowledgeGraphData["ideaKnowledgeGraph"]>;
export type WikiResolver = (target: string, anchor?: string) => string | null;

export const CITE_LABEL = "↩";
const WIKI_LINK = /\[\[([^\]|#]+)(?:#([^\]|]*))?(?:\|([^\]]+))?\]\]/g;

/** Document type (backend column) → idea page aspect slug. */
export const DOCUMENT_ASPECTS: Record<string, string> = {
  business_model_canvas: "business-model-canvas",
  pitch_deck: "pitch-deck",
  product_requirements_document: "product-requirements-document",
  provisional_patent: "patent",
};
/** Vault document file name → aspect slug. */
const DOCUMENT_FILE_ASPECTS: Record<string, string> = {
  "Business Model Canvas": "business-model-canvas",
  "Pitch Deck": "pitch-deck",
  "Product Requirements": "product-requirements-document",
  "Provisional Patent Draft": "patent",
};

const lastSegment = (path: string) => path.split("/").pop() || path;

/** Replace wiki links with Markdown links (resolved) or their label (unresolved). */
export function wikiLinksToMarkdown(markdown: string, resolve?: WikiResolver): string {
  return markdown.replace(WIKI_LINK, (_match, target: string, anchor?: string, label?: string) => {
    const text = (label || lastSegment(target)).replace(/[[\]]/g, "").trim();
    const href = resolve?.(target.trim(), anchor?.trim());
    return href ? `[${text}](<${href}>)` : text;
  });
}

/** The document as stored, i.e. with the generated citations and concept links removed. */
export function stripCitations(markdown: string): string {
  return markdown
    .replace(/\n\nSource: \[\[[^\]]*\]\]$/, "")
    .replace(/ \[\[[^\]]*\|↩\]\]/g, "")
    .replace(WIKI_LINK, (_m, target: string, _a?: string, label?: string) => label || lastSegment(target));
}

/** Cited Markdown for a document, but only while it still matches what is stored. */
export function citedFor(
  graph: KnowledgeGraph | null | undefined,
  documentType: string,
  raw: unknown,
): string | null {
  if (!graph || typeof raw !== "string" || !raw.trim()) return null;
  const cited = graph.documents.find((d) => d.documentType === documentType)?.markdown;
  if (!cited) return null;
  const norm = (text: string) =>
    text
      .split("\n")
      .map((line) => line.trimEnd())
      .join("\n")
      .trim();
  return norm(stripCitations(cited)) === norm(raw) ? cited : null;
}

/** Resolve vault paths to app routes for one idea's graph. */
export function makeResolver(graph: KnowledgeGraph | null | undefined): WikiResolver | undefined {
  if (!graph) return undefined;
  const ideaByPath = new Map<string, string>([[graph.ideaPath, graph.ideaId]]);
  for (const ref of [...graph.related, ...graph.concepts.flatMap((c) => c.ideas)]) {
    ideaByPath.set(ref.path, ref.ideaId);
  }
  const ideaByName = new Map(
    [...ideaByPath.entries()].map(([path, id]) => [lastSegment(path), id]),
  );
  return (target, anchor) => {
    const ideaId = ideaByPath.get(target);
    if (ideaId) {
      const cite = anchor?.startsWith("^") ? `?cite=${encodeURIComponent(anchor.slice(1))}` : "";
      return `/ideas/${ideaId}/description${cite}`;
    }
    if (target.startsWith("Manifest/Concepts/")) {
      // A concept opens the note with every place the founder wrote it highlighted.
      return `/ideas/${graph.ideaId}/description?mark=${encodeURIComponent(lastSegment(target))}`;
    }
    if (target.startsWith("Manifest/Documents/")) {
      const [, , folder, file] = target.split("/");
      const owner = ideaByName.get(folder ?? "");
      const aspect = DOCUMENT_FILE_ASPECTS[file ?? ""];
      return owner && aspect ? `/ideas/${owner}/${aspect}` : null;
    }
    return null;
  };
}

/** The passage a citation href points at (`?cite=p3`), if any. */
export function citedPassageId(href: string | undefined): string | null {
  const match = href?.match(/[?&]cite=([^&#]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}
