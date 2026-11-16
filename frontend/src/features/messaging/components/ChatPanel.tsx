import React, { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@apollo/client/react";

import { GET_CONVERSATION_MESSAGES, MARK_CONVERSATION_READ, SEND_MESSAGE } from "features/core/apollo/queries";
import { resolveBackendAssetUrl } from "features/core/network/urls";
import { createLogger } from "features/core/logError";
import type { ChatMessage as Message } from "features/core/apollo/operationTypes";

import { MESSAGES_FALLBACK_POLL_MS } from "../hooks/useLiveMessages";

const logger = createLogger("ChatPanel");

const newClientId = () =>
  typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

interface ChatPanelProps {
  conversationId: string;
  otherUserName: string;
  otherUserAvatar?: string | null;
  ideaTitle?: string | null;
  onBack?: () => void;
}

const ChatPanel: React.FC<ChatPanelProps> = ({
  conversationId,
  otherUserName,
  otherUserAvatar,
  ideaTitle,
  onBack,
}) => {
  const [newMessage, setNewMessage] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { data, loading, refetch } = useQuery(GET_CONVERSATION_MESSAGES, {
    variables: { conversationId, limit: 100 },
    pollInterval: MESSAGES_FALLBACK_POLL_MS,
    fetchPolicy: "cache-first",
    nextFetchPolicy: "cache-first",
  });

  const [sendMessage, { loading: sending }] = useMutation(SEND_MESSAGE, {
    onCompleted: () => {
      refetch();
      setNewMessage("");
    },
  });

  const [markRead] = useMutation(MARK_CONVERSATION_READ);

  const messages: Message[] = data?.conversationMessages || [];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  useEffect(() => {
    if (conversationId) {
      markRead({ variables: { conversationId } }).catch(() => undefined);
    }
  }, [conversationId, markRead]);

  const [sendError, setSendError] = useState<string | null>(null);

  const handleSend = async () => {
    if (!newMessage.trim() || sending) {
      return;
    }

    setSendError(null);
    try {
      // The same clientId makes a retried send land once in Open Media.
      await sendMessage({
        variables: {
          conversationId,
          content: newMessage.trim(),
          clientId: newClientId(),
        },
      });
    } catch (err) {
      logger.error("Failed to send message:", err);
      setSendError(err instanceof Error ? err.message : "Message not sent. Try again.");
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();

    if (isToday) {
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }

    return `${date.toLocaleDateString([], { month: "short", day: "numeric" })} ${date.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    })}`;
  };

  const initials = otherUserName
    .split(" ")
    .map((part) => part[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (
    <div className="manifest-panel min-w-0 flex h-full flex-col overflow-hidden" data-testid="chat-panel">
      <header className="border-b border-gray200 px-4 py-4 dark:border-neutral700 sm:px-5">
        <div className="flex items-center gap-3">
          {onBack ? (
            <button
              onClick={onBack}
              className="rounded-2xl p-2 text-gray500 hover:bg-white/80 hover:text-neutral900 dark:hover:bg-neutral800 dark:hover:text-white"
              aria-label="Back"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
          ) : null}

          {otherUserAvatar ? (
            <img src={resolveBackendAssetUrl(otherUserAvatar)} alt={otherUserName} className="h-11 w-11 rounded-lg object-cover shadow-none" />
          ) : (
            <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-neutral900 text-sm font-bold text-white shadow-none">
              {initials}
            </div>
          )}

          <div className="min-w-0 flex-1">
            <p className="text-base font-semibold text-neutral900 dark:text-white">{otherUserName}</p>
            <div className="mt-1 flex flex-wrap gap-2">
              <span className="manifest-pill">Via Open Media</span>
              {ideaTitle ? <span className="manifest-pill">Re: {ideaTitle}</span> : null}
            </div>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto bg-theme-primary px-4 py-5  sm:px-5">
        {loading && messages.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <div className="flex items-center gap-3 text-gray500 dark:text-gray400">
              <svg className="h-5 w-5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span className="text-sm font-medium">Loading messages...</span>
            </div>
          </div>
        ) : messages.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <div className="manifest-empty max-w-sm px-6 py-8 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-lg bg-white/85 shadow-none dark:bg-neutral800">
                <svg className="h-7 w-7 text-accent-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <p className="mt-4 text-sm font-semibold text-neutral900 dark:text-white">No messages yet</p>
              <p className="mt-1 text-sm text-gray500 dark:text-gray400">Send a message to start the conversation</p>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {messages.map((message) => (
              <div className={`flex ${message.isMine ? "justify-end" : "justify-start"}`} key={message.messageId}>
                <div
                  className={`max-w-[80%] rounded-lg px-4 py-3 shadow-none ${
                    message.isMine
                      ? "rounded-br-md bg-neutral900 text-white"
                      : "rounded-bl-md border border-gray200 bg-white/92 text-neutral900 dark:border-neutral700 dark:bg-neutral800 dark:text-white"
                  }`}
                >
                  <p className="whitespace-pre-wrap break-words text-sm leading-6">{message.content}</p>
                  <p className={`mt-2 text-[0.72rem] font-medium ${message.isMine ? "text-blue-100" : "text-gray500 dark:text-gray400"}`}>
                    {formatTime(message.createdAt)}
                  </p>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      <footer className="border-t border-gray200 px-4 py-4 dark:border-neutral700 sm:px-5">
        <div className="manifest-card p-3">
          <textarea
            value={newMessage}
            onChange={(event) => setNewMessage(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            rows={1}
            className="min-h-[5rem] w-full resize-none bg-transparent px-2 py-2 text-sm leading-6 text-neutral900 outline-none placeholder:text-gray400 dark:text-white dark:placeholder:text-gray500"
            data-testid="chat-message-input"
          />
          {sendError ? (
            <p role="alert" className="mt-2 text-xs text-red-600 dark:text-red-400">
              {sendError}
            </p>
          ) : null}
          <div className="mt-3 flex items-center justify-between gap-3">
            <p className="text-xs text-gray500 dark:text-gray400">Enter sends · Shift+Enter for a new line</p>
            <button
              onClick={handleSend}
              disabled={!newMessage.trim() || sending}
              className="manifest-control manifest-control-primary min-w-[7.5rem]"
              aria-label="Send message"
              data-testid="chat-send-button"
            >
              {sending ? (
                <>
                  <svg className="h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <span>Sending</span>
                </>
              ) : (
                <>
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                  <span>Send</span>
                </>
              )}
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default ChatPanel;
