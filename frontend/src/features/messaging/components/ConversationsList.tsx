import React from "react";
import { useQuery } from "@apollo/client/react";

import { GET_MY_CONVERSATIONS } from "features/core/apollo/queries";
import { resolveBackendAssetUrl } from "features/core/network/urls";
import type { Conversation } from "features/core/apollo/operationTypes";

import { MESSAGES_FALLBACK_POLL_MS } from "../hooks/useLiveMessages";
import { formatListTime } from "../utils/formatListTime";

interface ConversationsListProps {
  onSelectConversation: (conv: Conversation) => void;
  selectedConversationId?: string;
  conversations?: Conversation[];
  loading?: boolean;
  error?: unknown;
}

const ConversationsList: React.FC<ConversationsListProps> = ({
  onSelectConversation,
  selectedConversationId,
  conversations: providedConversations,
  loading: providedLoading,
  error: providedError,
}) => {
  const shouldLoadConversations = !providedConversations;
  const { data, loading, error } = useQuery(GET_MY_CONVERSATIONS, {
    variables: { limit: 50, offset: 0 },
    skip: !shouldLoadConversations,
    pollInterval: MESSAGES_FALLBACK_POLL_MS,
    fetchPolicy: "cache-first",
    nextFetchPolicy: "cache-first",
  });

  const conversations: Conversation[] = providedConversations ?? data?.myConversations ?? [];
  const isLoading = providedLoading ?? loading;
  const queryError = providedError ?? error;

  if (isLoading) {
    return (
      <div className="space-y-3 p-4">
        {[1, 2, 3].map((item) => (
          <div className="animate-pulse rounded-lg bg-white/75 p-4 shadow-none dark:bg-neutral800" key={item}>
            <div className="flex gap-3">
              <div className="h-11 w-11 rounded-lg bg-gray200 dark:bg-neutral700" />
              <div className="flex-1 space-y-2">
                <div className="h-4 w-1/3 rounded-full bg-gray200 dark:bg-neutral700" />
                <div className="h-3 w-2/3 rounded-full bg-gray200 dark:bg-neutral700" />
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (queryError) {
    return (
      <div className="p-4">
        <div className="manifest-empty px-5 py-6 text-center">
          <p className="text-sm font-semibold text-neutral900 dark:text-white">Failed to load conversations</p>
        </div>
      </div>
    );
  }

  if (conversations.length === 0) {
    return (
      <div className="p-4">
        <div className="manifest-empty px-5 py-8 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-lg bg-white/85 shadow-none dark:bg-neutral800">
            <svg className="h-6 w-6 text-accent-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </div>
          <p className="mt-4 text-sm font-semibold text-neutral900 dark:text-white">No conversations yet</p>
          <p className="mt-1 text-sm text-gray500 dark:text-gray400">Your Open Media chats show up here. Message an idea&apos;s founder to start one.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-1 p-2">
      {conversations.map((conversation) => {
        const initials = conversation.otherUserName
          .split(" ")
          .map((part) => part[0])
          .join("")
          .toUpperCase()
          .slice(0, 2);
        const isSelected = selectedConversationId === conversation.conversationId;

        return (
          <button
            key={conversation.conversationId}
            onClick={() => onSelectConversation(conversation)}
            data-testid={`conversation-item-${conversation.conversationId}`}
            aria-pressed={isSelected}
            className={`w-full rounded-lg border border-transparent px-3 py-3 text-left transition-colors ${
              isSelected
                ? "bg-accent-50 dark:bg-accent-900/20"
                : "bg-transparent hover:bg-white dark:hover:bg-neutral800"
            }`}
          >
            <div className="flex items-start gap-3">
              {conversation.otherUserAvatar ? (
                <img
                  src={resolveBackendAssetUrl(conversation.otherUserAvatar)}
                  alt={conversation.otherUserName}
                  className="h-11 w-11 rounded-lg object-cover shadow-none"
                />
              ) : (
                <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-neutral900 text-sm font-bold text-white shadow-none">
                  {initials}
                </div>
              )}

              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-sm font-semibold text-neutral900 dark:text-white">
                    {conversation.otherUserName}
                    {conversation.otherUserHandle ? (
                      <span className="ml-1 font-normal text-gray500 dark:text-gray400">@{conversation.otherUserHandle}</span>
                    ) : null}
                  </p>
                  <span className="text-xs font-medium text-gray500 dark:text-gray400">{formatListTime(conversation.lastMessageAt)}</span>
                </div>
                {conversation.ideaTitle ? (
                  <p className="mt-1 text-xs font-semibold uppercase tracking-[0.12em] text-accent-600 dark:text-accent-300">
                    Re: {conversation.ideaTitle}
                  </p>
                ) : null}
                {conversation.lastMessagePreview ? (
                  <p className="mt-2 truncate text-sm text-gray500 dark:text-gray400">{conversation.lastMessagePreview}</p>
                ) : null}
              </div>

              {conversation.unreadCount > 0 ? (
                <div className="flex h-6 min-w-[1.5rem] items-center justify-center rounded-full bg-neutral900 px-2 text-xs font-bold text-white dark:bg-white dark:text-neutral900">
                  {conversation.unreadCount > 9 ? "9+" : conversation.unreadCount}
                </div>
              ) : null}
            </div>
          </button>
        );
      })}
    </div>
  );
};

export default ConversationsList;
