import React, { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useReactiveVar } from '@apollo/client/react';
import { similarIdeasVar, getSimilarIdeasEntry } from 'features/core/apollo/localState';

interface SimilarIdeasProps {
  similarIdeas?: string;
  ideaId?: string | null;
  headerAction?: React.ReactNode;
}

interface LandscapeCard {
  title: string;
  url?: string;
  summary?: string;
  whySimilar?: string;
  signal?: string;
  notes: string[];
}

interface ResearchSourceLink {
  label: string;
  url: string;
  type: 'direct' | 'search';
}

interface ResearchCard {
  title: string;
  url?: string;
  sourceSummary?: string;
  sourceLinks: ResearchSourceLink[];
  importance?: string;
  validation?: string;
  notes: string[];
}

const unwrapBracketLabel = (value: string) => {
  const trimmed = value.trim();
  const match = trimmed.match(/^\[([^\]]+)\]$/);
  return match ? match[1].trim() : trimmed;
};

const stripMarkdown = (value: string) =>
  unwrapBracketLabel(
    value
      .replace(/\[(.*?)\]\((.*?)\)/g, '$1')
      .replace(/[*_`>#]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim(),
  );

const cleanUrl = (value: string) => value.replace(/[),.;]+$/, '').trim();

const isBlockedSearchUrl = (value: string) => {
  try {
    const parsed = new URL(value);
    const hostname = parsed.hostname.replace(/^www\./, '');
    if (hostname === 'google.com') {
      return parsed.pathname.startsWith('/search') || parsed.pathname.startsWith('/url');
    }
    if (hostname === 'bing.com' || hostname === 'duckduckgo.com') {
      return parsed.pathname.startsWith('/search');
    }
    if (hostname === 'search.yahoo.com') {
      return true;
    }
    if (hostname === 'perplexity.ai') {
      return parsed.pathname.startsWith('/search') || parsed.pathname.startsWith('/discover');
    }
    return false;
  } catch {
    return false;
  }
};

const trimLeadingPunctuation = (value: string) => {
  let cleaned = value;
  while (cleaned.startsWith(' ') || cleaned.startsWith('-') || cleaned.startsWith(':') || cleaned.startsWith(',')) {
    cleaned = cleaned.slice(1);
  }
  return cleaned.trimStart();
};

const extractLink = (value: string) => {
  const markdownLink = value.match(/\[(.*?)\]\((https?:\/\/[^\s)]+)\)/i);
  if (markdownLink) {
    const cleanedUrl = cleanUrl(markdownLink[2]);
    return {
      label: stripMarkdown(markdownLink[1]) || markdownLink[2],
      url: isBlockedSearchUrl(cleanedUrl) ? '' : cleanedUrl,
    };
  }

  const rawUrl = value.match(/https?:\/\/[^\s)]+/i);
  if (rawUrl) {
    const cleanedUrl = cleanUrl(rawUrl[0]);
    return {
      label: trimLeadingPunctuation(stripMarkdown(value.replace(rawUrl[0], ''))) || rawUrl[0],
      url: isBlockedSearchUrl(cleanedUrl) ? '' : cleanedUrl,
    };
  }

  return {
    label: stripMarkdown(value),
    url: '',
  };
};

const dedupeLinks = (links: ResearchSourceLink[]) => {
  const seen = new Set<string>();

  return links.filter((link) => {
    if (!link.url || seen.has(link.url)) {
      return false;
    }

    seen.add(link.url);
    return true;
  });
};

const extractLinksFromText = (value: string) => {
  const links: ResearchSourceLink[] = [];
  const markdownRegex = /\[(.*?)\]\((https?:\/\/[^\s)]+)\)/gi;
  const rawUrlRegex = /https?:\/\/[^\s,)]+/gi;

  for (const match of value.matchAll(markdownRegex)) {
    const url = cleanUrl(match[2]);
    if (isBlockedSearchUrl(url)) {
      continue;
    }
    links.push({
      label: stripMarkdown(match[1]) || cleanUrl(match[2]),
      url,
      type: 'direct',
    });
  }

  for (const match of value.matchAll(rawUrlRegex)) {
    const url = cleanUrl(match[0]);
    if (!isBlockedSearchUrl(url) && !links.some((link) => link.url === url)) {
      links.push({
        label: url.replace(/^https?:\/\//, '').replace(/^www\./, ''),
        url,
        type: 'direct',
      });
    }
  }

  return dedupeLinks(links);
};
const getSourceLinks = (value: string) => extractLinksFromText(value);

const normalizeLabel = (value: string) =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

const splitSections = (markdown: string) => {
  const sections: Array<{ title: string; body: string }> = [];
  let currentTitle = '';
  let currentLines: string[] = [];

  markdown.split('\n').forEach((line) => {
    const match = line.match(/^##\s+(.+)$/);
    if (!match) {
      currentLines.push(line);
      return;
    }

    if (currentTitle) {
      sections.push({ title: currentTitle, body: currentLines.join('\n').trim() });
    }

    currentTitle = match[1].trim();
    currentLines = [];
  });

  if (currentTitle) {
    sections.push({ title: currentTitle, body: currentLines.join('\n').trim() });
  }

  return sections;
};

const splitEntries = (body: string) => {
  const entries: Array<{ title: string; lines: string[] }> = [];
  let currentTitle = '';
  let currentLines: string[] = [];

  body.split('\n').forEach((line) => {
    const headingMatch = line.match(/^###\s+(.+)$/);
    if (!headingMatch) {
      currentLines.push(line);
      return;
    }

    if (currentTitle) {
      entries.push({ title: currentTitle, lines: currentLines });
    }

    currentTitle = headingMatch[1].trim();
    currentLines = [];
  });

  if (currentTitle) {
    entries.push({ title: currentTitle, lines: currentLines });
  }

  return entries;
};

const parseLandscapeCard = (title: string, lines: string[]): LandscapeCard => {
  const titleLink = extractLink(title);
  const card: LandscapeCard = {
    title: titleLink.label || stripMarkdown(title),
    url: titleLink.url || undefined,
    notes: [],
  };

  lines
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const bullet = line.replace(/^[-*]\s+/, '');
      const labelMatch = bullet.match(/^([^:]+):\s*(.+)$/);

      if (!labelMatch) {
        card.notes.push(stripMarkdown(bullet));
        return;
      }

      const label = normalizeLabel(labelMatch[1]);
      const value = labelMatch[2].trim();

      if (label === 'url' || label === 'website' || label === 'source url' || label === 'link') {
        const extractedUrl = extractLink(value).url;
        if (extractedUrl) {
          card.url = extractedUrl;
        }
        return;
      }

      if (label === 'summary' || label === 'snapshot' || label === 'description') {
        card.summary = stripMarkdown(value);
        return;
      }

      if (label === 'why similar' || label === 'similarity' || label === 'reason') {
        card.whySimilar = stripMarkdown(value);
        return;
      }

      if (label === 'distinguishing signal' || label === 'signal' || label === 'differentiator' || label === 'wedge') {
        card.signal = stripMarkdown(value);
        return;
      }

      card.notes.push(`${labelMatch[1].trim()}: ${stripMarkdown(value)}`);
    });

  return card;
};

const parseResearchCard = (title: string, lines: string[]): ResearchCard => {
  const titleLink = extractLink(title);
  const titleLabel = titleLink.label || stripMarkdown(title);
  const card: ResearchCard = {
    title: titleLabel,
    url: titleLink.url || undefined,
    sourceLinks: [],
    notes: [],
  };

  lines
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const bullet = line.replace(/^[-*]\s+/, '');
      const labelMatch = bullet.match(/^([^:]+):\s*(.+)$/);

      if (!labelMatch) {
        card.notes.push(stripMarkdown(bullet));
        return;
      }

      const label = normalizeLabel(labelMatch[1]);
      const rawValue = labelMatch[2].trim();
      const value = stripMarkdown(rawValue);

      if (label === 'suggested sources' || label === 'sources' || label === 'source') {
        card.sourceSummary = value;
        card.sourceLinks = dedupeLinks([...card.sourceLinks, ...getSourceLinks(rawValue)]);
        return;
      }

      if (label === 'why it matters' || label === 'importance' || label === 'why this matters') {
        card.importance = value;
        return;
      }

      if (label === 'what to validate' || label === 'validation' || label === 'next check') {
        card.validation = value;
        return;
      }

      card.notes.push(`${labelMatch[1].trim()}: ${value}`);
    });

  return card;
};

const parseSimilarIdeas = (markdown: string) => {
  const sections = splitSections(markdown);
  const companies: LandscapeCard[] = [];
  const research: ResearchCard[] = [];

  sections.forEach((section) => {
    const entries = splitEntries(section.body);
    const normalizedTitle = normalizeLabel(section.title);

    if (normalizedTitle.includes('comparable') || normalizedTitle.includes('company') || normalizedTitle.includes('landscape')) {
      if (entries.length) {
        entries.forEach((entry) => companies.push(parseLandscapeCard(entry.title, entry.lines)));
      }
      return;
    }

    if (
      normalizedTitle.includes('research') ||
      normalizedTitle.includes('literature') ||
      normalizedTitle.includes('watchlist') ||
      normalizedTitle.includes('emerging')
    ) {
      if (entries.length) {
        entries.forEach((entry) => research.push(parseResearchCard(entry.title, entry.lines)));
      }
    }
  });

  return { companies, research };
};

const hostOf = (url?: string) => {
  if (!url) {
    return '';
  }
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
};

const LogoMark: React.FC<{ title: string; url?: string }> = ({ title, url }) => {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const initials = stripMarkdown(title)
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  let faviconUrl = '';
  if (url) {
    try {
      faviconUrl = new URL('/favicon.ico', new URL(url).origin).toString();
    } catch {
      faviconUrl = '';
    }
  }

  return (
    <span className="manifest-related-logo" aria-hidden="true">
      <span>{initials || '·'}</span>
      {faviconUrl && !failed ? (
        <img
          alt=""
          data-loaded={loaded}
          loading="lazy"
          onError={() => setFailed(true)}
          onLoad={() => setLoaded(true)}
          src={faviconUrl}
        />
      ) : null}
    </span>
  );
};

interface RelatedRowProps {
  title: string;
  href?: string;
  line?: string;
  detail?: string;
  index: number;
}

/** One result, one line: logo, name, source and a single sentence. Details live in the tooltip. */
const RelatedRow: React.FC<RelatedRowProps> = ({ title, href, line, detail, index }) => {
  const domain = hostOf(href);
  const body = (
    <>
      <LogoMark title={title} url={href} />
      <span className="manifest-related-text">
        <span className="manifest-related-name">
          <span className="truncate">{title}</span>
          {domain ? <span className="manifest-related-domain max-w-full truncate">{domain}</span> : null}
        </span>
        {line ? <span className="manifest-related-line">{line}</span> : null}
      </span>
      {href ? (
        <svg className="manifest-related-arrow" aria-hidden="true" viewBox="0 0 12 12" fill="none" stroke="currentColor">
          <path d="M4 8 8 4M5 4h3v3" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : null}
    </>
  );

  return (
    <li className="manifest-related-item" style={{ '--i': index } as React.CSSProperties}>
      {href ? (
        <a className="manifest-related-row" href={href} rel="noopener noreferrer" target="_blank" title={detail || line}>
          {body}
        </a>
      ) : (
        <div className="manifest-related-row" title={detail || line}>
          {body}
        </div>
      )}
    </li>
  );
};

const SimilarIdeasSkeleton: React.FC = () => (
  <div className="manifest-related-skeleton" role="status">
    <span className="sr-only">Finding similar ideas…</span>
    {Array.from({ length: 4 }).map((_, index) => (
      <div className="manifest-related-skeleton-row" data-testid="similar-ideas-skeleton-card" key={index}>
        <i />
        <div>
          <b />
          <b />
        </div>
      </div>
    ))}
  </div>
);

const joinDetail = (...parts: Array<string | undefined>) => parts.filter(Boolean).join('\n\n');

const SimilarIdeas = ({ similarIdeas = '', ideaId = null, headerAction = null }: SimilarIdeasProps) => {
  const similarIdeasState = useReactiveVar(similarIdeasVar);
  const entry = ideaId ? getSimilarIdeasEntry(similarIdeasState, ideaId) : null;
  const isLoading =
    entry?.loading ??
    (ideaId ? similarIdeasState.ideaId === ideaId && similarIdeasState.loading : similarIdeasState.loading);
  const error =
    entry?.error ??
    (ideaId ? (similarIdeasState.ideaId === ideaId ? similarIdeasState.error : null) : similarIdeasState.error);
  const resolvedMarkdown =
    typeof similarIdeas === 'string' && similarIdeas.trim()
      ? similarIdeas
      : entry?.data || (ideaId && similarIdeasState.ideaId !== ideaId ? '' : similarIdeasState.data);
  const isEmpty = typeof resolvedMarkdown !== 'string' || resolvedMarkdown.trim() === '';
  const { companies, research } = useMemo(
    () => (isEmpty ? { companies: [], research: [] } : parseSimilarIdeas(resolvedMarkdown)),
    [isEmpty, resolvedMarkdown],
  );
  const hasStructuredData = companies.length > 0 || research.length > 0;

  return (
    <div className="manifest-similar-panel manifest-related flex min-h-0 flex-col" data-testid="similar-ideas">
      <header className="manifest-related-header">
        <h3 className="manifest-related-title">Similar ideas</h3>
        {headerAction}
      </header>

      <div className="manifest-related-body min-h-0 flex-1 overflow-y-auto overflow-x-hidden" data-testid="similar-ideas-body">
        {isLoading ? (
          <SimilarIdeasSkeleton />
        ) : isEmpty ? (
          <div className="manifest-related-note">
            <h4>No similar ideas yet</h4>
            <p>Add more detail to generate competitors and research.</p>
          </div>
        ) : hasStructuredData ? (
          <>
            {companies.length > 0 ? (
              <section aria-labelledby="related-competitors">
                <h4 className="manifest-related-label" id="related-competitors">
                  Competitors <span>{companies.length}</span>
                </h4>
                <ul className="manifest-related-list">
                  {companies.map((company, index) => (
                    <RelatedRow
                      detail={joinDetail(company.summary, company.whySimilar, company.signal, ...company.notes)}
                      href={company.url}
                      index={index}
                      key={`${company.title}-${company.url || ''}`}
                      line={company.summary || company.signal || company.whySimilar}
                      title={company.title}
                    />
                  ))}
                </ul>
              </section>
            ) : null}

            {research.length > 0 ? (
              <section aria-labelledby="related-research">
                <h4 className="manifest-related-label" id="related-research">
                  Research <span>{research.length}</span>
                </h4>
                <ul className="manifest-related-list">
                  {research.map((item, index) => (
                    <RelatedRow
                      detail={joinDetail(item.importance, item.validation && `Validate: ${item.validation}`, ...item.notes)}
                      href={item.url || item.sourceLinks[0]?.url}
                      index={companies.length + index}
                      key={`${item.title}-${item.url || item.sourceSummary || ''}`}
                      line={item.importance || item.validation || item.sourceSummary}
                      title={item.title}
                    />
                  ))}
                </ul>
              </section>
            ) : null}
          </>
        ) : (
          <div className="prose prose-sm max-w-none text-neutral700 dark:prose-invert dark:text-gray300">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{resolvedMarkdown}</ReactMarkdown>
          </div>
        )}

        {!isLoading && error ? (
          <p className="manifest-related-warning">Landscape refresh hit an issue. Showing the last available output for this idea.</p>
        ) : null}
      </div>
    </div>
  );
};

export default SimilarIdeas;
