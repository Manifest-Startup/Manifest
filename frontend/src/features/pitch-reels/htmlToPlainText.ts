/**
 * Convert stored rich-text HTML (e.g. TipTap) to a single line of plain text for Pitch Reels UI.
 */
export function htmlToPlainText(html: string | null | undefined): string {
  if (html == null || typeof html !== "string") {
    return "";
  }
  const trimmed = html.trim();
  if (!trimmed) {
    return "";
  }
  if (typeof DOMParser !== "undefined") {
    try {
      const doc = new DOMParser().parseFromString(trimmed, "text/html");
      const text = doc.body?.textContent ?? "";
      return text.replace(/\s+/g, " ").trim();
    } catch {
      // fall through to regex fallback
    }
  }
  return trimmed.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
}
