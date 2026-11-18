import React from "react";

import type { InboxConversation } from "features/core/apollo/operationTypes";

import { formatListTime } from "../utils/inboxTime";
import InboxAvatar from "./InboxAvatar";

interface InboxListProps {
  conversations: InboxConversation[];
  loading?: boolean;
  error?: unknown;
  selectedId?: string;
  onSelect: (conversation: InboxConversation) => void;
}

/** Every Open Media chat and email conversation in one list, newest first, as Open Media shows it. */
const InboxList: React.FC<InboxListProps> = ({ conversations, loading, error, selectedId, onSelect }) => {
  if (loading && conversations.length === 0) {
    return (
      <p role="status" className="om-state">
        Loading your inbox…
      </p>
    );
  }
  if (error && conversations.length === 0) {
    return (
      <div className="om-state" data-testid="inbox-error">
        <strong>Couldn&apos;t load your inbox</strong>
        Open Media didn&apos;t answer. Try again in a moment.
      </div>
    );
  }
  if (conversations.length === 0) {
    return (
      <div className="om-state" data-testid="inbox-empty">
        <strong>No messages yet</strong>
        Chats and email from Open Media show up here. Message an idea&apos;s founder to start a chat.
      </div>
    );
  }
  return (
    <div className="om-list" role="list">
      {conversations.map((conversation) => {
        const unread = conversation.unreadCount > 0;
        return (
          <button
            key={conversation.conversationId}
            type="button"
            role="listitem"
            className="om-row"
            data-unread={unread}
            aria-current={selectedId === conversation.conversationId}
            data-testid={`inbox-row-${conversation.conversationId}`}
            onClick={() => onSelect(conversation)}
          >
            <InboxAvatar name={conversation.title} initials={conversation.initials} url={conversation.avatarUrl} />
            <span className="om-row-main">
              <span className="om-row-top">
                <span className="om-row-name">{conversation.title}</span>
                <span className="om-row-time">{formatListTime(new Date(conversation.lastMessageAt))}</span>
              </span>
              {conversation.ideaTitle ? <span className="om-row-context">Re: {conversation.ideaTitle}</span> : null}
              <span className="om-row-bottom">
                <span className="om-row-preview">{conversation.preview}</span>
                {unread ? (
                  <span className="om-badge" aria-label={`${conversation.unreadCount} unread`}>
                    {conversation.unreadCount > 99 ? "99+" : conversation.unreadCount}
                  </span>
                ) : null}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
};

export default InboxList;
