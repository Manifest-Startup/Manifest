import React, { useCallback, useId, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FiDownload } from "react-icons/fi";
import {
  DocumentGenerationNotice,
  type DocumentGenerationState,
} from "./DocumentGenerationNotice";
import {
  hasPitchDeckSlideHeadings,
  parsePitchDeckDocument,
  parseSlideTitle,
} from "../../utils/pitchDeckDocument";
import "./documents.css";

type MarkdownDisplayVariant = "default" | "pitch-deck" | "prd" | "legal";
interface MarkdownDisplayProps {
  content: unknown;
  fallbackMessage: string;
  title?: string;
  className?: string;
  variant?: MarkdownDisplayVariant;
  generationState?: DocumentGenerationState | null;
}

// Keep source Markdown intact: headings inside code fences are not document sections.
const documentHeadings = (content: string) => {
  let fence = "";
  return content.split("\n").flatMap((line, index) => {
    const marker = line.match(/^\s{0,3}(`{3,}|~{3,})/);
    if (marker) {
      if (!fence) fence = marker[1];
      else if (marker[1][0] === fence[0] && marker[1].length >= fence.length)
        fence = "";
      return [];
    }
    const heading = !fence && line.match(/^(#{1,2})\s+(.+?)\s*#*$/);
    return heading
      ? [{ level: heading[1].length, title: heading[2], line: index + 1 }]
      : [];
  });
};

export const DocumentMarkdown: React.FC<{ content: string }> = ({
  content,
}) => (
  <ReactMarkdown
    remarkPlugins={[remarkGfm]}
    components={{
      table: ({ children }) => (
        <div
          className="manifest-document-table"
          tabIndex={0}
          role="region"
          aria-label="Document table"
        >
          <table>{children}</table>
        </div>
      ),
    }}
  >
    {content}
  </ReactMarkdown>
);

const PitchDeck: React.FC<{ content: string; title?: string }> = ({
  content,
  title,
}) => {
  const parsed = parsePitchDeckDocument(content, title);
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const download = useCallback(async () => {
    setIsExporting(true);
    setExportError("");
    try {
      const { exportPitchDeckPptx } = await import(
        "../../utils/exportPitchDeckPptx"
      );
      await exportPitchDeckPptx(content, parsed.documentTitle);
    } catch {
      setExportError("Could not download the deck. Please try again.");
    } finally {
      setIsExporting(false);
    }
  }, [content, parsed.documentTitle]);
  return (
    <div className="manifest-deck">
      <header className="manifest-document-header">
        <div>
          <h3>{parsed.documentTitle}</h3>
          <p>{parsed.sections.length} slides · Investor deck</p>
        </div>
        <button
          type="button"
          className="manifest-document-button"
          disabled={isExporting}
          onClick={download}
        >
          <FiDownload aria-hidden="true" />
          {isExporting ? "Preparing…" : "Download PowerPoint"}
        </button>
      </header>
      {exportError && <p role="alert">{exportError}</p>}
      {parsed.sections.map((section, index) => {
        const { slideNumber, slideTitle } = parseSlideTitle(
          section.title,
          index,
        );
        return (
          <section
            className="manifest-slide"
            key={`${section.id}-${index}`}
            aria-label={`Slide ${slideNumber}: ${slideTitle}`}
          >
            <div className="manifest-slide-number">Slide {slideNumber}</div>
            <h4>{slideTitle}</h4>
            <div className="manifest-document-body">
              <DocumentMarkdown content={section.body} />
            </div>
          </section>
        );
      })}
    </div>
  );
};

export const MarkdownDisplay: React.FC<MarkdownDisplayProps> = ({
  content,
  fallbackMessage,
  title,
  className = "",
  variant = "default",
  generationState,
}) => {
  const prefix = useId();
  if (typeof content !== "string" || !content.trim()) {
    return generationState ? (
      <DocumentGenerationNotice
        state={generationState}
        title={title || "Document"}
        variant={variant === "default" ? "prd" : variant}
      />
    ) : (
      <p className="manifest-document-empty">{fallbackMessage}</p>
    );
  }
  const headings = documentHeadings(content);
  const hasSourceTitle = headings[0]?.level === 1;
  const contents = hasSourceTitle ? headings.slice(1) : headings;
  const heading =
    (level: 1 | 2) =>
    ({
      children,
      node,
    }: {
      children?: React.ReactNode;
      node?: { position?: { start: { line: number } } };
    }) => {
      const id = `${prefix}-section-${headings.findIndex((item) => item.line === node?.position?.start.line)}`;
      return level === 1 ? (
        <h1 id={id}>{children}</h1>
      ) : (
        <h2 id={id}>{children}</h2>
      );
    };
  const notice = generationState ? (
    <DocumentGenerationNotice
      layout="inline"
      state={generationState}
      title={title || "Document"}
      variant={variant === "default" ? "prd" : variant}
    />
  ) : null;
  if (variant === "pitch-deck" && hasPitchDeckSlideHeadings(content))
    return (
      <div className={className}>
        {notice}
        <PitchDeck content={content} title={title} />
      </div>
    );
  return (
    <div
      className={`manifest-document manifest-document--${variant} ${className}`}
    >
      {notice}
      <header className="manifest-document-header">
        <div>
          <h3>
            {title ||
              (variant === "prd"
                ? "Product Requirements Document"
                : variant === "legal"
                  ? "Provisional Patent Draft"
                  : "Document")}
          </h3>
          {variant === "legal" && (
            <p>U.S. provisional draft · Inventor and attorney review needed</p>
          )}
        </div>
      </header>
      {contents.length > 1 && (
        <details className="manifest-document-contents">
          <summary>Contents</summary>
          <nav aria-label="Document contents">
            {contents.map((item, i) => (
              <a
                key={i}
                href={`#${prefix}-section-${i + (hasSourceTitle ? 1 : 0)}`}
              >
                {item.title}
              </a>
            ))}
          </nav>
        </details>
      )}
      <article className="manifest-document-body">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: heading(1),
            h2: heading(2),
            table: ({ children }) => (
              <div
                className="manifest-document-table"
                tabIndex={0}
                role="region"
                aria-label="Document table"
              >
                <table>{children}</table>
              </div>
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </article>
    </div>
  );
};
