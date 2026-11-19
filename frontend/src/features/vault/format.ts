/**
 * How an idea looks on disk in a local vault (ADR 0011): plain Markdown the founder owns,
 * readable in Obsidian, iA Writer or any editor.
 *
 *   Manifest/Ideas/<Title>.md                     the idea note
 *   Manifest/Documents/<Title>/<Document>.md      generated or written documents
 *
 * An idea note is YAML frontmatter, a `# Title` line and the note in Markdown:
 *
 *   ---
 *   manifest_id: 6c1f…
 *   type: idea
 *   created: 2026-11-19T10:00:00.000Z
 *   updated: 2026-11-19T10:05:00.000Z
 *   published: false
 *   skills: [Embedded Systems, Sales]
 *   ---
 *   # TideLine
 *
 *   Coastal neighborhoods flood street by street…
 *
 * Files exported from a Manifest account (ADR 0005) also open: the generated block is read
 * and the founder's own writing after it is kept.
 */

export const ROOT = "Manifest";
export const IDEAS_DIR = `${ROOT}/Ideas`;
export const DOCUMENTS_DIR = `${ROOT}/Documents`;
export const TRASH_DIR = `${ROOT}/.trash`;

/** GraphQL document field → file name (the same names the account export uses). */
export const DOCUMENT_FILES: Record<string, string> = {
  businessModelCanvas: "Business Model Canvas",
  pitchDeck: "Pitch Deck",
  productRequirementsDocument: "Product Requirements",
  provisionalPatent: "Provisional Patent Draft",
  similarIdeas: "Similar Ideas",
};

const BEGIN = "<!-- manifest:begin";
const END = "<!-- manifest:end -->";

export interface IdeaFile {
  id: string | null;
  title: string;
  created: string | null;
  updated: string | null;
  published: boolean;
  skills: string[];
  /** The note as Markdown. */
  body: string;
  /** Frontmatter keys Manifest doesn't use, kept as written. */
  extra: string[];
  /** Writing after an account export's generated block, kept as written. */
  tail: string;
}

/** A file-safe, readable name (same rules as the account export's `safe_name`). */
export function safeName(text: string, fallback = "Untitled idea"): string {
  const name = String(text || "")
    .replace(/[\\/:*?"<>|#^[\]\n\r\t]+/g, " ")
    .trim()
    .replace(/^\.+|\.+$/g, "");
  return name.replace(/\s+/g, " ").slice(0, 120) || fallback;
}

const unquote = (value: string) => {
  const v = value.trim();
  if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
    return v.slice(1, -1).replace(/\\"/g, '"');
  }
  return v;
};

const quote = (value: string) =>
  /^[\w .@:+-]+$/.test(value) && !/^(true|false|null|yes|no|\d)/i.test(value)
    ? value
    : JSON.stringify(value);

function parseList(value: string, following: string[]): string[] {
  const v = value.trim();
  if (v.startsWith("[")) {
    // Items may be quoted and contain commas: ["Sales, B2B", Design].
    const inner = v.replace(/^\[|\]$/g, "");
    const items = [...inner.matchAll(/\s*("(?:[^"\\]|\\.)*"|'[^']*'|[^,]+)/g)].map((m) => m[1]);
    return items.map(unquote).filter(Boolean);
  }
  return following.map((line) => unquote(line.replace(/^\s*-\s*/, ""))).filter(Boolean);
}

export function parseIdeaFile(text: string, fallbackTitle: string): IdeaFile {
  const file: IdeaFile = {
    id: null,
    title: fallbackTitle,
    created: null,
    updated: null,
    published: false,
    skills: [],
    body: "",
    extra: [],
    tail: "",
  };
  let rest = text.replace(/^\uFEFF/, "");
  const front = rest.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
  if (front) {
    rest = rest.slice(front[0].length);
    const lines = front[1].split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const match = line.match(/^([A-Za-z_][\w-]*):\s*(.*)$/);
      if (!match) continue;
      const [, key, value] = match;
      const block: string[] = [];
      while (i + 1 < lines.length && /^\s+-\s/.test(lines[i + 1])) block.push(lines[++i]);
      if (key === "manifest_id" || key === "id") file.id = unquote(value) || null;
      else if (key === "created") file.created = unquote(value) || null;
      else if (key === "updated") file.updated = unquote(value) || null;
      else if (key === "published") file.published = /^(true|yes)$/i.test(value.trim());
      else if (key === "skills" || key === "required_skills") file.skills = parseList(value, block);
      else if (key === "title") file.title = unquote(value) || fallbackTitle;
      else if (key !== "type") file.extra.push(line, ...block);
    }
  }
  // An account export: the note is the generated block's sentences, the rest is theirs.
  const begin = rest.indexOf(BEGIN);
  const end = rest.indexOf(END);
  if (begin !== -1 && end > begin) {
    const block = rest.slice(rest.indexOf("\n", begin) + 1, end);
    file.tail = rest.slice(end + END.length).trim();
    rest = block
      .split(/\n## /)[0]
      .split("\n")
      .map((line) => line.replace(/\s\^[pa]\d+\s*$/, ""))
      .join("\n");
  }
  const heading = rest.match(/^\s*#\s+(.+?)\s*#*\s*(\r?\n|$)/);
  if (heading) {
    file.title = heading[1].trim() || file.title;
    rest = rest.slice(heading[0].length);
  }
  file.body = rest.replace(/^\s*\n/, "").trimEnd();
  return file;
}

export function serializeIdeaFile(file: IdeaFile): string {
  const front = [
    `manifest_id: ${file.id}`,
    "type: idea",
    file.created ? `created: ${file.created}` : null,
    file.updated ? `updated: ${file.updated}` : null,
    `published: ${file.published ? "true" : "false"}`,
    `skills: [${file.skills.map(quote).join(", ")}]`,
    ...file.extra,
  ].filter((line): line is string => line !== null);
  const parts = [`---\n${front.join("\n")}\n---`, `# ${file.title.trim() || "Untitled idea"}`];
  if (file.body.trim()) parts.push(file.body.trim());
  if (file.tail.trim()) parts.push(file.tail.trim());
  return `${parts.join("\n\n")}\n`;
}

/** A new, random idea id (UUID v4 when the browser has crypto). */
export function newIdeaId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `local-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
