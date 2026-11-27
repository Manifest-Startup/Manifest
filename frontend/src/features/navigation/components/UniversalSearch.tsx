import React, { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { useApolloClient, useMutation } from "@apollo/client/react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";

import { useSafeQuery } from "features/common-ui/api/useSafeQuery";
import { CREATE_IDEA, GET_IDEAS, UNIVERSAL_SEARCH } from "features/core/apollo/queries";
import { sidebarVar } from "features/core/apollo/localState";
import { useMessage } from "features/notifications/context/MessageContext";
import { safeNavigate } from "utils/safeNavigate";
import { subscribeToVoiceSearchCommand } from "features/voice/voiceCommandEvents";

interface IdeaListItem {
  ideaId: string;
  title: string;
  description?: string | null;
  isPublished?: boolean;
}

interface SearchIdeaResult {
  ideaId: string;
  title: string;
  snippet: string;
  matchedIn?: string | null;
  createdAt: string;
  userId: string;
  isPublished: boolean;
  creatorName?: string | null;
  creatorAvatar?: string | null;
}

interface SearchWebSource {
  title: string;
  url: string;
  hostname?: string | null;
}

interface SearchMessageResult {
  conversationId: string;
  kind: string;
  title: string;
  preview?: string | null;
  lastMessageAt: string;
  unreadCount: number;
  ideaTitle?: string | null;
}

interface UniversalSearchPayload {
  query: string;
  assistantSummary?: string | null;
  webSummary?: string | null;
  myIdeas: SearchIdeaResult[];
  publishedIdeas: SearchIdeaResult[];
  webSources: SearchWebSource[];
  messages?: SearchMessageResult[];
}

interface UniversalSearchResponse {
  universalSearch: UniversalSearchPayload;
}

interface IdeasResponse {
  ideas: IdeaListItem[];
}

interface PaletteItem {
  id: string;
  section: string;
  kind: "action" | "idea" | "published" | "web" | "message";
  title: string;
  subtitle: string;
  meta?: string;
  actionLabel: string;
  creatorName?: string | null;
  sources?: SearchWebSource[];
  onSelect: () => void | Promise<void>;
}

interface SearchState {
  results: UniversalSearchPayload | null;
  loading: boolean;
  webLoading: boolean;
  error: string | null;
}

const RESULT_LIMIT = 4;

const ChatIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h8M8 14h5m-9 6l2.4-3.2A8 8 0 1 1 20 12a8 8 0 0 1-8 8H4z" />
  </svg>
);

const stripMarkup = (value?: string | null) =>
  (value || "")
    .replace(/<[^>]*>/g, " ")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();

const isEditableTarget = (target: EventTarget | null) => {
  if (!(target instanceof HTMLElement)) {
    return false;
  }

  if (target.isContentEditable) {
    return true;
  }

  const tagName = target.tagName.toLowerCase();
  return tagName === "input" || tagName === "textarea" || tagName === "select";
};

const buildIdeaTitle = (value: string, fallback = "Brand New Idea") => {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized ? normalized.slice(0, 80) : fallback;
};

const buildSeedDescription = (
  query: string,
  results: UniversalSearchPayload | null,
  selectedPublishedIdea?: SearchIdeaResult
) => {
  const normalizedQuery = buildIdeaTitle(query, "Brand New Idea");
  const lines: string[] = [`Idea seed: ${normalizedQuery}`];

  if (results?.assistantSummary) {
    lines.push(`Manifest search synthesis:\n${results.assistantSummary}`);
  } else if (results?.webSummary) {
    lines.push(`Web research summary:\n${results.webSummary}`);
  } else {
    lines.push("Direction:\nTurn this search into a differentiated startup idea with a clear customer, product, and go-to-market angle.");
  }

  if (selectedPublishedIdea) {
    const creator = selectedPublishedIdea.creatorName ? ` by ${selectedPublishedIdea.creatorName}` : "";
    lines.push(
      `Published inspiration:\n${selectedPublishedIdea.title}${creator}\n${selectedPublishedIdea.snippet}`
    );
  }

  if (results?.myIdeas?.length) {
    lines.push(
      `Relevant internal notes:\n${results.myIdeas
        .slice(0, 3)
        .map((idea) => `- ${idea.title}: ${idea.snippet}`)
        .join("\n")}`
    );
  }

  if (results?.publishedIdeas?.length) {
    lines.push(
      `Related published ideas:\n${results.publishedIdeas
        .slice(0, 3)
        .map((idea) => {
          const creator = idea.creatorName ? ` by ${idea.creatorName}` : "";
          return `- ${idea.title}${creator}: ${idea.snippet}`;
        })
        .join("\n")}`
    );
  }

  if (results?.webSources?.length) {
    lines.push(
      `Web sources:\n${results.webSources
        .slice(0, 5)
        .map((source) => `- ${source.title}: ${source.url}`)
        .join("\n")}`
    );
  }

  return lines.join("\n\n").trim();
};

