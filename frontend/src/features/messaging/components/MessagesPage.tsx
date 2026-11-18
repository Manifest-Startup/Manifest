import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@apollo/client/react";

import { GET_MY_CONVERSATIONS, GET_MY_EMAIL_THREADS } from "features/core/apollo/queries";
import OpenMediaConnectPrompt from "features/open-media/OpenMediaConnectPrompt";
import { useOpenMediaLink } from "features/open-media/useOpenMediaLink";

import { MESSAGES_FALLBACK_POLL_MS, useLiveMessages } from "../hooks/useLiveMessages";
import ChatPanel from "./ChatPanel";
import ConversationsList from "./ConversationsList";
import EmailThreadPanel from "./EmailThreadPanel";
import EmailThreadsList from "./EmailThreadsList";
import type { Conversation, EmailThread } from "features/core/apollo/operationTypes";

type InboxTab = "chats" | "email";
const EMAIL_LIMIT = 100;

const MessagesPage: React.FC = () => {
  const { conversationId: routeConversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [tab, setTab] = useState<InboxTab>("chats");
  const [selectedEmail, setSelectedEmail] = useState<EmailThread | null>(null);
  const openMedia = useOpenMediaLink();

  // Every Open Media chat, not only the ones started from Manifest: one place for all of them.
  const { data, loading, error } = useQuery(GET_MY_CONVERSATIONS, {
    variables: { limit: 50, offset: 0, allApps: true },
    skip: !openMedia.ready,
    pollInterval: MESSAGES_FALLBACK_POLL_MS,
    fetchPolicy: "cache-first",
    nextFetchPolicy: "cache-first",
  });
  useLiveMessages(openMedia.ready);

  // Email is read live from Open Media when the tab opens; Manifest never stores it.
  const email = useQuery(GET_MY_EMAIL_THREADS, {
    variables: { limit: EMAIL_LIMIT },
    skip: !openMedia.ready || tab !== "email",
    fetchPolicy: "cache-and-network",
  });

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

  const handleEmailBack = () => setSelectedEmail(null);

  const openItem = tab === "chats" ? selected : selectedEmail;
  const showListMobile = !openItem;
  const showThreadMobile = Boolean(openItem);

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
                <div role="tablist" aria-label="Inbox" className="mt-3 flex gap-2">
                  {(["chats", "email"] as const).map((name) => (
                    <button
                      key={name}
                      role="tab"
                      aria-selected={tab === name}
                      data-testid={`inbox-tab-${name}`}
                      onClick={() => setTab(name)}
                      className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors ${
                        tab === name
                          ? "bg-neutral900 text-white dark:bg-white dark:text-neutral900"
                          : "text-gray500 hover:bg-white dark:text-gray400 dark:hover:bg-neutral800"
                      }`}
                    >
                      {name === "chats" ? "Chats" : "Email"}
                    </button>
                  ))}
                </div>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto">
                {tab === "chats" ? (
                  <ConversationsList
                    onSelectConversation={handleSelect}
                    selectedConversationId={selected?.conversationId}
                    conversations={data?.myConversations || []}
                    loading={loading}
                    error={error}
                  />
                ) : (
                  <EmailThreadsList
                    threads={email.data?.myEmailThreads || []}
                    loading={email.loading}
                    error={email.error}
                    selectedThreadId={selectedEmail?.threadId}
                    onSelectThread={setSelectedEmail}
                  />
                )}
              </div>
            </aside>

            <section
              className={`min-h-0 flex-1 overflow-hidden ${showThreadMobile ? "flex flex-col" : "hidden md:flex md:flex-col"}`}
            >
              {tab === "email" && selectedEmail ? (
                <EmailThreadPanel thread={selectedEmail} onBack={handleEmailBack} />
              ) : tab === "chats" && selected ? (
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
                  <p className="text-base font-semibold text-neutral900 dark:text-white">
                    {tab === "chats" ? "Pick a conversation" : "Pick an email"}
                  </p>
                  <p className="mt-2 max-w-sm text-sm text-gray500 dark:text-gray400">
                    {tab === "chats"
                      ? "All your Open Media chats are here. New ones open from a published idea's founder panel."
                      : "Email from the mailboxes you connected in Open Media. Reply in Open Media."}
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
