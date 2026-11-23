import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@apollo/client/react";

import { GET_MY_INBOX } from "features/core/apollo/queries";
import OpenMediaConnectPrompt from "features/open-media/OpenMediaConnectPrompt";
import { useOpenMediaLink } from "features/open-media/useOpenMediaLink";
import type { InboxConversation } from "features/core/apollo/operationTypes";

import { MESSAGES_FALLBACK_POLL_MS, useLiveMessages } from "../hooks/useLiveMessages";
import GoalsPanel from "./GoalsPanel";
import InboxList from "./InboxList";
import InboxThread from "./InboxThread";
import "../inbox.css";

/** One inbox: every Open Media chat and email conversation, assembled by Open Media. */
const MessagesPage: React.FC = () => {
  const { conversationId: routeId } = useParams<{ conversationId?: string }>();
  const selectedId = routeId ? decodeURIComponent(routeId) : undefined;
  const navigate = useNavigate();
  const openMedia = useOpenMediaLink();

  const { data, loading, error } = useQuery(GET_MY_INBOX, {
    variables: { limit: 100 },
    skip: !openMedia.ready,
    pollInterval: MESSAGES_FALLBACK_POLL_MS,
    fetchPolicy: "cache-and-network",
    nextFetchPolicy: "cache-first",
  });
  useLiveMessages(openMedia.ready);

  const conversations = data?.myInbox ?? [];
  const selected = conversations.find((c) => c.conversationId === selectedId);
  const open = (conversation: InboxConversation) => navigate(`/messages/${encodeURIComponent(conversation.conversationId)}`);
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
      <div className="om-inbox" data-open={Boolean(selectedId)}>
        <aside className="om-list-pane" aria-label="Inbox">
          <div className="om-heading">
            <h1 className="om-title">Messages</h1>
          </div>
          <GoalsPanel />
          <InboxList
            conversations={conversations}
            loading={loading}
            error={error}
            selectedId={selectedId}
            onSelect={open}
          />
        </aside>
        {selectedId ? (
          <InboxThread key={selectedId} conversationId={selectedId} fallbackTitle={selected?.title} onBack={back} />
        ) : (
          <section className="om-thread-pane" data-testid="messages-empty-state">
            <div className="om-state">
              <strong>Pick a conversation</strong>
              Your chats and email are together here. Replies go out through Open Media.
            </div>
          </section>
        )}
      </div>
    </div>
  );
};

export default MessagesPage;
