/**
 * The note editor works in HTML; vault files are Markdown (ADR 0011). These conversions
 * keep what the editor can express: headings, paragraphs, lists, quotes, code, bold,
 * italic, strikethrough, underline (kept as <u>), links and rules.
 */
import { marked } from "marked";
import TurndownService from "turndown";

const turndown = new TurndownService({
  headingStyle: "atx",
  bulletListMarker: "-",
  codeBlockStyle: "fenced",
  emDelimiter: "*",
  strongDelimiter: "**",
  hr: "---",
});
turndown.addRule("strikethrough", {
  filter: ["del", "s"],
  replacement: (content) => `~~${content}~~`,
});
turndown.keep(["u"]);
// Tiptap wraps list item text in <p>; Markdown lists don't need it.
turndown.addRule("listParagraph", {
  filter: (node) => node.nodeName === "P" && node.parentNode?.nodeName === "LI",
  replacement: (content, node) => (node.nextSibling ? `${content}\n\n` : content),
});

export function htmlToMarkdown(html: string): string {
  if (!html || !html.replace(/<[^>]*>/g, "").trim()) return "";
  return turndown
    .turndown(html)
    // "-   item" (Turndown's padding) → "- item", as people write lists by hand.
    .replace(/^(\s*)([-*+]|\d+\.)[ \t]{2,}/gm, "$1$2 ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function markdownToHtml(markdown: string): string {
  if (!markdown.trim()) return "";
  return (marked.parse(markdown, { async: false, gfm: true, breaks: false }) as string).trim();
}

/** True when the HTML has any text (the backend's rule for saving a description). */
export const hasText = (html: string | null | undefined) =>
  Boolean(html && html.replace(/<[^>]*>/g, "").replace(/&nbsp;|&#160;/g, " ").trim());
