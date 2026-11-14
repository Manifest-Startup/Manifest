export interface ParsedSection {
  body: string;
  id: string;
  level: number;
  title: string;
}

export interface ParsedPitchDeck {
  documentTitle: string;
  sections: ParsedSection[];
  summary: string;
}

export const SLIDE_HEADING_PATTERN = /^Slide\s+(\d+):\s*(.+)$/i;

const slugify = (value: string) =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

export const stripMarkdown = (value: string) =>
  value
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/[*_>#-]/g, " ")
    .replace(/\[(.*?)\]\(.*?\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();

export const hasPitchDeckSlideHeadings = (content: string) =>
  content
    .split("\n")
    .some((line) => /^#{1,6}\s+Slide\s+\d+:/i.test(line.trim()));

export const parseSlideTitle = (title: string, fallbackIndex: number) => {
  const slideMatch = title.match(SLIDE_HEADING_PATTERN);
  return {
    slideNumber: slideMatch?.[1] || String(fallbackIndex + 1),
    slideTitle: slideMatch?.[2] || title,
  };
};

export const parseMarkdownTable = (body: string, includeHeader = false) =>
  body
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("|"))
    .filter((_, index) => index !== 1 && (includeHeader || index !== 0))
    .map((line) =>
      line
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split(/(?<!\\)\|/)
        .map((cell) => stripMarkdown(cell.trim()).replace(/\\\|/g, "|")),
    )
    .filter((cells) => cells.length >= 2);

export const parsePitchDeckDocument = (
  content: string,
  fallbackTitle?: string,
): ParsedPitchDeck => {
  const lines = content.split("\n");
  const sections: ParsedSection[] = [];
  let currentTitle = "";
  let currentLines: string[] = [];

  const flushSection = () => {
    if (!currentTitle) {
      return;
    }

    sections.push({
      body: currentLines.join("\n").trim(),
      id: slugify(currentTitle),
      level: 1,
      title: currentTitle,
    });

    currentTitle = "";
    currentLines = [];
  };

  lines.forEach((line) => {
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (!headingMatch) {
      if (currentTitle) {
        currentLines.push(line);
      }
      return;
    }

    const heading = headingMatch[2].trim();
    if (!SLIDE_HEADING_PATTERN.test(heading)) {
      if (currentTitle) {
        currentLines.push(line);
      }
      return;
    }

    flushSection();
    currentTitle = heading;
  });

  flushSection();

  const documentTitle = fallbackTitle?.trim() || "Pitch Deck";
  const summarySource = stripMarkdown(sections[0]?.body || "");
  const summary =
    summarySource.length > 220
      ? `${summarySource.slice(0, 217).trimEnd()}...`
      : summarySource;

  return {
    documentTitle,
    sections,
    summary,
  };
};

export interface SlideBodyPart {
  kind: "paragraph" | "bullet" | "table";
  text?: string;
  rows?: string[][];
}

export const parseSlideBody = (body: string): SlideBodyPart[] => {
  const parts: SlideBodyPart[] = [];
  const lines = body.split("\n");
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();

    if (!line) {
      index += 1;
      continue;
    }

    if (line.startsWith("|")) {
      const tableLines: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        tableLines.push(lines[index].trim());
        index += 1;
      }

      const rows = parseMarkdownTable(tableLines.join("\n"), true);
      if (rows.length) {
        parts.push({ kind: "table", rows });
      }
      continue;
    }

    if (/^[-*]\s+/.test(line) || /^\d+\.\s+/.test(line)) {
      const bullets: string[] = [];
      while (index < lines.length) {
        const bulletLine = lines[index].trim();
        if (!/^[-*]\s+/.test(bulletLine) && !/^\d+\.\s+/.test(bulletLine)) {
          break;
        }
        bullets.push(
          stripMarkdown(
            bulletLine.replace(/^[-*]\s+/, "").replace(/^\d+\.\s+/, ""),
          ),
        );
        index += 1;
      }
      parts.push({ kind: "bullet", text: bullets.join("\n") });
      continue;
    }

    const paragraphLines: string[] = [line];
    index += 1;
    while (index < lines.length) {
      const nextLine = lines[index].trim();
      if (
        !nextLine ||
        nextLine.startsWith("|") ||
        /^[-*]\s+/.test(nextLine) ||
        /^\d+\.\s+/.test(nextLine)
      ) {
        break;
      }
      paragraphLines.push(nextLine);
      index += 1;
    }
    parts.push({
      kind: "paragraph",
      text: stripMarkdown(paragraphLines.join(" ")),
    });
  }

  return parts;
};

export const sanitizeFilename = (value: string) =>
  value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "pitch-deck";
