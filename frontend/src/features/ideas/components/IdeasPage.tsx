import React, { lazy, Suspense, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useReactiveVar } from "@apollo/client/react";

import { sidebarVar, similarIdeasVar, getSimilarIdeasEntry } from "features/core/apollo/localState";
import { createLogger } from "features/core/logError";
import { IdeaOwnerPanel } from "features/messaging/components";
import { subscribeToVoiceWorkspaceLayoutCommand } from "features/voice/voiceCommandEvents";
import Button from "features/common-ui/Button";
import { SidebarLeftIcon, SidebarRightIcon } from "features/common-ui/icons";

import IdeasList from "./IdeasList";

const Idea = lazy(() => import("./Idea").then((module) => ({ default: module.Idea })));

const logger = createLogger("IdeasPage");
const WORKSPACE_LAYOUT_STORAGE_KEY = "manifest:workspace-layout";

interface WorkspaceLayoutState {
  libraryCollapsed: boolean;
  contextCollapsed: boolean;
  focusMode: boolean;
}

const defaultWorkspaceLayout = (): WorkspaceLayoutState => ({
  libraryCollapsed: typeof window !== "undefined" && window.innerWidth < 1024,
  contextCollapsed: true,
  focusMode: false,
});

const isTypingTarget = (target: EventTarget | null) => {
  if (!(target instanceof HTMLElement)) {
    return false;
  }

  return Boolean(
    target.closest('input, textarea, select, [contenteditable="true"], .ProseMirror')
  );
};

const IdeasPage: React.FC = () => {
  logger.log("rendered");

  const { idea_id } = useParams<{ idea_id: string }>();
  const similarIdeasState = useReactiveVar(similarIdeasVar);
  const similarIdeasEntry = idea_id ? getSimilarIdeasEntry(similarIdeasState, idea_id) : null;
  const similarIdeas =
    similarIdeasEntry?.data ||
    (similarIdeasState.ideaId === idea_id ? similarIdeasState.data : "");
  const [layout, setLayout] = useState<WorkspaceLayoutState>(() => {
    if (typeof window === "undefined") {
      return defaultWorkspaceLayout();
    }

    try {
      const raw = window.localStorage.getItem(WORKSPACE_LAYOUT_STORAGE_KEY);
      if (!raw) {
        return defaultWorkspaceLayout();
      }

      return {
        ...defaultWorkspaceLayout(),
        ...JSON.parse(raw),
      };
    } catch {
      return defaultWorkspaceLayout();
    }
  });

  useEffect(() => {
    sidebarVar({ ...sidebarVar(), currentIdeaId: idea_id || null });
  }, [idea_id]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    window.localStorage.setItem(WORKSPACE_LAYOUT_STORAGE_KEY, JSON.stringify(layout));
  }, [layout]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) {
        return;
      }

      if (event.key === "Escape" && layout.focusMode) {
        setLayoutValue({ focusMode: false });
        return;
      }

      if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === "f") {
        event.preventDefault();
        setLayoutValue({ focusMode: !layout.focusMode });
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [layout.focusMode]);

  useEffect(() => {
    return subscribeToVoiceWorkspaceLayoutCommand(({ action }) => {
      setLayout((previous) => {
        if (action === "enable_focus_mode") {
          return { ...previous, focusMode: true };
        }

        if (action === "disable_focus_mode") {
          return { ...previous, focusMode: false };
        }

        if (action === "collapse_library") {
          return { ...previous, libraryCollapsed: true, focusMode: false };
        }

        if (action === "expand_library") {
          return { ...previous, libraryCollapsed: false, focusMode: false };
        }

        if (action === "collapse_context") {
          return { ...previous, contextCollapsed: true, focusMode: false };
        }

        return { ...previous, contextCollapsed: false, focusMode: false };
      });
    });
  }, []);

  const setLayoutValue = (updates: Partial<WorkspaceLayoutState>) => {
    setLayout((previous) => ({ ...previous, ...updates }));
  };

  if (!idea_id) {
    return (
      <div className="manifest-page">
        <div className="manifest-page-shell">
          <div className="px-4 py-3">
            <h1 className="text-2xl font-semibold tracking-tight text-neutral900 dark:text-white">
              Your ideas
            </h1>
            <p className="mt-1 text-sm text-gray500 dark:text-gray400">
              Open an idea or create a new one.
            </p>
          </div>
          <div className="h-[calc(100dvh-11rem)] min-h-[18rem] sm:h-[min(42rem,calc(100dvh-12rem))] lg:h-[calc(100dvh-12rem)]">
            <IdeasList />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="manifest-page manifest-page-workspace">
      <div className="manifest-workspace-shell">
        <div className="manifest-workspace-grid" data-focus-mode={layout.focusMode}
          data-library-open={!layout.focusMode && !layout.libraryCollapsed}
          data-context-open={!layout.focusMode && !layout.contextCollapsed}>
          <div id="workspace-library" className="manifest-workspace-library" hidden={layout.focusMode || layout.libraryCollapsed}>
              <IdeasList
                onToggleCollapse={() => setLayoutValue({ libraryCollapsed: !layout.libraryCollapsed, focusMode: false })}
              />
          </div>
          <div className="manifest-workspace-document">
            <Suspense fallback={<div role="status" className="p-4">Opening idea…</div>}>
            <Idea
              panelActions={<>
                {(layout.focusMode || layout.libraryCollapsed) && <Button variant="ghost" className="manifest-panel-toggle h-11 w-11 p-0"
                  aria-label="Show ideas" title="Show ideas" aria-expanded={false} aria-controls="workspace-library"
                  onClick={() => setLayoutValue({ libraryCollapsed: false, focusMode: false })}><SidebarLeftIcon /></Button>}
                {(layout.focusMode || layout.contextCollapsed) && <Button variant="ghost" className="manifest-panel-toggle h-11 w-11 p-0"
                  aria-label="Show similar ideas" title="Show similar ideas" aria-expanded={false} aria-controls="workspace-context"
                  onClick={() => setLayoutValue({ contextCollapsed: false, focusMode: false })}><SidebarRightIcon /></Button>}
              </>}
            />
            </Suspense>
          </div>
          <div id="workspace-context" className="manifest-workspace-context" hidden={layout.focusMode || layout.contextCollapsed}>
            {!layout.focusMode && !layout.contextCollapsed && (
              <IdeaOwnerPanel
                ideaId={idea_id}
                onToggleCollapse={() => setLayoutValue({ contextCollapsed: !layout.contextCollapsed, focusMode: false })}
                similarIdeas={similarIdeas}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default IdeasPage;
