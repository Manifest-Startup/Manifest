import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useMutation, useReactiveVar } from "@apollo/client/react";
import type { Reference } from "@apollo/client";
import { CombinedGraphQLErrors } from "@apollo/client/errors";
import { v4 as uuidv4 } from "uuid";

import { useSafeQuery } from "features/common-ui/api/useSafeQuery";
import { trackEvent } from "features/analytics/projectAnalytics";
import Button from "features/common-ui/Button";
import { useMessage } from "features/notifications/context/MessageContext";
import { GET_IDEAS, CREATE_IDEA, DELETE_IDEA } from "features/core/apollo/queries";
import { sidebarVar, userVar } from "features/core/apollo/localState";
import { createLogger, logError } from "features/core/logError";
import { IdeaPublishBadge } from "features/social/components";
import { withRenderLog } from "hoc/withRenderLog";
import { safeNavigate } from "utils/safeNavigate";
import { toSlug } from "utils/toSlug";
import { ChevronRightIcon, PlusIcon, SidebarLeftIcon } from "features/common-ui/icons";

const logger = createLogger("IdeasList");

interface IdeaType {
  ideaId: string;
  title: string;
  createdAt?: string;
  isPublished?: boolean;
}

type IdeasSort = "newest" | "oldest" | "alpha";

const IDEAS_SORT_STORAGE_KEY = "manifest.ideasSort";

const ideaAspects: string[] = [
  "Business Model Canvas",
  "Cost Structure",
  "Pitch Deck",
  "Product Requirements Document",
  "Patent",
];

// Short sidebar labels; the full title still drives the route slug and tooltip.
const aspectLabels: Record<string, string> = {
  "Product Requirements Document": "Requirements (PRD)",
};

const INITIAL_IDEAS_TO_RENDER = 80;
const IDEAS_RENDER_BATCH = 80;

const readStoredIdeasSort = (): IdeasSort => {
  try {
    const stored = localStorage.getItem(IDEAS_SORT_STORAGE_KEY);
    if (stored === "newest" || stored === "oldest" || stored === "alpha") {
      return stored;
    }
  } catch {
    // ignore storage failures in private browsing or restricted contexts
  }
  return "newest";
};

const getIdeaDisplayTitle = (idea?: IdeaType) => {
  const trimmedTitle = idea?.title?.trim();
  return trimmedTitle ? trimmedTitle : "Brand New Idea";
};

const sortIdeaIds = (
  ideaIds: string[],
  ideasById: Map<string, IdeaType>,
  sort: IdeasSort
): string[] => {
  const ids = [...ideaIds];
  if (sort === "alpha") {
    return ids.sort((a, b) =>
      getIdeaDisplayTitle(ideasById.get(a)).localeCompare(
        getIdeaDisplayTitle(ideasById.get(b)),
        undefined,
        { sensitivity: "base" }
      )
    );
  }

  return ids.sort((a, b) => {
    const aTime = new Date(ideasById.get(a)?.createdAt ?? 0).getTime();
    const bTime = new Date(ideasById.get(b)?.createdAt ?? 0).getTime();
    return sort === "newest" ? bTime - aTime : aTime - bTime;
  });
};

