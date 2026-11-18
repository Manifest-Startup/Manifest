import React, { Suspense, lazy, useRef, useEffect, useMemo, useState } from "react";
import debounce from "lodash.debounce";
import throttle from "lodash/throttle";
import { useParams, useSearchParams } from "react-router-dom";
// The rich-text editor (TipTap/ProseMirror, ~100 KB gzipped) is only needed on
// the Note view; generated documents are read-only, so load it on demand and
// warm it in idle time so opening the Note view stays instant.
const loadTextArea = () => import("features/common-ui/TextArea");
const TextArea = lazy(loadTextArea);
// The canvas view carries the integrations catalogue (icons for suggested
// partner tools), so it loads only when that tab opens.
const BusinessModelCanvasDisplay = lazy(() =>
  import("./display/BusinessModelCanvasDisplay").then((module) => ({ default: module.BusinessModelCanvasDisplay }))
);
const warmTextArea = () => {
  const run = () => { void loadTextArea(); };
  if (typeof window !== "undefined" && "requestIdleCallback" in window) {
    window.requestIdleCallback(run, { timeout: 4000 });
  } else {
    setTimeout(run, 1500);
  }
};

// Collaboration components
import { ShareButton, VersionButton } from "features/collaboration";

// Services
import { useMutation, useReactiveVar } from '@apollo/client/react';
import { useSafeQuery } from 'features/common-ui/api/useSafeQuery';
import {
  GET_IDEA_CORE,
  GET_IDEA_DOCUMENTS,
  GET_IDEA_VERSIONS,
  UPDATE_IDEA,
  FIND_SIMILAR_IDEAS,
  GET_IDEA_KNOWLEDGE_GRAPH,
} from 'features/core/apollo/queries';
import {
  sidebarVar,
  editorStatusVar,
  similarIdeasVar,
  createSimilarIdeasEntry,
  getSimilarIdeasEntry,
} from 'features/core/apollo/localState';
import { client } from 'features/core/apollo/client';

// Contexts
import { useMessage } from "features/notifications/context/MessageContext";

// Display components
// Import views directly, not through the './display' barrel: the barrel also
// re-exports the canvas view, which would pull the integrations catalogue
// back into this chunk.
import { MarkdownDisplay } from './display/MarkdownDisplay';
import { ProvisionalPatentDisplay } from './display/ProvisionalPatentDisplay';
import { CostStructureDisplay, extractCostStructure } from './display/CostStructureDisplay';
import type { DocumentGenerationState } from './display/DocumentGenerationNotice';
import { subscribeToIdeaPublished } from '../events/ideaPublishEvents';

// Utils
import { logError, createLogger } from 'features/core/logError';
import { syncIdeaTitleInCache } from '../utils/syncIdeaTitleCache';
import { WikiLinksProvider } from '../knowledge/WikiLinkContext';
import { makeResolver } from '../knowledge/wikiLinks';
import { CitationBanner, KnowledgeGraphView } from '../knowledge/KnowledgeGraphView';

const logger = createLogger('IdeaComponent');
const IDEA_TITLE_FALLBACK = 'Brand New Idea';

// For dynamic aspect access, use a type-safe mapping
const aspectMap: Record<string, keyof IdeaType> = {
  "description": "description",
  "business-model-canvas": "businessModelCanvas",
  "cost-structure": "provisionalPatent", // cost structure is extracted from patent
  "pitch-deck": "pitchDeck",
  "product-requirements-document": "productRequirementsDocument",
  "patent": "provisionalPatent",
  "development": "description", // fallback
};

const aspectLabelMap: Record<string, string> = {
  "description": "Note",
  "business-model-canvas": "Canvas",
  "cost-structure": "Costs",
  "pitch-deck": "Deck",
  "product-requirements-document": "Requirements",
  "patent": "Patent",
  "development": "Note",
  "knowledge-graph": "Knowledge Graph",
};

// Utility functions
const logIdea = (message: string, data?: any, ideaId?: string) => {
  logger.log(`[Idea] ${message}`, data);
};