const SearchIcon: React.FC<{ className?: string }> = ({ className = "" }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
    <circle cx="11" cy="11" r="7" />
    <path strokeLinecap="round" d="m20 20-3.5-3.5" />
  </svg>
);

const PlusIcon: React.FC<{ className?: string }> = ({ className = "" }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
    <path strokeLinecap="round" d="M12 5v14M5 12h14" />
  </svg>
);

const ArrowTurnIcon: React.FC<{ className?: string }> = ({ className = "" }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" d="M8 8h7a4 4 0 0 1 0 8H9" />
    <path strokeLinecap="round" strokeLinejoin="round" d="m8 8 3-3M8 8l3 3" />
  </svg>
);

const UniversalSearch: React.FC = () => {
  const client = useApolloClient();
  const navigate = useNavigate();
  const location = useLocation();
  const { setMessage } = useMessage();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const requestIdRef = useRef(0);
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [activeIndex, setActiveIndex] = useState(0);
  const [searchState, setSearchState] = useState<SearchState>({
    results: null,
    loading: false,
    webLoading: false,
    error: null,
  });

  const { data: ideasData } = useSafeQuery<IdeasResponse>(GET_IDEAS, {
    skip: !isOpen,
    fetchPolicy: "cache-first",
  });

  const [createIdea, { loading: isCreating }] = useMutation(CREATE_IDEA, {
    refetchQueries: [{ query: GET_IDEAS }],
  });

  const closePalette = () => {
    setIsOpen(false);
    setQuery("");
    setActiveIndex(0);
    setSearchState({
      results: null,
      loading: false,
      webLoading: false,
      error: null,
    });
  };

  const handleOpenIdea = (ideaId: string) => {
    const sidebarState = sidebarVar();
    sidebarVar({ ...sidebarState, currentIdeaId: ideaId });
    closePalette();
    safeNavigate(navigate, setMessage, `/ideas/${ideaId}/description`);
  };

  const handleOpenConversation = (conversationId: string) => {
    closePalette();
    safeNavigate(navigate, setMessage, `/messages/${encodeURIComponent(conversationId)}`);
  };

  const handleCreateIdea = async (title: string, description?: string) => {
    try {
      const { data } = await createIdea({
        variables: {
          title: buildIdeaTitle(title),
          description,
        },
      });

      const newIdeaId = data?.createIdea?.ideaId;
      if (!newIdeaId) {
        throw new Error("Idea creation did not return an idea ID.");
      }

      const sidebarState = sidebarVar();
      sidebarVar({
        ...sidebarState,
        currentIdeaId: newIdeaId,
        allIdeaIds: [newIdeaId, ...sidebarState.allIdeaIds.filter((ideaId) => ideaId !== newIdeaId)],
      });

      closePalette();
      safeNavigate(navigate, setMessage, `/ideas/${newIdeaId}/description`);
    } catch (error) {
      console.error("Failed to create idea from search:", error);
      setMessage("Failed to start an idea from search. Please try again.", "error");
    }
  };

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    });

    return () => window.cancelAnimationFrame(frame);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  useEffect(() => {
    closePalette();
  }, [location.pathname]);

  useEffect(() => {
    const handleGlobalKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setIsOpen(true);
        return;
      }

      if (event.key === "Escape" && isOpen) {
        event.preventDefault();
        closePalette();
        return;
      }

      if (!isOpen && !event.metaKey && !event.ctrlKey && !event.altKey && event.key === "/" && !isEditableTarget(event.target)) {
        event.preventDefault();
        setIsOpen(true);
      }
    };

    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const trimmedQuery = deferredQuery.trim();
    setActiveIndex(0);

    if (!trimmedQuery) {
      setSearchState({
        results: null,
        loading: false,
        webLoading: false,
        error: null,
      });
      return;
    }

    const currentRequestId = requestIdRef.current + 1;
    requestIdRef.current = currentRequestId;

    setSearchState({
      results: null,
      loading: true,
      webLoading: false,
      error: null,
    });

    const fastTimer = window.setTimeout(async () => {
      try {
        const { data } = await client.query<UniversalSearchResponse>({
          query: UNIVERSAL_SEARCH,
          variables: { query: trimmedQuery, limit: RESULT_LIMIT, includeWeb: false },
          fetchPolicy: "no-cache",
        });

        if (requestIdRef.current !== currentRequestId) {
          return;
        }
        if (!data) {
          throw new Error("Universal search returned no data.");
        }

        setSearchState((previous) => ({
          ...previous,
          results: data.universalSearch,
          loading: false,
          error: null,
        }));
      } catch (error) {
        if (requestIdRef.current !== currentRequestId) {
          return;
        }

        console.error("Fast universal search failed:", error);
        setSearchState({
          results: null,
          loading: false,
          webLoading: false,
          error: "Search results could not be loaded.",
        });
      }
    }, 120);

    const webTimer = window.setTimeout(async () => {
      if (requestIdRef.current !== currentRequestId) {
        return;
      }

      setSearchState((previous) => ({
        ...previous,
        webLoading: true,
      }));

      try {
        const { data } = await client.query<UniversalSearchResponse>({
          query: UNIVERSAL_SEARCH,
          variables: { query: trimmedQuery, limit: RESULT_LIMIT, includeWeb: true },
          fetchPolicy: "no-cache",
        });

        if (requestIdRef.current !== currentRequestId) {
          return;
        }
        if (!data) {
          throw new Error("Universal search returned no data.");
        }

        setSearchState({
          results: data.universalSearch,
          loading: false,
          webLoading: false,
          error: null,
        });
      } catch (error) {
        if (requestIdRef.current !== currentRequestId) {
          return;
        }

        console.error("Web universal search failed:", error);
        setSearchState((previous) => ({
          ...previous,
          webLoading: false,
        }));
      }
    }, 520);

    return () => {
      window.clearTimeout(fastTimer);
      window.clearTimeout(webTimer);
    };
  }, [client, deferredQuery, isOpen]);

  const recentIdeas = useMemo(() => (ideasData?.ideas || []).slice(0, 4), [ideasData?.ideas]);
  const trimmedQuery = query.trim();
  const searchResults = searchState.results;

  const paletteItems = useMemo<PaletteItem[]>(() => {
    if (!trimmedQuery) {
      const quickStart: PaletteItem[] = [
        {
          id: "new-blank-idea",
          section: "New",
          kind: "action",
          title: "New blank idea",
          subtitle: "Start a blank idea.",
          actionLabel: "Create",
          onSelect: () => handleCreateIdea("Brand New Idea"),
        },
      ];

      const recentItems = recentIdeas.map((idea) => ({
        id: `recent-${idea.ideaId}`,
        section: "Recent",
        kind: "idea" as const,
        title: idea.title || "Untitled Idea",
        subtitle: stripMarkup(idea.description) || "Open this idea.",
        actionLabel: "Open",
        onSelect: () => handleOpenIdea(idea.ideaId),
      }));

      return [...quickStart, ...recentItems];
    }

    const synthesis =
      searchResults?.assistantSummary?.trim() ||
      searchResults?.webSummary?.trim() ||
      "";

    const items: PaletteItem[] = [
      {
        id: "start-from-query",
        section: "New",
        kind: synthesis ? "web" : "action",
        title: "New idea",
        subtitle: synthesis || `From “${trimmedQuery}”.`,
        sources: searchResults?.webSources,
        actionLabel: "Create",
        onSelect: () =>
          handleCreateIdea(
            trimmedQuery,
            buildSeedDescription(trimmedQuery, searchResults)
          ),
      },
    ];

    searchResults?.myIdeas.forEach((idea) => {
      items.push({
        id: `my-idea-${idea.ideaId}`,
        section: "Ideas",
        kind: "idea",
        title: idea.title,
        subtitle: idea.snippet,
        meta: idea.matchedIn || "Idea",
        actionLabel: "Open",
        onSelect: () => handleOpenIdea(idea.ideaId),
      });
    });

    searchResults?.messages?.forEach((conversation) => {
      items.push({
        id: `message-${conversation.conversationId}`,
        section: "Messages",
        kind: "message",
        title: conversation.title,
        subtitle: stripMarkup(conversation.preview) || (conversation.ideaTitle ? `Re: ${conversation.ideaTitle}` : "Open this conversation."),
        meta: conversation.kind === "email" ? "Email" : "Chat",
        actionLabel: "Open",
        onSelect: () => handleOpenConversation(conversation.conversationId),
      });
    });

    searchResults?.publishedIdeas.forEach((idea) => {
      items.push({
        id: `published-idea-${idea.ideaId}`,
        section: "Published",
        kind: "published",
        title: idea.title,
        subtitle: idea.snippet,
        meta: idea.matchedIn || "Published",
        creatorName: idea.creatorName,
        actionLabel: "Start",
        onSelect: () =>
          handleCreateIdea(
            trimmedQuery || idea.title,
            buildSeedDescription(trimmedQuery || idea.title, searchResults, idea)
          ),
      });
    });

    return items;
  }, [recentIdeas, searchResults, trimmedQuery]);

  useEffect(() => {
    if (activeIndex < paletteItems.length) {
      return;
    }
    setActiveIndex(0);
  }, [activeIndex, paletteItems.length]);

  useEffect(() => {
    return subscribeToVoiceSearchCommand(({ query: nextQuery }) => {
      setIsOpen(true);
      setQuery(nextQuery || "");
      setActiveIndex(0);

      window.setTimeout(() => {
        inputRef.current?.focus();
      }, 30);
    });
  }, []);

  const handlePaletteKeyDown = async (event: React.KeyboardEvent<HTMLDivElement | HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) => (paletteItems.length ? (current + 1) % paletteItems.length : 0));
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => (paletteItems.length ? (current - 1 + paletteItems.length) % paletteItems.length : 0));
      return;
    }

    if (event.key === "Enter") {
      const item = paletteItems[activeIndex];
      if (!item) {
        return;
      }

      event.preventDefault();
      await item.onSelect();
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      closePalette();
    }
  };

  const renderEmptyState = () => {
    if (trimmedQuery && searchState.loading) {
      return (
        <div className="px-4 py-10 text-center text-sm text-gray500 dark:text-gray400">
          Searching…
        </div>
      );
    }

    if (trimmedQuery && searchState.error && paletteItems.length <= 1) {
      return (
        <div className="px-4 py-10 text-center text-sm font-medium text-red-600 dark:text-red-300">
          {searchState.error}
        </div>
      );
    }

    if (trimmedQuery && paletteItems.length === 1) {
      return (
        <div className="px-4 py-6 text-center text-sm text-gray500 dark:text-gray400">
          No matches yet — create a new idea below.
        </div>
      );
    }

    if (!trimmedQuery && recentIdeas.length === 0) {
      return (
        <div className="px-4 py-6 text-center text-sm text-gray500 dark:text-gray400">
          Create a blank idea or search to explore.
        </div>
      );
    }

    return null;
  };

  let lastSection = "";

  const paletteOverlay =
    isOpen && typeof document !== "undefined"
      ? createPortal(
          <div
            className="manifest-modal-backdrop items-start overflow-y-auto px-3 py-3 sm:px-4 sm:pb-8 sm:pt-16"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) {
                closePalette();
              }
            }}
          >
            <div
              className="manifest-modal manifest-modal-compact flex max-h-[calc(100dvh-1.5rem)] w-full max-w-4xl flex-col overflow-hidden rounded-[32px] border border-stone200/90 bg-white/96 shadow-panel dark:border-white/10 dark:bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.14),_transparent_28%),linear-gradient(180deg,_rgba(15,23,42,0.98),_rgba(3,7,18,0.98))] sm:max-h-[calc(100dvh-5rem)]"
              role="dialog"
              aria-modal="true"
              aria-labelledby="universal-search-title"
              onKeyDown={handlePaletteKeyDown}
            >
              <div className="manifest-modal-header shrink-0 border-b border-stone200/80 px-0 py-0 dark:border-white/10">
                <p id="universal-search-title" className="sr-only">
                  Search workspace
                </p>
                <div className="flex w-full items-center gap-3 bg-white/90 px-4 py-3.5 dark:bg-white/[0.04] sm:gap-3.5 sm:px-5 sm:py-4">
                  <div className="flex h-9 w-9 flex-none items-center justify-center rounded-xl bg-stone100/95 text-neutral900 dark:bg-white/10 dark:text-white">
                    <SearchIcon className="h-[1.05rem] w-[1.05rem] text-gray500 dark:text-gray300" />
                  </div>
                  <label htmlFor="universal-search-input" className="min-w-0 flex-1 cursor-text">
                    <span className="sr-only">Query</span>
                    <input
                      id="universal-search-input"
                      ref={inputRef}
                      type="text"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder="Search ideas, messages, web…"
                      className="w-full min-w-0 border-none bg-transparent text-[1.0625rem] font-medium leading-snug tracking-[-0.01em] text-neutral900 outline-none placeholder:text-gray400/95 dark:text-white dark:placeholder:text-gray500"
                      aria-label="Search everything"
                    />
                  </label>
                  {query ? (
                    <button
                      type="button"
                      onClick={() => setQuery("")}
                      className="flex-none rounded-lg border border-stone200/90 bg-stone50/90 px-2.5 py-1.5 text-xs font-semibold text-gray600 transition-colors hover:border-stone300 hover:bg-white hover:text-neutral900 dark:border-white/12 dark:bg-white/5 dark:text-gray300 dark:hover:border-white/22 dark:hover:bg-white/10 dark:hover:text-white"
                      aria-label="Clear search"
                    >
                      Clear
                    </button>
                  ) : null}
                </div>
              </div>

              <div className="manifest-modal-body min-h-0 flex-1 max-h-none overflow-y-auto px-3 pb-4 pt-3 sm:px-4">
                {renderEmptyState()}

                {paletteItems.length > 0 ? (
                  <div role="listbox" aria-label="Universal search results" className="space-y-1.5">
                    {paletteItems.map((item, index) => {
                      const isActive = index === activeIndex;
                      const showSection = item.section !== lastSection;
                      if (showSection) {
                        lastSection = item.section;
                      }

                      return (
                        <React.Fragment key={item.id}>
                          {showSection ? (
                            <div className="px-2 pb-2 pt-5">
                              <div className="flex items-center gap-3">
                                <span className="text-[0.68rem] font-bold uppercase tracking-[0.16em] text-gray500 dark:text-gray400">
                                  {item.section}
                                </span>
                                <div className="h-px flex-1 bg-stone200/80 dark:bg-white/10" />
                              </div>
                            </div>
                          ) : null}
                          <button
                            type="button"
                            role="option"
                            aria-selected={isActive}
                            onMouseEnter={() => setActiveIndex(index)}
                            onClick={() => {
                              void item.onSelect();
                            }}
                            className={`group w-full rounded-[26px] border px-4 py-4 text-left transition-all ${
                              isActive
                                ? "border-accent-300 bg-[linear-gradient(180deg,rgba(239,246,255,0.96),rgba(247,250,252,0.94))] shadow-soft dark:border-accent-700 dark:bg-[linear-gradient(180deg,rgba(30,41,59,0.96),rgba(15,23,42,0.96))]"
                                : "border-transparent bg-transparent hover:border-stone200 hover:bg-white/70 dark:hover:border-white/10 dark:hover:bg-white/[0.035]"
                            }`}
                          >
                            <div className="flex items-start gap-3">
                              <div
                                className={`mt-0.5 flex h-11 w-11 flex-none items-center justify-center rounded-2xl border ${
                                  item.kind === "action"
                                    ? "border-neutral900 bg-neutral900 text-white dark:border-white/10 dark:bg-white dark:text-neutral900"
                                    : item.kind === "published"
                                      ? "border-stone200 bg-stone50 text-neutral900 dark:border-white/10 dark:bg-white/8 dark:text-white"
                                      : item.kind === "web"
                                        ? "border-accent-100 bg-accent-50 text-accent-700 dark:border-accent-800/60 dark:bg-accent-900/30 dark:text-accent-200"
                                        : "border-stone200 bg-stone50 text-neutral900 dark:border-white/10 dark:bg-white/8 dark:text-white"
                                }`}
                              >
                                {item.kind === "action" ? (
                                  <PlusIcon className="h-4 w-4" />
                                ) : item.kind === "published" ? (
                                  <ArrowTurnIcon className="h-4 w-4" />
                                ) : item.kind === "message" ? (
                                  <ChatIcon className="h-4 w-4" />
                                ) : (
                                  <SearchIcon className="h-4 w-4" />
                                )}
                              </div>

                              <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-start gap-2">
                                  <p className="truncate text-[0.97rem] font-semibold text-neutral900 dark:text-white">
                                    {item.title}
                                  </p>
                                  {item.meta ? (
                                    <span className="rounded-full border border-stone200/80 bg-stone50 px-2.5 py-1 text-[0.68rem] font-bold uppercase tracking-[0.12em] text-gray500 dark:border-white/10 dark:bg-white/5 dark:text-gray400">
                                      {item.meta}
                                    </span>
                                  ) : null}
                                  {item.creatorName ? (
                                    <span className="rounded-full border border-stone200/80 bg-stone50 px-2.5 py-1 text-[0.68rem] font-bold uppercase tracking-[0.12em] text-gray500 dark:border-white/10 dark:bg-white/5 dark:text-gray400">
                                      {item.creatorName}
                                    </span>
                                  ) : null}
                                </div>
                                <p className="mt-2 line-clamp-2 text-sm leading-6 text-gray500 dark:text-gray400">
                                  {item.subtitle}
                                </p>
                                {item.sources?.length ? (
                                  <div className="mt-3 flex flex-wrap gap-2">
                                    {item.sources.slice(0, 4).map((source) => (
                                      <a
                                        key={source.url}
                                        href={source.url}
                                        target="_blank"
                                        rel="noreferrer"
                                        onClick={(event) => event.stopPropagation()}
                                        className="rounded-full border border-stone200 bg-white px-2.5 py-1 text-[0.68rem] font-bold uppercase tracking-[0.12em] text-gray500 hover:border-stone300 hover:text-neutral900 dark:border-white/10 dark:bg-white/5 dark:text-gray400 dark:hover:border-white/20 dark:hover:text-white"
                                      >
                                        {source.hostname || source.title}
                                      </a>
                                    ))}
                                  </div>
                                ) : null}
                              </div>

                              <div className="pt-0.5">
                                <span
                                  className={`rounded-full border px-3 py-1.5 text-[0.68rem] font-bold uppercase tracking-[0.12em] transition-colors ${
                                    isActive
                                      ? "border-accent-200 bg-white/90 text-accent-700 dark:border-accent-700/70 dark:bg-accent-950/40 dark:text-accent-200"
                                      : "border-stone200 bg-white/80 text-gray500 group-hover:border-stone300 group-hover:text-neutral900 dark:border-white/10 dark:bg-white/5 dark:text-gray400 dark:group-hover:border-white/20 dark:group-hover:text-white"
                                  }`}
                                >
                                  {item.actionLabel}
                                </span>
                              </div>
                            </div>
                          </button>
                        </React.Fragment>
                      );
                    })}
                  </div>
                ) : null}

                {trimmedQuery && searchState.webLoading ? (
                  <div className="px-3 pb-2 pt-3 text-center text-xs font-medium text-gray400 dark:text-gray500">
                    Enriching results…
                  </div>
                ) : null}

                {isCreating ? (
                  <div className="px-3 pb-2 pt-3 text-center text-xs font-medium text-gray400 dark:text-gray500">
                    Creating…
                  </div>
                ) : null}
              </div>
            </div>
          </div>,
          document.body
        )
      : null;

  return (
    <div className="flex w-full min-w-0 items-center justify-end gap-2">
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="hidden min-h-10 w-full min-w-0 items-center gap-2 rounded-md border border-transparent bg-stone50 px-3 py-1 text-left transition-colors hover:border-stone200 dark:bg-neutral800 dark:hover:border-neutral700 md:flex"
        aria-label="Search ideas, messages, and the web"
      >
        <div className="flex h-6 w-6 flex-none items-center justify-center">
          <SearchIcon className="h-[0.95rem] w-[0.95rem] text-gray500 dark:text-gray300" />
        </div>
        <span className="min-w-0 flex-1 truncate text-left text-[0.9375rem] font-medium tracking-[-0.01em] text-neutral800 dark:text-white/95">
          Search
        </span>
      </button>

      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-stone200 bg-white/80 shadow-soft transition-all hover:-translate-y-0.5 hover:border-stone300 dark:border-white/10 dark:bg-white/5 dark:hover:border-white/20 md:hidden"
        aria-label="Open universal search"
      >
        <SearchIcon className="h-4 w-4 text-gray500 dark:text-gray300" />
      </button>

      {paletteOverlay}
    </div>
  );
};

export default UniversalSearch;