interface IdeasListProps {
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

const IdeasList: React.FC<IdeasListProps> = ({ collapsed = false, onToggleCollapse }) => {
  logger.log("rendered");

  const { currentIdeaId, allIdeaIds } = useReactiveVar(sidebarVar);
  const { isLoggedIn } = useReactiveVar(userVar);
  const { setMessage } = useMessage();
  const navigate = useNavigate();
  const location = useLocation();
  const [expandedIdeaId, setExpandedIdeaId] = useState<string | null>(null);
  const [hasAutoCreated, setHasAutoCreated] = useState(false);
  const [autoCreateError, setAutoCreateError] = useState(false);
  const [visibleCount, setVisibleCount] = useState(INITIAL_IDEAS_TO_RENDER);
  const [ideasSort, setIdeasSort] = useState<IdeasSort>(() => readStoredIdeasSort());
  const ideaItemRefs = useRef<Record<string, HTMLElement | null>>({});
  const aspectItemRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const aspectMatch = location.pathname.match(/\/ideas\/[^/]+\/([^/]+)/);
  const selectedAspect = aspectMatch ? aspectMatch[1] : "description";

  const { data: ideasData, loading, error } = useSafeQuery(GET_IDEAS, {
    skip: !isLoggedIn,
    fetchPolicy: "cache-first",
    nextFetchPolicy: "cache-first",
  });
  const ideas = ideasData?.ideas;
  const ideasById = useMemo(
    () => new Map<string, IdeaType>((ideas || []).map((idea: IdeaType) => [idea.ideaId, idea])),
    [ideas]
  );

  const sortedIdeaIds = useMemo(
    () => sortIdeaIds(allIdeaIds, ideasById, ideasSort),
    [allIdeaIds, ideasById, ideasSort]
  );

  const renderedIdeaIds = useMemo(() => {
    const initialIds = sortedIdeaIds.slice(0, visibleCount);
    if (!currentIdeaId || initialIds.includes(currentIdeaId)) {
      return initialIds;
    }

    return [...initialIds, currentIdeaId];
  }, [sortedIdeaIds, currentIdeaId, visibleCount]);

  const [createIdea] = useMutation(CREATE_IDEA, {
    refetchQueries: [{ query: GET_IDEAS }],
  });
  // Task #48: drop refetchQueries here. Apollo v4 mutate() resolves to
  // { data, error? } (no plural `errors` field) and a refetch race could
  // re-introduce the deleted idea before the cache evict landed. Each
  // delete call passes an `update` callback that evicts the entity and
  // filters it out of the cached `ideas` list — synchronous and safe.
  const [deleteIdea] = useMutation(DELETE_IDEA);

  useEffect(() => {
    if (!ideas) {
      return;
    }

    const ideaIds = ideas.map((idea: IdeaType) => idea.ideaId);
    sidebarVar({ ...sidebarVar(), allIdeaIds: ideaIds });
    logger.log("Synced idea IDs to sidebarVar:", ideaIds);
  }, [ideas]);

  useEffect(() => {
    if (!ideas || hasAutoCreated || !isLoggedIn) {
      return;
    }

    if (ideas.length === 0) {
      setHasAutoCreated(true);
      setAutoCreateError(false);

      createIdea({ variables: { title: "Brand New Idea" } })
        .then(({ data }) => {
          const createdIdeaId = data?.createIdea?.ideaId || uuidv4();
          sidebarVar({ ...sidebarVar(), allIdeaIds: [createdIdeaId], currentIdeaId: createdIdeaId });
          trackEvent("idea_created", { creation_surface: "empty_state_auto_create" });
          navigate(`/ideas/${createdIdeaId}/description`);
          setExpandedIdeaId(createdIdeaId);
        })
        .catch((err) => {
          setAutoCreateError(true);
          setMessage("Failed to auto-create idea. Please try again.", "error");
          logError("[IdeasList] Error auto-creating idea", err);
        });
    }
  }, [ideas, createIdea, hasAutoCreated, isLoggedIn, navigate, setMessage]);

  useEffect(() => {
    if (!error) {
      return;
    }

    logError("[IdeasList] Failed to load ideas", error);
    setMessage("Failed to load ideas. Please try again.", "error");
  }, [error, setMessage]);

  useEffect(() => {
    if (currentIdeaId) {
      setExpandedIdeaId(currentIdeaId);
    }
  }, [currentIdeaId]);

  useEffect(() => {
    if (!currentIdeaId) {
      return;
    }

    const selectedIdeaIndex = sortedIdeaIds.indexOf(currentIdeaId);
    if (selectedIdeaIndex === -1 || selectedIdeaIndex < visibleCount) {
      return;
    }

    setVisibleCount(Math.min(sortedIdeaIds.length, selectedIdeaIndex + IDEAS_RENDER_BATCH));
  }, [sortedIdeaIds, currentIdeaId, visibleCount]);

  const loadMoreIdeas = () => {
    setVisibleCount((current) => Math.min(current + IDEAS_RENDER_BATCH, sortedIdeaIds.length));
  };

  const handleIdeasSortChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const nextSort = event.target.value as IdeasSort;
    setIdeasSort(nextSort);
    try {
      localStorage.setItem(IDEAS_SORT_STORAGE_KEY, nextSort);
    } catch {
      // ignore storage failures in private browsing or restricted contexts
    }
  };

  const handleIdeasScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const target = event.currentTarget;
    if (visibleCount >= sortedIdeaIds.length) {
      return;
    }