// Helper function to check if HTML content has meaningful text (matches backend logic)
const hasMeaningfulHtml = (html: string): boolean => {
  if (!html || typeof html !== "string") {
    return false;
  }
  const textOnly = html.replace(/<[^>]+>/g, "");
  const normalized = textOnly.replace(/&nbsp;|&#160;/g, " ").trim();
  const cleaned = normalized.replace(/[\u200B-\u200D\uFEFF]/g, "");
  return cleaned !== "";
};

// Define the IdeaType locally
interface IdeaType {
  ideaId: string;
  title: string;
  description?: string;
  pitchDeck?: string;
  productRequirementsDocument?: string;
  provisionalPatent?: string;
  businessModelCanvas?: string;
  similarIdeas?: string;
  createdAt?: string;
}

type GeneratedDocumentKey =
  | 'business-model-canvas'
  | 'pitch-deck'
  | 'product-requirements-document'
  | 'patent';

interface DocumentGenerationSession {
  baselines: Record<GeneratedDocumentKey, string | null>;
  expiresAt: number;
  startedAt: number;
}

const DOCUMENT_GENERATION_TIMEOUT_MS = 6 * 60 * 1000;
const GENERATED_DOCUMENT_KEYS: GeneratedDocumentKey[] = [
  'business-model-canvas',
  'pitch-deck',
  'product-requirements-document',
  'patent',
];

const documentSignature = (value?: string | null) => {
  if (typeof value !== 'string') {
    return null;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  return trimmed.length > 280 ? trimmed.slice(0, 280) : trimmed;
};

const setActiveSimilarIdeasIdea = (ideaId: string | null) => {
  const previous = similarIdeasVar();

  if (!ideaId) {
    similarIdeasVar({
      ...previous,
      ideaId: null,
      loading: false,
      error: null,
      data: '',
    });
    return;
  }

  const cached = getSimilarIdeasEntry(previous, ideaId);

  similarIdeasVar({
    ...previous,
    ideaId,
    loading: cached?.loading ?? false,
    error: cached?.error ?? null,
    data: cached?.data ?? '',
  });
};

const updateSimilarIdeasEntry = (
  ideaId: string,
  nextEntry: Partial<ReturnType<typeof createSimilarIdeasEntry>>,
) => {
  const previous = similarIdeasVar();
  const currentEntry = getSimilarIdeasEntry(previous, ideaId) || createSimilarIdeasEntry();
  const mergedEntry = createSimilarIdeasEntry({
    ...currentEntry,
    ...nextEntry,
  });

  similarIdeasVar({
    ...previous,
    ideaId,
    loading: mergedEntry.loading,
    error: mergedEntry.error,
    data: mergedEntry.data,
    byIdeaId: {
      ...previous.byIdeaId,
      [ideaId]: mergedEntry,
    },
  });
};

// Idea component integrates TipTap editor for editing and auto-saving idea content with debounce.
interface IdeaProps {
  panelActions?: React.ReactNode;
}

export const Idea: React.FC<IdeaProps> = ({ panelActions }) => {
  logIdea('rendered');
  // -------------------- Context and State Hooks --------------------
  const { currentIdeaId } = useReactiveVar(sidebarVar);
  const status = useReactiveVar(editorStatusVar);
  const { setMessage } = useMessage();
  const { ideaAspect = "description" } = useParams();

  // -------------------- Save Idea Mutation Hook --------------------
  const [patchIdea] = useMutation(UPDATE_IDEA);

  // -------------------- Refs --------------------
  // lastSavedRef holds the last saved content and ideaId
  const lastSavedRef = useRef<{ content: string; ideaId: string | null }>({
    content: "",
    ideaId: null,
  });
  
  // contentRef holds the current editor content
  const contentRef = useRef<string>("");
  const [content, setContent] = useState("");
  const refetchTimeoutsRef = useRef<number[]>([]);
  const currentIdeaIdRef = useRef<string | null>(currentIdeaId);
  const [documentGenerationSessions, setDocumentGenerationSessions] = useState<Record<string, DocumentGenerationSession>>({});
  const currentDocumentSession = currentIdeaId ? documentGenerationSessions[currentIdeaId] : undefined;
  const shouldLoadDocumentPayload = Boolean(
    currentIdeaId &&
      (ideaAspect === 'business-model-canvas' ||
        ideaAspect === 'cost-structure' ||
        ideaAspect === 'pitch-deck' ||
        ideaAspect === 'product-requirements-document' ||
        ideaAspect === 'patent' ||
        currentDocumentSession)
  );

  // Add a flag to track when we're switching ideas
  const isSwitchingRef = useRef(false);

  const clearScheduledRefetches = () => {
    refetchTimeoutsRef.current.forEach((timeoutId) => window.clearTimeout(timeoutId));
    refetchTimeoutsRef.current = [];
  };

  const scheduleDocumentRefetches = () => {
    clearScheduledRefetches();

    // Full document generation can take several minutes depending on model latency.
    [10000, 30000, 60000, 120000].forEach((delay) => {
      const timeoutId = window.setTimeout(() => {
        const activeIdeaId = currentIdeaIdRef.current;
        if (activeIdeaId) {
          logIdea(`Refetch after document generation (${delay / 1000}s)`);
          void client.query({
            query: GET_IDEA_DOCUMENTS,
            variables: { ideaId: activeIdeaId },
            fetchPolicy: "network-only",
          });
        }
      }, delay);

      refetchTimeoutsRef.current.push(timeoutId);
    });
  };

  // Fetch the current idea's data from the backend using the useGetIdeaByIdQuery hook
  const { data: ideaCoreData, loading: isFetching, refetch } = useSafeQuery(GET_IDEA_CORE, {
    variables: { ideaId: currentIdeaId },
    skip: !currentIdeaId, // Skip the query if no currentIdeaId is provided
    fetchPolicy: 'cache-first',
    nextFetchPolicy: 'cache-first',
  });
  const { data: ideaDocumentsData } = useSafeQuery(GET_IDEA_DOCUMENTS, {
    variables: { ideaId: currentIdeaId },
    skip: !shouldLoadDocumentPayload,
    fetchPolicy: 'cache-first',
    nextFetchPolicy: 'cache-first',
  });
  const ideaData = useMemo(
    () =>
      ideaCoreData?.idea
        ? {
            idea: {
              ...ideaCoreData.idea,
              ...(ideaDocumentsData?.idea || {}),
            },
          }
        : ideaCoreData,
    [ideaCoreData, ideaDocumentsData]
  );
  const refetchRef = useRef(refetch);
  const ideaSnapshotRef = useRef<IdeaType | null>(null);

  // -------------------- Knowledge graph (ADR 0006) --------------------
  // Documents cite the idea note with [[wiki-links]]; the graph is built live on the server
  // from the note, interview answers and documents, so refetch it when a document changes.
  const [searchParams] = useSearchParams();
  const needsKnowledgeGraph = Boolean(
    currentIdeaId &&
      (shouldLoadDocumentPayload || ideaAspect === 'knowledge-graph' || searchParams.get('cite'))
  );
  const {
    data: knowledgeData,
    loading: knowledgeLoading,
    refetch: refetchKnowledge,
  } = useSafeQuery(GET_IDEA_KNOWLEDGE_GRAPH, {
    variables: { ideaId: currentIdeaId as string },
    skip: !needsKnowledgeGraph,
    fetchPolicy: 'cache-and-network',
    nextFetchPolicy: 'cache-first',
  });
  const knowledgeGraph =
    knowledgeData?.ideaKnowledgeGraph?.ideaId === currentIdeaId
      ? knowledgeData?.ideaKnowledgeGraph
      : null;
  const wikiLinks = useMemo(
    () => ({ graph: knowledgeGraph, resolve: makeResolver(knowledgeGraph) }),
    [knowledgeGraph]
  );
  const documentsKey = [
    ideaData?.idea?.businessModelCanvas,
    ideaData?.idea?.pitchDeck,
    ideaData?.idea?.productRequirementsDocument,
    ideaData?.idea?.provisionalPatent,
  ]
    .map((doc) => (typeof doc === 'string' ? doc.length : 0))
    .join(':');
  const documentsKeyRef = useRef(documentsKey);
  useEffect(() => {
    if (documentsKeyRef.current === documentsKey) return;
    documentsKeyRef.current = documentsKey;
    if (needsKnowledgeGraph) void refetchKnowledge?.();
  }, [documentsKey, needsKnowledgeGraph, refetchKnowledge]);

  logIdea("Document data:", {
    hasBMC: !!ideaData?.idea?.businessModelCanvas,
    hasPitchDeck: !!ideaData?.idea?.pitchDeck,
    hasPRD: !!ideaData?.idea?.productRequirementsDocument,
    hasPatent: !!ideaData?.idea?.provisionalPatent,
    hasSimilarIdeas: !!ideaData?.idea?.similarIdeas,
  });

  logIdea("currentIdeaId", currentIdeaId);
  logIdea('ideaData', ideaData);

  useEffect(() => {
    warmTextArea();
  }, []);

  useEffect(() => {
    currentIdeaIdRef.current = currentIdeaId;
  }, [currentIdeaId]);

  useEffect(() => {
    setActiveSimilarIdeasIdea(currentIdeaId);
  }, [currentIdeaId]);

  useEffect(() => {
    refetchRef.current = refetch;
  }, [refetch]);

  useEffect(() => {
    ideaSnapshotRef.current = ideaData?.idea || null;
  }, [ideaData]);

  useEffect(() => {
    if (!currentIdeaId || ideaData?.idea?.ideaId !== currentIdeaId) {
      return;
    }

    const backendSimilarIdeas = ideaData?.idea?.similarIdeas || '';

    if (backendSimilarIdeas) {
      const currentEntry = getSimilarIdeasEntry(similarIdeasVar(), currentIdeaId);
      if (
        !currentEntry ||
        currentEntry.data !== backendSimilarIdeas ||
        currentEntry.loading ||
        currentEntry.error
      ) {
        updateSimilarIdeasEntry(currentIdeaId, {
          loading: false,
          error: null,
          data: backendSimilarIdeas,
          updatedAt: Date.now(),
        });
      }
    }
  }, [currentIdeaId, ideaData?.idea?.ideaId, ideaData?.idea?.similarIdeas]);

  const startDocumentGenerationTracking = (ideaId: string) => {
    const snapshot = ideaSnapshotRef.current;

    setDocumentGenerationSessions((previous) => ({
      ...previous,
      [ideaId]: {
        startedAt: Date.now(),
        expiresAt: Date.now() + DOCUMENT_GENERATION_TIMEOUT_MS,
        baselines: {
          'business-model-canvas': documentSignature(snapshot?.businessModelCanvas),
          'pitch-deck': documentSignature(snapshot?.pitchDeck),
          'product-requirements-document': documentSignature(snapshot?.productRequirementsDocument),
          patent: documentSignature(snapshot?.provisionalPatent),
        },
      },
    }));
  };

  const getPendingDocuments = (
    session: DocumentGenerationSession | undefined,
    idea: IdeaType | null | undefined
  ): GeneratedDocumentKey[] => {
    if (!session || Date.now() >= session.expiresAt) {
      return [];
    }

    return GENERATED_DOCUMENT_KEYS.filter((documentKey) => {
      const baseline = session.baselines[documentKey];

      const currentSignature =
        documentKey === 'business-model-canvas'
          ? documentSignature(idea?.businessModelCanvas)
          : documentKey === 'pitch-deck'
            ? documentSignature(idea?.pitchDeck)
            : documentKey === 'product-requirements-document'
              ? documentSignature(idea?.productRequirementsDocument)
              : documentSignature(idea?.provisionalPatent);

      return baseline === currentSignature;
    });
  };

  const pendingGeneratedDocuments = getPendingDocuments(
    currentDocumentSession,
    (ideaData?.idea as IdeaType | undefined) || null
  );

  const getDocumentGenerationState = (documentKey: GeneratedDocumentKey): DocumentGenerationState | null => {
    if (!currentDocumentSession || !pendingGeneratedDocuments.includes(documentKey)) {
      return null;
    }

    return {
      startedAt: currentDocumentSession.startedAt,
      pendingDocuments: pendingGeneratedDocuments,
      mode: currentDocumentSession.baselines[documentKey] ? 'refresh' : 'initial',
    };
  };

  const startDocumentGenerationTrackingRef = useRef(startDocumentGenerationTracking);
  const scheduleDocumentRefetchesRef = useRef(scheduleDocumentRefetches);
  startDocumentGenerationTrackingRef.current = startDocumentGenerationTracking;
  scheduleDocumentRefetchesRef.current = scheduleDocumentRefetches;

  useEffect(() => {
    return subscribeToIdeaPublished((publishedIdeaId) => {
      if (publishedIdeaId === currentIdeaIdRef.current) {
        startDocumentGenerationTrackingRef.current(publishedIdeaId);
        scheduleDocumentRefetchesRef.current();
      }
    });
  }, []);

  // -------------------- Editor Setup --------------------
  // debouncedSave is a debounced function that saves the editor content to the backend
  const debouncedSave = useRef(
    debounce(async (content: string, ideaId: string | null) => {
      logIdea('debouncedSave called', { content, ideaId });
      
      // Don't save if we're in the middle of switching ideas
      if (isSwitchingRef.current) {
        logIdea('Skipping save - switching ideas');
        return;
      }
      
      if (!ideaId) {
        logger.warn("[Idea] Skipping patchIdea — no ideaId provided.");
        setMessage("Cannot save idea: No idea selected.", "info");
        return;
      }

      // Don't save if description has no meaningful content (matches backend validation)
      if (!hasMeaningfulHtml(content)) {
        logIdea('Skipping description save - no meaningful HTML content');
        return;
      }

      editorStatusVar('saving');
      try {
        const response = await patchIdea({
          variables: {
            ideaId,
            description: content,
          }
        });
        logIdea("Patch response from backend:", response);

        void client.query({
          query: GET_IDEA_VERSIONS,
          variables: { ideaId },
          fetchPolicy: "network-only",
        });

        // ✅ Remember the last successfully saved version so we can
        // detect unsaved local edits later and avoid overwriting them
        lastSavedRef.current = { content, ideaId };
        startDocumentGenerationTracking(ideaId);
        scheduleDocumentRefetches();
      } catch (error) {
        logError("Failed to patch idea content", error, { content: contentRef.current, ideaId: currentIdeaId });
        setMessage("Failed to save idea content. Please try again.", "error");
      }
      editorStatusVar('idle');
    }, 1200)
  ).current;

  // Debounced background task updater
  const debouncedBackgroundTasks = useRef(
    debounce(async (content: string) => {
      logIdea('debouncedBackgroundTasks called', { content });
      const activeIdeaId = currentIdeaIdRef.current;
      if (!content || !activeIdeaId) return;
      
      // Extract plain text from HTML for better AI processing
      const plainText = content.replace(/<[^>]*>/g, '').trim();
      if (!plainText || plainText.length < 10) {
        logIdea('Skipping background tasks - content too short');
        return;
      }
      
      logIdea('Refreshing related idea insights', { ideaId: activeIdeaId, contentLength: plainText.length });

      try {
        // The backend already starts document generation from updateIdea.
        // Keep the client-side related ideas fetch here for responsiveness.
        try {
          updateSimilarIdeasEntry(activeIdeaId, {
            loading: true,
            error: null,
          });
          const { data } = await client.query({ query: FIND_SIMILAR_IDEAS, variables: { ideaDescription: plainText } });
          if (!data) {
            throw new Error('Similar ideas query returned no data.');
          }
          updateSimilarIdeasEntry(activeIdeaId, {
            loading: false,
            error: null,
            data: data.findSimilarIdeas.similarIdeas,
            updatedAt: Date.now(),
          });
        } catch (error: any) {
          logError('Failed to fetch similar ideas', error);
          updateSimilarIdeasEntry(activeIdeaId, {
            loading: false,
            error: error.message,
          });
        }
      } catch (error: any) {
        logError('Failed to update related ideas', error);
      }
    }, 2000) // Increased debounce to 2 seconds to avoid too many calls
  ).current;

  // Log similar ideas from Redux
  const { data: similarIdeas } = useReactiveVar(similarIdeasVar);
  logIdea('similarIdeas from Redux', { similarIdeas });

  // Reset the global editor status when the user navigates between ideas or
  // aspects so a stale "typing"/"saving" doesn't survive across the context
  // (regression #16). The Note view starts at `idle` — that's the truthful
  // baseline for a freshly mounted aspect.
  useEffect(() => {
    editorStatusVar('idle');
  }, [currentIdeaId, ideaAspect]);

  useEffect(() => {
    if (!currentIdeaId || !currentDocumentSession) {
      return;
    }

    if (pendingGeneratedDocuments.length > 0) {
      return;
    }

    setDocumentGenerationSessions((previous) => {
      if (!previous[currentIdeaId]) {
        return previous;
      }

      const nextSessions = { ...previous };
      delete nextSessions[currentIdeaId];
      return nextSessions;
    });
  }, [currentDocumentSession, currentIdeaId, pendingGeneratedDocuments.length]);

  // Add local state for the title
  const [title, setTitle] = useState("");
  const titleInputRef = useRef<HTMLInputElement>(null);
  // Track whether the user is actively editing the title so we don't overwrite
  // the input value from a background update or need to imperatively blur.
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  // Track the title that we're currently saving to prevent overwriting it
  const pendingTitleSaveRef = useRef<string | null>(null);
  const isSavingTitleRef = useRef(false);
  // Distinguish "data not loaded yet" from "data loaded but title is empty".
  // While the query is still pending we leave the local title state empty so
  // the input shows its placeholder ("Untitled Idea") instead of flashing the
  // "Brand New Idea" fallback over an existing idea (regression #14).
  const ideaRowLoaded = Boolean(ideaData?.idea);
  const backendTitle: string | null = ideaRowLoaded
    ? (ideaData?.idea?.title?.trim() ? ideaData!.idea!.title! : IDEA_TITLE_FALLBACK)
    : null;

  // Sync local title state with backend value only when idea ID changes or backend title changes,
  // but do NOT overwrite if the user is actively editing (input is focused) or if we're saving a title
  useEffect(() => {
    logIdea('useEffect: sync local title state', {
      currentIdeaId,
      backendTitle,
      isEditingTitle,
      isSavingTitle: isSavingTitleRef.current,
      pendingTitleSave: pendingTitleSaveRef.current,
      currentTitle: title
    });

    // Don't sync until the backend row is actually loaded (regression #14).
    if (backendTitle === null) {
      return;
    }

    // Don't overwrite if user is editing or if we have a save in progress
    if (isEditingTitle || isSavingTitleRef.current) {
      logIdea('Skipping title sync - user editing or save in progress');
      return;
    }

    // Don't overwrite if the current title matches what we're trying to save
    if (pendingTitleSaveRef.current !== null && title === pendingTitleSaveRef.current) {
      logIdea('Skipping title sync - title matches pending save');
      return;
    }

    // Only update the local title if it differs from the backend
    if (title !== backendTitle) {
      logIdea('Updating title from backend', { from: title, to: backendTitle });
      setTitle(backendTitle);
      // Clear pending save ref since we've synced with backend
      pendingTitleSaveRef.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIdeaId, ideaData?.idea?.title, isEditingTitle]);

  // 📌 Imperative blur no longer required – handled via isEditingTitle flag.

  // -------------------- Throttled Title Save Logic --------------------
  const throttledTitleSave = useRef(
    throttle(async (title: string, ideaId: string | null) => {
      logIdea('throttledTitleSave called', { title, ideaId });
      if (!ideaId || typeof ideaId !== "string") {
        logger.warn("[Idea] Invalid ideaId for title patchIdea:", ideaId);
        setMessage("Cannot save title: Invalid idea ID.", "error");
        return;
      }

      // Don't save if title is empty or just whitespace
      if (!title || typeof title !== "string" || title.trim() === "") {
        logIdea('Skipping title save - title is empty or whitespace');
        return;
      }

      // Persist the trimmed value so we don't store leading/trailing whitespace
      // (regression #28). Surrounding spaces in DB cause aria-label / sidebar
      // diff churn and look like sloppy data to investors.
      const normalizedTitle = title.trim();

      // Track that we're saving this title
      isSavingTitleRef.current = true;
      pendingTitleSaveRef.current = normalizedTitle;

      logIdea("Triggering throttled title patchIdea:", { title: normalizedTitle, ideaId });
      editorStatusVar('saving');

      try {
        const response = await patchIdea({
          variables: {
            ideaId: ideaId,
            title: normalizedTitle,
          }
        });

        logIdea("Title patchIdea response:", response);
        syncIdeaTitleInCache(
          client.cache,
          ideaId,
          response?.data?.updateIdea?.title || normalizedTitle
        );
        // Clear the pending save ref after successful save
        pendingTitleSaveRef.current = null;
      } catch (error) {
        logError("Failed to patch idea title", error);
        setMessage("Failed to save idea title. Please try again.", "error");
        // Clear pending save ref on error so we can retry
        pendingTitleSaveRef.current = null;
      } finally {
        // Always clear the saving flag
        isSavingTitleRef.current = false;
      }

      editorStatusVar('idle');
    }, 2000)
  ).current;

  // -------------------- Effect: Cleanup debounced saveIdeas on unmount --------------------
  useEffect(() => {
    logIdea('useEffect: cleanup debounced saveIdeas on unmount');
    return () => {
      logger.log("[Idea] Cleaning up debounced saveIdea on unmount");
      debouncedSave.cancel();
      throttledTitleSave.cancel();
      debouncedBackgroundTasks.cancel();
      clearScheduledRefetches();
    };
  }, [debouncedSave, throttledTitleSave, debouncedBackgroundTasks]);

  const prevIdeaIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (prevIdeaIdRef.current && prevIdeaIdRef.current !== currentIdeaId) {
      // Set the switching flag to prevent saves
      isSwitchingRef.current = true;
      
      // 1️⃣ Persist any queued debounced save for the previous idea **now**
      debouncedSave.flush();
      throttledTitleSave.flush?.(); // lodash/throttle provides flush
    }

    // 2️⃣ Cancel timers so they don't run against the new ideaId/context
    debouncedSave.cancel();
    throttledTitleSave.cancel();
    debouncedBackgroundTasks.cancel();
    clearScheduledRefetches();

    // 3️⃣ Reset local editor state for the new idea
    // NOTE: Don't update lastSavedRef.current.ideaId here - let the content loading
    // useEffect detect the switch and update it when content is successfully loaded
    contentRef.current = '';
    lastSavedRef.current = { content: '', ideaId: lastSavedRef.current.ideaId };
    setContent('');

    prevIdeaIdRef.current = currentIdeaId;
    
    // Clear the switching flag after a short delay to allow the new content to load
    setTimeout(() => {
      isSwitchingRef.current = false;
    }, 100);
  }, [currentIdeaId, debouncedSave, throttledTitleSave]);

  // Hydrate after the idea-switch reset above, including synchronous cache hits.
  // Resetting after this effect would erase cached notes until another response.
  useEffect(() => {
    // When fetching is complete and we have data, decide whether to update the editor.
    if (ideaData?.idea && !isFetching) {
      const ideaObj = (ideaData as any).idea;

      // Ensure the loaded data matches the current idea
      if (ideaObj.ideaId !== currentIdeaId) {
        logIdea('Skipping content load - ideaId mismatch', {
          loadedIdeaId: ideaObj.ideaId,
          currentIdeaId
        });
        return;
      }

      const mappedAspect = aspectMap[ideaAspect] || "description";
      const newContent = ideaObj[mappedAspect] ?? "";

      /**
       * If we've switched ideas (ideaId changed), always load the new content.
       * Otherwise, only overwrite local editor state when *both*:
       *   1. The remote content differs from what is currently shown, *and*
       *   2. We have no unsaved local edits (editor content matches the last
       *      version that was persisted).
       *
       * This prevents "rollback" where a slow network response delivers an
       * older version and clobbers freshly-typed characters.
       */
      const hasSwitchedIdeas = lastSavedRef.current.ideaId !== currentIdeaId;
      const noUnsavedChanges = contentRef.current === lastSavedRef.current.content;
      const contentDiffers = contentRef.current !== newContent;

      // Always load content when switching ideas, or when we have no unsaved changes and content differs
      if (hasSwitchedIdeas) {
        logIdea('Loading content into editor - switched ideas', {
          previousIdeaId: lastSavedRef.current.ideaId,
          currentIdeaId,
          newContentLength: newContent.length
        });
        setContent(newContent);
        contentRef.current = newContent;
        // Update lastSavedRef to reflect what's actually saved in the backend
        lastSavedRef.current = { content: newContent, ideaId: currentIdeaId };
      } else if (noUnsavedChanges && contentDiffers) {
        logIdea('Loading content into editor - content changed', {
          noUnsavedChanges,
          contentDiffers,
          newContentLength: newContent.length
        });
        setContent(newContent);
        contentRef.current = newContent;
        // Update lastSavedRef to reflect what's actually saved in the backend
        lastSavedRef.current = { content: newContent, ideaId: currentIdeaId };
      } else {
        logIdea('Skipping content load', {
          hasSwitchedIdeas,
          noUnsavedChanges,
          contentDiffers,
          currentContentLength: contentRef.current.length,
          newContentLength: newContent.length
        });
      }
    }
  }, [ideaData, isFetching, ideaAspect, currentIdeaId]);


  // Handle title input change
  const handleTitleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nextTitle = e.target.value;
    logIdea('title onChange', nextTitle);
    setTitle(nextTitle);
    syncIdeaTitleInCache(client.cache, currentIdeaId, nextTitle);
    throttledTitleSave(nextTitle, currentIdeaId);
  };

  const handleTitleFocus = () => {
    setIsEditingTitle(true);
    // Clear pending save ref when user starts editing again
    pendingTitleSaveRef.current = null;
  };

  const handleTitleBlur = () => {
    setIsEditingTitle(false);
    // Flush any pending save so that blur behaves like "commit"
    throttledTitleSave.flush?.();
  };

  const handleTitleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      titleInputRef.current?.blur();
      return;
    }

    if (event.key === 'Escape') {
      event.preventDefault();
      throttledTitleSave.cancel();
      pendingTitleSaveRef.current = null;
      if (backendTitle !== null) {
        setTitle(backendTitle);
        syncIdeaTitleInCache(client.cache, currentIdeaId, backendTitle);
      }
      setIsEditingTitle(false);
      titleInputRef.current?.blur();
    }
  };

  // Handle editor content change
  const handleEditorContentChange = (newContent: string) => {
    setContent(newContent);
    contentRef.current = newContent;

    const hasChanged = newContent !== lastSavedRef.current.content;
    if (hasChanged) {
      editorStatusVar('typing');
      debouncedSave(newContent, currentIdeaId);
      debouncedBackgroundTasks(newContent);
    }
  };

  // -------------------- Render UI --------------------
  const currentAspectLabel = aspectLabelMap[ideaAspect] || "Note";
  const showHeaderLabel = currentAspectLabel !== "Note";

  return (
    <div className="manifest-panel manifest-note flex h-full flex-col overflow-hidden">
      <div className="manifest-note-header">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-h-[1rem] flex-wrap items-center gap-2 text-xs font-medium text-gray500 dark:text-gray400">
            {panelActions}
            {showHeaderLabel ? <span>{currentAspectLabel}</span> : null}
          </div>

          <div className="flex flex-wrap items-center gap-1">
          {currentIdeaId && (
            <div className="flex flex-wrap items-center gap-1">
              <VersionButton ideaId={currentIdeaId} onVersionRestored={() => refetch()} />
              <ShareButton ideaId={currentIdeaId} />
            </div>
          )}
          </div>
        </div>

        <div className="flex flex-wrap items-end justify-between gap-2">
          <div className="group min-w-0 flex-1">
            <label className="sr-only" htmlFor="idea-title-input">Idea title</label>
            <input
              aria-describedby="idea-title-helper"
              aria-label="Idea title"
              className="manifest-note-title"
              id="idea-title-input"
              onBlur={handleTitleBlur}
              onChange={handleTitleInputChange}
              onFocus={handleTitleFocus}
              onKeyDown={handleTitleKeyDown}
              placeholder="Untitled Idea"
              ref={titleInputRef}
              type="text"
              value={title}
            />
            <p
              className="sr-only"
              id="idea-title-helper"
            >
              {isEditingTitle
                ? 'Press Enter to save, or Esc to cancel.'
                : 'Click the title to rename this idea.'}
            </p>
          </div>

        </div>
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <WikiLinksProvider value={wikiLinks}>
        <div className="manifest-note-content flex-1 overflow-auto">
          {ideaAspect === 'business-model-canvas' ? (
            <Suspense fallback={<div className="min-h-[16rem]" aria-busy="true" />}>
              <BusinessModelCanvasDisplay
                content={ideaData?.idea?.businessModelCanvas}
                fallbackMessage="Start typing your idea to generate the Business Model Canvas automatically."
                generationState={getDocumentGenerationState('business-model-canvas')}
              />
            </Suspense>
          ) : ideaAspect === 'cost-structure' ? (
            (() => {
              const bmcData = ideaData?.idea?.businessModelCanvas;
              const costData = bmcData ? extractCostStructure(bmcData) : null;
              return (
                <CostStructureDisplay
                  cost={costData}
                  generationState={getDocumentGenerationState('business-model-canvas')}
                />
              );
            })()
          ) : ideaAspect === 'pitch-deck' ? (
            <MarkdownDisplay 
              content={ideaData?.idea?.pitchDeck} 
              fallbackMessage="Start typing your idea to generate the Pitch Deck automatically."
              generationState={getDocumentGenerationState('pitch-deck')}
              title="Pitch Deck"
              variant="pitch-deck"
              documentType="pitch_deck"
            />
          ) : ideaAspect === 'product-requirements-document' ? (
            <MarkdownDisplay 
              content={ideaData?.idea?.productRequirementsDocument} 
              fallbackMessage="Start typing your idea to generate the Product Requirements Document automatically."
              generationState={getDocumentGenerationState('product-requirements-document')}
              title="Product Requirements Document"
              variant="prd"
              documentType="product_requirements_document"
            />
          ) : ideaAspect === 'knowledge-graph' ? (
            <KnowledgeGraphView
              graph={knowledgeGraph}
              loading={knowledgeLoading}
              ideaTitle={title || 'This idea'}
            />
          ) : ideaAspect === 'patent' ? (
            <ProvisionalPatentDisplay
              ideaId={currentIdeaId}
              fallbackMessage="Start typing your idea to generate the Provisional Patent Draft automatically."
              generationState={getDocumentGenerationState('patent')}
            />
          ) : (
            <div className="flex flex-col gap-6">
              <CitationBanner graph={knowledgeGraph} />
<Suspense fallback={<div className="min-h-[16rem]" aria-busy="true" />}>
              <TextArea
                value={content}
                onChange={handleEditorContentChange}
                editable={!isFetching}
                autoFocus={ideaAspect === 'description'}
                focusKey={`${currentIdeaId || 'no-idea'}-${ideaAspect}`}
                className="min-h-[16rem]"
                placeholder="Write your idea…"
              />
              </Suspense>
            </div>
          )}
        </div>
        </WikiLinksProvider>
        {/* Status footer is only meaningful on the editable Note (description)
            view. Read-only generated aspects (BMC, Pitch Deck, PRD, Patent,
            etc.) shouldn't display "Typing..." or "Saving..." since the user
            isn't editing them — this caused regression #16 where the
            indicator persisted across asset tabs. */}
        {ideaAspect === "description" ? (
          <div className="manifest-note-status shrink-0 border-t border-stone200/80 px-4 py-2 dark:border-neutral700">
            <div
              className="text-right text-xs font-medium text-gray500 dark:text-gray400"
              data-testid="idea-status-footer"
            >
              {status === "saving" && (
                <span className="flex items-center justify-end gap-2">
                  <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Saving...
                </span>
              )}
              {status === "typing" && (
                <span className="text-gray400 dark:text-gray500">Typing...</span>
              )}
              {status === "idle" && (
                <span className="text-success-600 dark:text-success-400 flex items-center justify-end gap-1.5">
                  <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                  All changes saved
                </span>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};
