import React, { createContext, useContext } from "react";
import { Link } from "react-router-dom";
import {
  CITE_LABEL,
  citedPassageId,
  wikiLinksToMarkdown,
  type KnowledgeGraph,
  type WikiResolver,
} from "./wikiLinks";

interface WikiLinksValue {
  graph?: KnowledgeGraph | null;
  resolve?: WikiResolver;
}

const WikiLinksContext = createContext<WikiLinksValue>({});

export const WikiLinksProvider = WikiLinksContext.Provider;
export const useWikiLinks = () => useContext(WikiLinksContext);

/** Markdown with [[wiki-links]] turned into app links (or plain text when unresolved). */
export const useWikiMarkdown = (content: string) => {
  const { resolve } = useWikiLinks();
  return content.includes("[[") ? wikiLinksToMarkdown(content, resolve) : content;
};

/** `a` renderer for ReactMarkdown: in-app routes use the router; citations become chips. */
export const WikiAnchor: React.FC<React.AnchorHTMLAttributes<HTMLAnchorElement> & { node?: unknown }> = ({
  href,
  children,
  node: _node,
  ...rest
}) => {
  const { graph } = useWikiLinks();
  if (!href || !href.startsWith("/")) {
    return (
      <a href={href} target="_blank" rel="noreferrer noopener" {...rest}>
        {children}
      </a>
    );
  }
  const passageId = citedPassageId(href);
  const isCitation = React.Children.toArray(children).join("") === CITE_LABEL;
  if (isCitation) {
    const passage = graph?.passages.find((p) => p.id === passageId);
    const where = passage?.kind === "answer" ? "your interview" : "your idea note";
    const label = passage ? `Source, ${where}: “${passage.text}”` : "Source: your idea note";
    return (
      <Link to={href} className="manifest-cite" title={label} aria-label={label}>
        {passageId ?? CITE_LABEL}
      </Link>
    );
  }
  return (
    <Link to={href} className="manifest-wiki-link">
      {children}
    </Link>
  );
};