    const remainingScroll = target.scrollHeight - target.scrollTop - target.clientHeight;
    if (remainingScroll < 320) {
      loadMoreIdeas();
    }
  };

  const handleNewIdeaClick = async () => {
    try {
      setAutoCreateError(false);
      const { data } = await createIdea({ variables: { title: "Brand New Idea" } });
      if (data?.createIdea) {
        const newIdeaId = data.createIdea.ideaId;
        trackEvent("idea_created", { creation_surface: "new_button" });
        navigate(`/ideas/${newIdeaId}/description`);
        setExpandedIdeaId(newIdeaId);
      }
    } catch (creationError) {
      setMessage("Failed to create new idea. Please try again.", "error");
      logger.error("Error saving new idea:", creationError);
    }
  };

  const handleIdeaSelect = (ideaId: string) => {
    trackEvent("idea_opened", { entry_point: "sidebar" });
    safeNavigate(navigate, setMessage, `/ideas/${ideaId}/description`);
    sidebarVar({ ...sidebarVar(), currentIdeaId: ideaId });
    setExpandedIdeaId(ideaId);
  };

  const handleAspectClick = (title: string, ideaId: string) => {
    const aspectURL = toSlug(title);
    trackEvent("idea_opened", { entry_point: "aspect" });
    safeNavigate(navigate, setMessage, `/ideas/${ideaId}/${aspectURL}`);
  };

  const handleDeleteIdea = async (ideaId: string, event: React.MouseEvent) => {
    event.stopPropagation();
    event.preventDefault();

    const originalSidebar = sidebarVar();
    const originalIdeaIds = [...originalSidebar.allIdeaIds];

    try {
      const updatedIdeaIds = originalIdeaIds.filter((id) => id !== ideaId);
      const updatedSidebar = { ...originalSidebar, allIdeaIds: updatedIdeaIds };

      if (currentIdeaId === ideaId) {
        updatedSidebar.currentIdeaId = null;
        navigate("/ideas");
      }

      sidebarVar(updatedSidebar);

      if (expandedIdeaId === ideaId) {
        setExpandedIdeaId(null);
      }

      // Apollo v4: mutate() resolves to { data, error? } (singular) and
      // throws on GraphQL/network errors by default. The plural `errors`
      // field that existed in v3 was removed — destructuring it would
      // always be undefined and silently mask backend failures.
      const result = await deleteIdea({
        variables: { ideaId },
        update: (cache, { data: mutationData }) => {
          // Only mutate the cache when the server confirmed the delete.
          if (!mutationData?.deleteIdea) {
            return;
          }
          // Filter the deleted idea out of any cached `ideas` query result.
          // The cached value is an array of normalized Apollo Refs (the
          // `ideas` query returns Idea entities, which are normalized via
          // their `keyFields`), so `Reference[]` is the correct type.
          cache.modify({
            fields: {
              ideas(
                existing: readonly Reference[] = [],
                { readField }
              ): readonly Reference[] {
                return existing.filter(
                  (ideaRef) => readField("ideaId", ideaRef) !== ideaId
                );
              },
            },
          });
          // Evict the cached entity itself so any single-idea reads miss
          // and re-fetch instead of returning the stale row.
          const ideaCacheId = cache.identify({ __typename: "Idea", ideaId });
          if (ideaCacheId) {
            cache.evict({ id: ideaCacheId });
          }
          const summaryCacheId = cache.identify({
            __typename: "IdeaSummary",
            ideaId,
          });
          if (summaryCacheId) {
            cache.evict({ id: summaryCacheId });
          }
          cache.gc();
        },
      });

      // Apollo v4 MutateResult exposes a singular `error` field. With the
      // default errorPolicy ("none") Apollo throws on GraphQL errors so
      // this is rarely populated, but if a non-default policy is ever
      // configured (e.g. "all" or "ignore") errors arrive here on the
      // resolved result instead of being thrown. Throwing it forwards
      // unifies the failure path with the catch block below so the
      // server message still reaches the toast.
      const resultError = (result as { error?: unknown })?.error;
      if (resultError) {
        throw resultError;
      }

      if (!result?.data?.deleteIdea) {
        // Server reached but returned a falsy payload (no row deleted) —
        // surface a clear error and roll back the optimistic UI change.
        sidebarVar({ ...originalSidebar, allIdeaIds: originalIdeaIds });
        setMessage("Failed to delete idea. Please try again.", "error");
        return;
      }

      setMessage("Idea deleted successfully", "info");
    } catch (deleteError) {
      sidebarVar({ ...originalSidebar, allIdeaIds: originalIdeaIds });
      // Surface the underlying GraphQL message when present so users
      // can distinguish "not found" from "permission denied" from
      // generic failures, instead of always seeing the same toast.
      //
      // Apollo Client v4 wraps server-side GraphQL errors in a
      // `CombinedGraphQLErrors` instance whose individual errors live
      // on `.errors` (NOT the legacy v3 `.graphQLErrors`). We check
      // both shapes — `CombinedGraphQLErrors.is(...)` first for the
      // canonical v4 path, then a defensive `.errors[0].message`
      // duck-type, then the legacy `.graphQLErrors[0].message` — so
      // resolver-classified messages ("related records prevent…",
      // "not found or you do not have permission…") always reach the
      // toast instead of being swallowed by the generic fallback.
      // For network/Apollo errors we keep the generic toast so we don't
      // dump cryptic "Failed to fetch" / "Network error" strings on users.
      const apolloErr = deleteError as {
        errors?: ReadonlyArray<{ message?: string }>;
        graphQLErrors?: ReadonlyArray<{ message?: string }>;
      };
      let graphQLMessage: string | undefined;
      if (CombinedGraphQLErrors.is(deleteError)) {
        graphQLMessage = deleteError.errors?.[0]?.message;
      } else if (apolloErr?.errors?.[0]?.message) {
        graphQLMessage = apolloErr.errors[0].message;
      } else if (apolloErr?.graphQLErrors?.[0]?.message) {
        graphQLMessage = apolloErr.graphQLErrors[0].message;
      }
      const friendlyMessage =
        graphQLMessage || "Failed to delete idea. Please try again.";
      setMessage(friendlyMessage, "error");
      logError("[IdeasList] Error deleting idea", deleteError, { ideaId });
    }
  };

  const focusIdeaItem = (ideaId: string) => {
    const node = ideaItemRefs.current[ideaId];
    if (node) {
      node.focus();
    }
  };

  const focusAspectButton = (ideaId: string, aspectIndex: number) => {
    const aspect = ideaAspects[aspectIndex];
    if (!aspect) {
      return;
    }

    const key = `${ideaId}:${aspect}`;
    aspectItemRefs.current[key]?.focus();
  };

  const moveIdeaFocus = (ideaId: string, direction: -1 | 1) => {
    const currentIndex = sortedIdeaIds.indexOf(ideaId);
    if (currentIndex === -1) {
      return;
    }

    const nextIdeaId = sortedIdeaIds[currentIndex + direction];
    if (nextIdeaId) {
      focusIdeaItem(nextIdeaId);
    }
  };

  const handleIdeaKeyDown = (event: React.KeyboardEvent<HTMLElement>, ideaId: string) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveIdeaFocus(ideaId, 1);
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      moveIdeaFocus(ideaId, -1);
      return;
    }

    if (event.key === "ArrowRight") {
      event.preventDefault();
      if (collapsed) {
        onToggleCollapse?.();
        return;
      }

      setExpandedIdeaId(ideaId);
      if (currentIdeaId !== ideaId) {
        handleIdeaSelect(ideaId);
        return;
      }

      window.setTimeout(() => focusAspectButton(ideaId, 0), 30);
      return;
    }

    if (event.key === "ArrowLeft" && !collapsed) {
      event.preventDefault();
      if (expandedIdeaId === ideaId) {
        setExpandedIdeaId(null);
      } else {
        onToggleCollapse?.();
      }
      return;
    }

    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handleIdeaSelect(ideaId);
    }
  };

  const handleAspectKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, ideaId: string, title: string) => {
    const currentIndex = ideaAspects.indexOf(title);

    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusAspectButton(ideaId, Math.min(currentIndex + 1, ideaAspects.length - 1));
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (currentIndex === 0) {
        focusIdeaItem(ideaId);
        return;
      }

      focusAspectButton(ideaId, currentIndex - 1);
      return;
    }

    if (event.key === "ArrowLeft" || event.key === "Escape") {
      event.preventDefault();
      focusIdeaItem(ideaId);
      return;
    }

    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handleAspectClick(title, ideaId);
    }
  };

  if (collapsed) {
    return (
      <aside className="manifest-panel manifest-library flex h-full flex-col overflow-hidden">
        <div className="border-b border-stone200/80 px-3 py-4 dark:border-neutral700">
          <div className="flex flex-col items-center gap-2">
            <Button
              aria-expanded={false}
              aria-label="Expand ideas"
              className="h-12 w-12 rounded-[1.35rem] p-0"
              onClick={onToggleCollapse}
              title="Expand ideas"
              type="button"
              variant="secondary"
            >
              <ChevronRightIcon className="h-6 w-6" />
            </Button>
            <Button
              aria-label="Create new idea"
              className="h-12 w-12 rounded-[1.35rem] p-0"
              data-testid="new-idea-button"
              onClick={handleNewIdeaClick}
              title="Create new idea"
              type="button"
              variant="primary"
            >
              <svg
                aria-hidden="true"
                className="text-current"
                fill="none"
                stroke="currentColor"
                style={{ flexShrink: 0, height: "1.5rem", minHeight: "1.5rem", minWidth: "1.5rem", width: "1.5rem" }}
                viewBox="0 0 24 24"
              >
                <path d="M12 5v14M5 12h14" strokeLinecap="round" strokeWidth="2" />
              </svg>
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-3">
          <div className="flex flex-col gap-2">
            {renderedIdeaIds.map((ideaId: string, index) => {
              const ideaObj = ideasById.get(ideaId);
              const displayIndex = sortedIdeaIds.indexOf(ideaId);
              const displayTitle = getIdeaDisplayTitle(ideaObj);
              const isSelected = currentIdeaId === ideaId;

              return (
                <button
                  key={ideaId}
                  ref={(node) => {
                    ideaItemRefs.current[ideaId] = node;
                  }}
                  aria-current={isSelected}
                  aria-label={`Open idea ${displayIndex + 1}: ${displayTitle}`}
                  className={`flex h-12 items-center justify-center rounded-2xl border text-sm font-bold transition-all ${
                    isSelected
                      ? "border-accent-200 bg-accent-50 text-accent-700 shadow-soft dark:border-accent-800 dark:bg-accent-900/25 dark:text-accent-200"
                      : "border-stone200 bg-white/80 text-gray500 hover:border-stone300 hover:text-neutral900 dark:border-neutral700 dark:bg-neutral900/84 dark:text-gray400 dark:hover:border-neutral600 dark:hover:text-white"
                  }`}
                  onClick={() => handleIdeaSelect(ideaId)}
                  onKeyDown={(event) => handleIdeaKeyDown(event, ideaId)}
                  title={displayTitle}
                  type="button"
                >
                    {(displayIndex + 1).toString().padStart(2, "0")}
                </button>
              );
            })}
          </div>
        </div>
      </aside>
    );
  }

  const ideaCount = allIdeaIds.length;

  return (
    <aside className="manifest-panel manifest-library manifest-sidebar flex h-full flex-col overflow-hidden" data-testid="ideas-list">
      <header className="manifest-sidebar-header">
        <div className="manifest-sidebar-header-row">
          <h2 className="manifest-sidebar-title">Ideas</h2>
          <span className="manifest-sidebar-count" data-testid="ideas-count-label" aria-label={`${ideaCount} idea${ideaCount === 1 ? "" : "s"}`}>
            {loading && !ideas ? "" : ideaCount}
          </span>
          <div className="ml-auto flex items-center">
            <button type="button" className="manifest-sidebar-icon" onClick={handleNewIdeaClick}
              aria-label="New Idea" title="New idea" data-testid="new-idea-button">
              <PlusIcon className="h-[18px] w-[18px]" strokeWidth={1.8} />
            </button>
            {onToggleCollapse && <button type="button" className="manifest-sidebar-icon" onClick={onToggleCollapse}
              aria-expanded aria-label="Collapse ideas" title="Collapse ideas">
              <SidebarLeftIcon className="h-[18px] w-[18px]" strokeWidth={1.6} />
            </button>}
          </div>
        </div>
        {ideaCount > 1 && <label className="manifest-sidebar-sort">
          <span className="sr-only">Sort ideas</span>
          <select aria-label="Sort ideas" data-testid="ideas-sort-select" onChange={handleIdeasSortChange} value={ideasSort}>
            <option value="newest">Newest</option><option value="oldest">Oldest</option><option value="alpha">A–Z</option>
          </select>
          <svg aria-hidden="true" viewBox="0 0 12 12" fill="none" stroke="currentColor"><path d="m3 4.5 3 3 3-3" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </label>}
      </header>

      <div className="manifest-sidebar-scroll flex-1 overflow-y-auto" onScroll={handleIdeasScroll}>
        {loading && !ideas ? (
          <div className="manifest-sidebar-skeleton" data-testid="ideas-loading-state" role="status">
            <span className="sr-only">Loading your ideas...</span>
            <i /><i /><i />
          </div>
        ) : null}

        {error ? (
          <div className="manifest-sidebar-note" data-testid="ideas-error-state">
            <p className="font-medium text-red-600 dark:text-red-300">We couldn't load your ideas.</p>
            <p>Refresh the page or try creating a new idea again.</p>
          </div>
        ) : null}

        {!loading && !error && ideaCount === 0 ? (
          <div className="manifest-sidebar-note" data-testid="ideas-empty-state">
            <p className="font-medium text-[var(--text-primary)]">You haven't created any ideas yet.</p>
            <p>{autoCreateError ? "Automatic setup failed, but you can still start manually." : "Click “New Idea” to start."}</p>
            {autoCreateError ? (
              <Button variant="primary" onClick={handleNewIdeaClick} className="mt-3 justify-center" data-testid="new-idea-button">
                <PlusIcon className="h-4 w-4" />
                New Idea
              </Button>
            ) : null}
          </div>
        ) : null}

        <ul className="manifest-sidebar-list">
          {renderedIdeaIds.map((ideaId: string, index) => {
            const ideaObj = ideasById.get(ideaId);
            const displayTitle = getIdeaDisplayTitle(ideaObj);
            const isSelected = currentIdeaId === ideaId;
            const isExpanded = expandedIdeaId === ideaId;
            const isPublished = ideaObj?.isPublished || false;

            return (
              <li key={ideaId} className="manifest-sidebar-item" style={{ "--i": index } as React.CSSProperties}>
                <div
                  className="manifest-sidebar-row"
                  data-selected={isSelected}
                  onClick={() => handleIdeaSelect(ideaId)}
                  onKeyDown={(event) => handleIdeaKeyDown(event, ideaId)}
                  ref={(node) => {
                    ideaItemRefs.current[ideaId] = node;
                  }}
                  role="button"
                  tabIndex={0}
                  aria-current={isSelected ? "true" : undefined}
                  aria-expanded={isExpanded}
                  aria-label={`Open idea ${displayTitle}`}
                >
                  <svg className="manifest-sidebar-disclosure" data-open={isExpanded} aria-hidden="true" viewBox="0 0 12 12" fill="none" stroke="currentColor">
                    <path d="m4.5 3 3 3-3 3" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  {/* #10: full title on hover disambiguates similar prefixes in a narrow sidebar. */}
                  <span className="manifest-sidebar-label" title={displayTitle}>{displayTitle}</span>
                  <span className="manifest-sidebar-actions" data-published={isPublished}>
                    <IdeaPublishBadge ideaId={ideaId} isPublished={isPublished} size="sm" />
                    <button
                      onClick={(event) => handleDeleteIdea(ideaId, event)}
                      onKeyDown={(event) => event.stopPropagation()}
                      className="manifest-sidebar-icon manifest-sidebar-delete"
                      aria-label={`Delete idea: ${displayTitle}`}
                      title="Delete idea"
                      type="button"
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M4 7h16" />
                        <path d="M18 7v12a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V7" />
                        <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                      </svg>
                    </button>
                  </span>
                </div>

                {isExpanded ? (
                  <ul className="manifest-sidebar-aspects">
                    {ideaAspects.map((title, aspectIndex) => {
                      const isAspectSelected = isSelected && toSlug(title) === selectedAspect;

                      return (
                        <li key={title} style={{ "--i": aspectIndex } as React.CSSProperties}>
                          <button
                            type="button"
                            ref={(node) => {
                              aspectItemRefs.current[`${ideaId}:${title}`] = node;
                            }}
                            className="manifest-sidebar-aspect"
                            data-selected={isAspectSelected}
                            title={title}
                            aria-label={title}
                            aria-current={isAspectSelected ? "page" : undefined}
                            onClick={() => handleAspectClick(title, ideaId)}
                            onKeyDown={(event) => handleAspectKeyDown(event, ideaId, title)}
                          >
                            {aspectLabels[title] ?? title}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
        {visibleCount < sortedIdeaIds.length ? (
          <button type="button" onClick={loadMoreIdeas} className="manifest-sidebar-more">
            Load more ideas
          </button>
        ) : null}
      </div>
    </aside>
  );
};

export default withRenderLog("IdeasList", IdeasList);
