import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@apollo/client/react";

import { GET_MY_CONVERSATIONS } from "features/core/apollo/queries";
import OpenMediaConnectPrompt from "features/open-media/OpenMediaConnectPrompt";
import { useOpenMediaLink } from "features/open-media/useOpenMediaLink";

import { MESSAGES_FALLBACK_POLL_MS, useLiveMessages } from "../hooks/useLiveMessages";
import ChatPanel from "./ChatPanel";
import ConversationsList from "./ConversationsList";
import type { Conversation } from "features/core/apollo/operationTypes";

const MessagesPage: React.FC = () => {
  const { conversationId: routeConversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<Conversation | null>(null);
  const openMedia = useOpenMediaLink();

  const { data, loading, error } = useQuery(GET_MY_CONVERSATIONS, {
    variables: { limit: 50, offset: 0 },
    skip: !openMedia.ready,
    pollInterval: MESSAGES_FALLBACK_POLL_MS,
    fetchPolicy: "cache-first",
    nextFetchPolicy: "cache-first",
  });
  useLiveMessages(openMedia.ready);

  useEffect(() => {
    const list: Conversation[] = data?.myConversations || [];
    if (!routeConversationId) {
      return;
    }
    const match = list.find((c) => c.conversationId === routeConversationId);
    if (match) {
      setSelected(match);
    }
  }, [data, routeConversationId]);

  const handleSelect = (conv: Conversation) => {
    setSelected(conv);
    navigate(`/messages/${conv.conversationId}`, { replace: false });
  };

  const handleBack = () => {
    setSelected(null);
    navigate("/messages", { replace: true });
  };

  const showListMobile = !selected;
  const showThreadMobile = Boolean(selected);

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
              purpose="send and receive messages with founders and investors"
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
      <div className="manifest-message-frame">
        <div className="flex min-w-0 flex-1">
          <div className="manifest-message-columns flex-col md:flex-row">
            <aside
              className={`w-full shrink-0 bg-theme-tertiary border-b border-stone200 dark:border-neutral700 md:w-72 md:border-b-0 md:border-r ${
                showListMobile ? "flex flex-col" : "hidden md:flex"
              } md:min-h-0`}
            >
              <div className="border-b border-stone200 px-4 py-3 dark:border-neutral700">
                <h1 className="text-lg font-semibold text-neutral900 dark:text-white">Inbox</h1>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto">
                <ConversationsList
                  onSelectConversation={handleSelect}
                  selectedConversationId={selected?.conversationId}
                  conversations={data?.myConversations || []}
                  loading={loading}
                  error={error}
                />
              </div>
            </aside>

            <section
              className={`min-h-0 flex-1 overflow-hidden ${showThreadMobile ? "flex flex-col" : "hidden md:flex md:flex-col"}`}
            >
              {selected ? (
                <ChatPanel
                  conversationId={selected.conversationId}
                  otherUserAvatar={selected.otherUserAvatar}
                  otherUserName={selected.otherUserName}
                  ideaTitle={selected.ideaTitle}
                  onBack={handleBack}
                />
              ) : (
                <div
                  className="manifest-empty flex flex-1 flex-col items-center justify-center px-6 py-16 text-center"
                  data-testid="messages-empty-state"
                >
                  <p className="text-base font-semibold text-neutral900 dark:text-white">Pick a conversation</p>
                  <p className="mt-2 max-w-sm text-sm text-gray500 dark:text-gray400">
                    New threads open from a published idea&apos;s founder panel. Messages are sent through Open Media.
                  </p>
                </div>
              )}
            </section>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MessagesPage;
