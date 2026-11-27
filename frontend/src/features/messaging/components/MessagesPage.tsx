import React, { useCallback, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@apollo/client/react";

import { GET_GOALS, GET_MY_INBOX } from "features/core/apollo/queries";
import OpenMediaConnectPrompt from "features/open-media/OpenMediaConnectPrompt";
import { useOpenMediaLink } from "features/open-media/useOpenMediaLink";
import type { InboxConversation } from "features/core/apollo/operationTypes";

import { MESSAGES_FALLBACK_POLL_MS, useLiveMessages } from "../hooks/useLiveMessages";
import GoalsPanel from "./GoalsPanel";
import InboxList from "./InboxList";
import InboxThread from "./InboxThread";
import OutreachDraft, { pendingApproval } from "./OutreachDraft";
import "../inbox.css";

/** One inbox: every Open Media chat and email conversation, assembled by Open Media. */
const MessagesPage: React.FC = () => {
  const { conversationId: routeId } = useParams<{ conversationId?: string }>();
  const selectedId = routeId ? decodeURIComponent(routeId) : undefined;
  const navigate = useNavigate();
  const openMedia = useOpenMediaLink();
  const [params, setParams] = useSearchParams();
  const draftId = routeId ? undefined : params.get("draft") ?? undefined;
  // Same query (and cache) as the goals panel: the open draft is always the panel's version.
  const { data: goalsData, refetch: refetchGoals } = useQuery(GET_GOALS, {
    skip: !openMedia.ready,
    fetchPolicy: "cache-first",
  });
  const goals = goalsData?.goals ?? [];
  const waitingIds = goals.filter((g) => g.draft && pendingApproval(g)).map((g) => g.id);
  const draftGoal = draftId ? goals.find((g) => g.id === draftId && g.draft) : undefined;
  const openDraft = useCallback(
    (goalId?: string) => {
      if (routeId) navigate(goalId ? `/messages?draft=${encodeURIComponent(goalId)}` : "/messages");
      else setParams(goalId ? { draft: goalId } : {}, { replace: !goalId });
    },
    [navigate, routeId, setParams],
  );
  const afterDecision = useCallback(async () => {
    // Straight on to the next message waiting for an OK, as when going through them by voice.
    const result = await refetchGoals();
    const next = (result.data?.goals ?? []).find((g) => g.draft && pendingApproval(g) && g.id !== draftId);
    openDraft(next?.id);
  }, [draftId, openDraft, refetchGoals]);

  const [search, setSearch] = useState("");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const { data, loading, error, refetch } = useQuery(GET_MY_INBOX, {
    variables: { limit: 100 },
    skip: !openMedia.ready,
    pollInterval: MESSAGES_FALLBACK_POLL_MS,
    fetchPolicy: "cache-and-network",
    nextFetchPolicy: "cache-first",
  });
  useLiveMessages(openMedia.ready);

  const conversations = useMemo(() => data?.myInbox ?? [], [data]);
  const selected = conversations.find((c) => c.conversationId === selectedId);
  const words = search.toLowerCase().split(/\s+/).filter(Boolean);
  const shown = useMemo(
    () =>
      conversations.filter((c) => {
        // The open conversation stays listed after reading it clears its unread mark.
        if (unreadOnly && c.unreadCount === 0 && c.conversationId !== selectedId) return false;
        if (!words.length) return true;
        const text = [c.title, c.company, c.preview, c.ideaTitle].filter(Boolean).join(" ").toLowerCase();
        return words.every((word) => text.includes(word));
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [conversations, unreadOnly, selectedId, search],
  );
  const unreadTotal = conversations.reduce((sum, c) => sum + (c.unreadCount > 0 ? 1 : 0), 0);
  const open = useCallback(
    (conversation: InboxConversation) => navigate(`/messages/${encodeURIComponent(conversation.conversationId)}`),
    [navigate],
  );
  const back = () => navigate("/messages", { replace: true });

  if (!openMedia.ready) {
    return (
      <div className="manifest-page manifest-page-messages" data-testid="messages-page">
        <div className="mx-auto max-w-lg px-4 py-16">
          {openMedia.loading ? (
            <p role="status" className="text-center text-sm text-gray500 dark:text-gray400">
              Loading messages…
            </p>
          ) : !openMedia.enabled ? (
            <div className="manifest-empty px-6 py-10 text-center" data-testid="messages-unavailable">
              <p className="text-sm font-semibold text-neutral900 dark:text-white">Messages aren&apos;t available here</p>
              <p className="mt-2 text-sm text-gray500 dark:text-gray400">
                This Manifest server doesn&apos;t have Open Media turned on.
              </p>
            </div>
          ) : (
            <OpenMediaConnectPrompt
              purpose="see your chats and email, and message founders and investors"
              reconnect={Boolean(openMedia.status?.needsReconnect)}
              connectUrl={openMedia.connectUrl}
            />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="manifest-page manifest-page-messages" data-testid="messages-page">
      <div className="om-inbox" data-open={Boolean(selectedId || draftGoal)}>
        <aside className="om-list-pane" aria-label="Inbox">
          <div className="om-heading">
            <h1 className="om-title">Messages</h1>
            <button
              type="button"
              className="om-icon-button om-filter-button"
              aria-pressed={unreadOnly}
              aria-label={unreadOnly ? "Show all conversations" : "Show unread only"}
              title={unreadOnly ? "Show all" : "Unread only"}
              onClick={() => setUnreadOnly((value) => !value)}
              data-testid="inbox-unread-filter"
            >
              <svg width="19" height="19" viewBox="0 0 24 24" fill={unreadOnly ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.9" aria-hidden="true">
                <path strokeLinejoin="round" d="M3 7.5A2.5 2.5 0 0 1 5.5 5h9M21 11v6.5a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5v-10l9 6 4.5-3" />
                <circle cx="19" cy="6" r="2.6" fill="currentColor" stroke="none" />
              </svg>
              {unreadTotal > 0 && !unreadOnly ? <span className="om-filter-dot" aria-hidden="true" /> : null}
            </button>
          </div>
          <div className="om-search">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path strokeLinecap="round" d="m20 20-3.5-3.5" />
            </svg>
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") setSearch("");
              }}
              placeholder="Search messages"
              aria-label="Search messages"
              data-testid="inbox-search"
            />
          </div>
          <div className="om-list">
            <GoalsPanel selectedGoalId={draftGoal?.id} onOpenDraft={openDraft} />
            {goals.some((g) => g.draft) && shown.length ? <p className="om-section-label om-inbox-label">Inbox</p> : null}
            <InboxList
              conversations={shown}
              filtered={Boolean(words.length) || unreadOnly}
              unreadOnly={unreadOnly && !words.length}
              loading={loading}
              error={error}
              selectedId={selectedId}
              onSelect={open}
              onRetry={() => void refetch()}
            />
          </div>
        </aside>
        {selectedId ? (
          <InboxThread key={selectedId} conversationId={selectedId} fallbackTitle={selected?.title} onBack={back} />
        ) : draftGoal ? (
          <OutreachDraft
            key={draftGoal.id}
            goal={draftGoal}
            position={
              waitingIds.includes(draftGoal.id)
                ? { index: waitingIds.indexOf(draftGoal.id), total: waitingIds.length }
                : undefined
            }
            onBack={() => openDraft(undefined)}
            onDecided={() => void afterDecision()}
          />
        ) : (
          <section className="om-thread-pane" data-testid="messages-empty-state">
            <div className="om-state">
              <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h8M8 14h5m-9 6 2.4-3.2A8 8 0 1 1 20 12a8 8 0 0 1-8 8H4z" />
              </svg>
              <strong>Choose a conversation</strong>
              Your chats and email are together here. Replies go out through Open Media.
            </div>
          </section>
        )}
      </div>
    </div>
  );
};

export default MessagesPage;
