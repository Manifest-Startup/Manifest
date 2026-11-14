import React, { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useReactiveVar } from '@apollo/client/react';
import { similarIdeasVar, getSimilarIdeasEntry } from 'features/core/apollo/localState';

interface SimilarIdeasProps {
  similarIdeas?: string;
  ideaId?: string | null;
  compact?: boolean;
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

const loadingBar = 'animate-pulse rounded-full bg-gradient-to-r from-stone-200 via-stone-100 to-stone-200';

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

const AvatarMark: React.FC<{ title: string; url?: string }> = ({ title, url }) => {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const initials = stripMarkdown(title)
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  let hostname = '';
  let faviconUrl = '';
  if (url) {
    try {
      const parsedUrl = new URL(url);
      hostname = parsedUrl.hostname.replace(/^www\./, '');
      faviconUrl = new URL('/favicon.ico', parsedUrl.origin).toString();
    } catch {
      hostname = '';
      faviconUrl = '';
    }
  }

  if (hostname && !failed) {
    return (
      <div className="relative h-12 w-12 shrink-0 overflow-hidden rounded-2xl">
        <div className="absolute inset-0 flex items-center justify-center bg-[linear-gradient(145deg,#1f2937,#4b5563)] text-sm font-semibold uppercase tracking-[0.14em] text-white">
          {initials || 'MI'}
        </div>
        <img
          alt={`${title} logo`}
          className={`absolute inset-0 h-12 w-12 rounded-2xl border border-stone-200 bg-white object-contain p-2 transition-opacity ${
            loaded ? 'opacity-100' : 'opacity-0'
          }`}
          onError={() => setFailed(true)}
          onLoad={() => setLoaded(true)}
          src={faviconUrl}
        />
      </div>
    );
  }

  return (
    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[linear-gradient(145deg,#1f2937,#4b5563)] text-sm font-semibold uppercase tracking-[0.14em] text-white">
      {initials || 'MI'}
    </div>
  );
};

const SimilarIdeasSkeleton: React.FC<{ compact?: boolean }> = ({ compact = false }) => (
  <div className={compact ? 'space-y-4' : 'space-y-6'}>
    <div
      className={compact ? 'manifest-related-card' : 'rounded-[28px] border border-stone-200 bg-[linear-gradient(145deg,#f8fafc,white_62%)] p-5 shadow-soft dark:border-neutral700 dark:bg-[linear-gradient(145deg,#111827,#0f172a_62%)]'}
    >
      <div className={`${loadingBar} h-3 w-28`} />
      <div className={`${loadingBar} mt-4 h-8 ${compact ? 'w-[68%]' : 'w-3/4'}`} />
      <div className={`${loadingBar} mt-3 h-3 w-full`} />
      <div className={`${loadingBar} mt-2 h-3 ${compact ? 'w-11/12' : 'w-10/12'}`} />
    </div>
    <div className="grid gap-4">
      {Array.from({ length: 3 }).map((_, index) => (
        <div
          className={compact ? 'manifest-related-card w-full overflow-hidden' : 'w-full overflow-hidden rounded-[24px] border border-stone-200 bg-white p-5 shadow-soft dark:border-neutral700 dark:bg-neutral900'}
          data-testid="similar-ideas-skeleton-card"
          key={index}
        >
          <div className={compact ? 'flex flex-col gap-3' : 'flex items-start gap-4'}>
            <div className={`${loadingBar} h-12 w-12 shrink-0 rounded-2xl`} />
            <div className="min-w-0 flex-1">
              <div className={`${loadingBar} h-5 ${compact ? 'w-[62%]' : 'w-40'}`} />
              <div className={`${loadingBar} mt-3 h-3 ${compact ? 'w-full' : 'w-56 max-w-full'}`} />
              <div className={`${loadingBar} mt-2 h-3 w-full`} />
              <div className={`${loadingBar} mt-2 h-3 ${compact ? 'w-10/12' : 'w-10/12'}`} />
            </div>
          </div>
        </div>
      ))}
    </div>
  </div>
);

const SimilarIdeas = ({ similarIdeas = '', ideaId = null, compact = false, headerAction = null }: SimilarIdeasProps) => {
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
  const structuredGridClass = compact ? 'mt-4 grid grid-cols-1 gap-3' : 'mt-4 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))]';
  const companyCardLayoutClass = compact ? 'flex flex-col gap-3' : 'flex flex-col gap-4 sm:flex-row sm:items-start';
  const researchCardLayoutClass = compact
    ? 'flex flex-col gap-3'
    : 'flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between';

  return (
    <div
      className={compact ? "manifest-similar-panel flex min-h-0 flex-col" : "flex min-h-0 flex-col overflow-hidden rounded-xl border border-gray200 bg-white shadow-soft transition-colors dark:border-neutral700 dark:bg-neutral800"}
      data-testid="similar-ideas"
      key="similar-ideas"
    >
      {compact ? (
        <div className="manifest-panel-heading">
          <div className="manifest-panel-heading-row">
            <h3 className="manifest-panel-title">Similar ideas</h3>
            {headerAction}
          </div>
        </div>
      ) : (
        <div className="border-b border-gray200 bg-gradient-to-b from-[#f6f4ef] to-white px-5 py-4 dark:border-neutral700 dark:from-neutral800 dark:to-neutral800">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-3">
                <span className="inline-flex items-center rounded-full border border-stone-300 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-neutral700 dark:border-neutral600 dark:bg-neutral900 dark:text-neutral200">
                  Similar
                </span>
                <span className="text-xs uppercase tracking-[0.18em] text-gray500 dark:text-gray400">
                  Competitors and sources
                </span>
              </div>
              <h3 className="mt-3 text-xl font-semibold tracking-tight text-neutral900 dark:text-white">
                Similar Ideas
              </h3>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral700 dark:text-gray300">
                Competitors and research for this idea.
              </p>
            </div>
            {headerAction ? <div className="shrink-0">{headerAction}</div> : null}
          </div>
        </div>
      )}

      <div
        className={`min-h-0 flex-1 space-y-6 overflow-y-auto overflow-x-hidden ${compact ? 'manifest-similar-body' : 'p-5'}`}
        data-testid="similar-ideas-body"
      >
        {isLoading ? (
          <SimilarIdeasSkeleton compact={compact} />
        ) : isEmpty ? (
          <div className={compact ? "manifest-panel-empty" : "rounded-[24px] border border-dashed border-stone-300 bg-stone-50 px-6 py-10 text-center dark:border-neutral700 dark:bg-neutral900/60"}>
            <h4 className="text-lg font-semibold text-neutral900 dark:text-white">No similar ideas yet</h4>
            <p className="mt-2 text-sm leading-6 text-gray500 dark:text-gray400">
              Add more detail to generate competitors and research.
            </p>
          </div>
        ) : hasStructuredData ? (
          <>
            {companies.length > 0 ? (
              <section className="space-y-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h4 className="text-sm font-semibold uppercase tracking-[0.16em] text-gray500 dark:text-gray400">Competitors</h4>
                    {!compact ? (
                      <p className="mt-1 text-sm text-neutral700 dark:text-gray300">Products or categories already serving nearby needs.</p>
                    ) : null}
                  </div>
                  <span className="rounded-full bg-stone-100 px-3 py-1 text-xs font-semibold text-neutral700 dark:bg-neutral700 dark:text-neutral200">
                    {companies.length} found
                  </span>
                </div>
                <div className="grid gap-4">
                  {companies.map((company) => {
                    let domain = '';
                    if (company.url) {
                      try {
                        domain = new URL(company.url).hostname.replace(/^www\./, '');
                      } catch {
                        domain = '';
                      }
                    }

                    return (
                      <article
                        className={compact ? 'manifest-related-card overflow-hidden' : 'overflow-hidden rounded-[24px] border border-stone-200 bg-[linear-gradient(145deg,#fbfaf7,white_58%)] p-5 shadow-soft dark:border-neutral700 dark:bg-[linear-gradient(145deg,#111827,#0f172a_62%)]'}
                        key={`${company.title}-${company.url || company.summary || company.whySimilar || ''}`}
                      >
                        <div className={companyCardLayoutClass}>
                          <AvatarMark title={company.title} url={company.url} />
                          <div className="min-w-0 flex-1">
                            <div className={compact ? 'flex flex-col items-start gap-2' : 'flex flex-wrap items-center gap-2'}>
                              <h5
                                className={`min-w-0 break-words font-semibold tracking-tight text-neutral900 dark:text-white ${
                                  compact ? 'text-base' : 'text-lg'
                                }`}
                              >
                                {company.title}
                              </h5>
                              {domain ? (
                                <span
                                  className={`max-w-full rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.14em] ${
                                    compact
                                      ? 'border-stone-200 bg-stone-50 text-gray500 dark:border-neutral700 dark:bg-neutral800 dark:text-gray400'
                                      : 'border-stone-200 bg-white text-gray500 dark:border-neutral700 dark:bg-neutral800 dark:text-gray400'
                                  }`}
                                >
                                  <span className="block max-w-full truncate">{domain}</span>
                                </span>
                              ) : null}
                            </div>
                            {company.summary ? (
                              <p className={`text-sm leading-6 ${compact ? 'mt-1 text-neutral800 dark:text-gray200' : 'mt-2 text-neutral700 dark:text-gray300'}`}>
                                {company.summary}
                              </p>
                            ) : null}
                            <div className={structuredGridClass}>
                              {company.whySimilar ? (
                                <div
                                  className={`rounded-2xl px-4 py-3 ${
                                    compact
                                      ? 'bg-stone-50 text-neutral700 dark:bg-neutral800 dark:text-gray300'
                                      : 'border border-stone-200 bg-white/90 dark:border-neutral700 dark:bg-neutral800/90'
                                  }`}
                                >
                                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray500 dark:text-gray400">Why</p>
                                  <p className="mt-2 text-sm leading-6 text-neutral700 dark:text-gray300">{company.whySimilar}</p>
                                </div>
                              ) : null}
                              {company.signal ? (
                                <div
                                  className={`rounded-2xl px-4 py-3 ${
                                    compact
                                      ? 'bg-stone-100 text-neutral900 dark:bg-neutral800 dark:text-white'
                                      : 'border border-stone-200 bg-white/90 dark:border-neutral700 dark:bg-neutral800/90'
                                  }`}
                                >
                                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray500 dark:text-gray400">Signal</p>
                                  <p className={`mt-2 text-sm leading-6 ${compact ? 'text-neutral800 dark:text-gray300' : 'text-neutral700 dark:text-gray300'}`}>{company.signal}</p>
                                </div>
                              ) : null}
                            </div>
                            {company.notes.length > 0 ? (
                              <ul className="mt-4 space-y-2 text-sm leading-6 text-neutral700 dark:text-gray300">
                                {company.notes.map((note) => (
                                  <li className="flex gap-2" key={note}>
                                    <span className="mt-2 h-1.5 w-1.5 rounded-full bg-neutral900 dark:bg-white" />
                                    <span>{note}</span>
                                  </li>
                                ))}
                              </ul>
                            ) : null}
                            {company.url ? (
                              <div className="mt-4">
                                <a
                                  className={`inline-flex items-center rounded-full bg-neutral900 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-neutral800 dark:bg-white dark:text-neutral900 dark:hover:bg-neutral100 ${
                                    compact ? 'w-full justify-center' : ''
                                  }`}
                                  href={company.url}
                                  rel="noopener noreferrer"
                                  target="_blank"
                                >
                                  Visit source
                                </a>
                              </div>
                            ) : null}
                          </div>
                        </div>
                      </article>
                    );
                  })}
                </div>
              </section>
            ) : null}

            {research.length > 0 ? (
              <section className="space-y-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h4 className="text-sm font-semibold uppercase tracking-[0.16em] text-gray500 dark:text-gray400">Research</h4>
                    {!compact ? (
                      <p className="mt-1 text-sm text-neutral700 dark:text-gray300">Sources and themes worth checking next.</p>
                    ) : null}
                  </div>
                  <span className="rounded-full bg-stone-100 px-3 py-1 text-xs font-semibold text-neutral700 dark:bg-neutral700 dark:text-neutral200">
                    {research.length} found
                  </span>
                </div>
                <div className="grid gap-4">
                  {research.map((item) => (
                    <article
                      className={compact ? 'manifest-related-card' : 'rounded-[24px] border border-stone-200 bg-white p-5 shadow-soft dark:border-neutral700 dark:bg-neutral900'}
                      key={`${item.title}-${item.sourceSummary || item.validation || ''}`}
                    >
                      <div className={researchCardLayoutClass}>
                        <div className="min-w-0 flex-1">
                          <h5
                            className={`font-semibold tracking-tight text-neutral900 dark:text-white ${
                              compact ? 'text-base' : 'text-lg'
                            }`}
                          >
                            {item.url ? (
                              <a
                                className="relative z-10 inline-flex max-w-full items-center gap-2 hover:text-accent-700 dark:hover:text-accent-200"
                                href={item.url}
                                rel="noopener noreferrer"
                                target="_blank"
                                title={item.url}
                              >
                                <span className="break-words">{item.title}</span>
                                <svg
                                  aria-hidden="true"
                                  className="h-4 w-4 shrink-0"
                                  fill="none"
                                  viewBox="0 0 24 24"
                                  stroke="currentColor"
                                >
                                  <path
                                    d="M7 17 17 7M9 7h8v8"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth="1.8"
                                  />
                                </svg>
                              </a>
                            ) : (
                              item.title
                            )}
                          </h5>
                          {item.sourceSummary ? (
                            <p className="mt-2 text-sm leading-6 text-gray600 dark:text-gray300">
                              <span className="font-semibold text-neutral900 dark:text-white">Suggested sources:</span> {item.sourceSummary}
                            </p>
                          ) : null}
                          {item.sourceLinks.length > 0 ? (
                            <div className="mt-3 flex flex-wrap gap-2">
                              {item.sourceLinks.map((link) => (
                                <a
                                  className={`relative z-10 inline-flex max-w-full cursor-pointer items-center rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
                                    link.type === 'direct'
                                      ? 'border-stone-200 bg-stone-50 text-neutral900 hover:border-stone-300 hover:bg-white dark:border-neutral700 dark:bg-neutral800 dark:text-white dark:hover:border-neutral600'
                                      : 'border-accent-200 bg-accent-50 text-accent-700 hover:bg-accent-100 dark:border-accent-900/50 dark:bg-accent-900/30 dark:text-accent-200'
                                  }`}
                                  href={link.url}
                                  key={`${item.title}-${link.url}`}
                                  rel="noopener noreferrer"
                                  target="_blank"
                                  title={link.url}
                                >
                                  <span className="truncate">{link.label}</span>
                                </a>
                              ))}
                            </div>
                          ) : null}
                        </div>
                        <span className="rounded-full border border-stone-200 bg-stone-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-gray500 dark:border-neutral700 dark:bg-neutral800 dark:text-gray400">
                          Research
                        </span>
                      </div>
                      <div className={structuredGridClass}>
                        {item.importance ? (
                          <div className="rounded-2xl bg-stone-50 px-4 py-3 dark:bg-neutral800">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray500 dark:text-gray400">Why</p>
                            <p className="mt-2 text-sm leading-6 text-gray700 dark:text-gray300">{item.importance}</p>
                          </div>
                        ) : null}
                        {item.validation ? (
                          <div className="rounded-2xl bg-stone-50 px-4 py-3 dark:bg-neutral800">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray500 dark:text-gray400">Validate</p>
                            <p className="mt-2 text-sm leading-6 text-gray700 dark:text-gray300">{item.validation}</p>
                          </div>
                        ) : null}
                      </div>
                      {item.notes.length > 0 ? (
                        <ul className="mt-4 space-y-2 text-sm leading-6 text-gray600 dark:text-gray300">
                          {item.notes.map((note) => (
                            <li className="flex gap-2" key={note}>
                              <span className="mt-2 h-1.5 w-1.5 rounded-full bg-neutral900 dark:bg-white" />
                              <span>{note}</span>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </article>
                  ))}
                </div>
              </section>
            ) : null}
          </>
        ) : (
          <div className="prose prose-sm max-w-none text-neutral700 dark:prose-invert dark:text-gray300">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{resolvedMarkdown}</ReactMarkdown>
          </div>
        )}

        {!isLoading && error ? (
          <p className="text-sm text-amber-700 dark:text-amber-300">
            Landscape refresh hit an issue. Showing the last available output for this idea.
          </p>
        ) : null}
      </div>
    </div>
  );
};

export default SimilarIdeas;
