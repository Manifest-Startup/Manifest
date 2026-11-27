import React, { memo } from "react";

import type { InboxConversation } from "features/core/apollo/operationTypes";

import { formatListTime } from "../utils/inboxTime";
import InboxAvatar from "./InboxAvatar";

interface InboxListProps {
  conversations: InboxConversation[];
  /** True when nothing matched the search or the unread filter (the inbox itself isn't empty). */
  filtered?: boolean;
  unreadOnly?: boolean;
  loading?: boolean;
  error?: unknown;
  selectedId?: string;
  onSelect: (conversation: InboxConversation) => void;
  onRetry?: () => void;
}

/** "Re: idea" for chats about a Manifest idea. (Open Media's list shows no company line: for email
 * it is only the sender's domain, which the name and logo already say.) */
const contextOf = (conversation: InboxConversation) => (conversation.ideaTitle ? `Re: ${conversation.ideaTitle}` : null);

const InboxRow = memo(function InboxRow({
  conversation,
  active,
  onSelect,
}: {
  conversation: InboxConversation;
  active: boolean;
  onSelect: (conversation: InboxConversation) => void;
}) {
  const unread = conversation.unreadCount > 0;
  const context = contextOf(conversation);
  const time = formatListTime(new Date(conversation.lastMessageAt));
  return (
    <li>
      <button
        type="button"
        className="om-row"
        data-unread={unread}
        aria-current={active ? "true" : undefined}
        aria-label={`${conversation.title}${conversation.kind === "email" ? ", email" : ""}. ${unread ? `${conversation.unreadCount} unread. ` : ""}${conversation.preview ?? ""}`}
        data-testid={`inbox-row-${conversation.conversationId}`}
        onClick={() => onSelect(conversation)}
      >
        <InboxAvatar name={conversation.title} initials={conversation.initials} url={conversation.avatarUrl} />
        <span className="om-row-main">
          <span className="om-row-top">
            <span className="om-row-name">{conversation.title}</span>
            <span className="om-row-time">{time}</span>
          </span>
          {context ? <span className="om-row-context">{context}</span> : null}
          <span className="om-row-bottom">
            {conversation.kind === "email" ? (
              <svg className="om-row-kind" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <rect x="3" y="5" width="18" height="14" rx="2" />
                <path d="m3 7 9 6 9-6" />
              </svg>
            ) : null}
            <span className="om-row-preview">{conversation.preview || "No messages yet"}</span>
            {unread ? (
              <span className="om-badge" aria-hidden="true">
                {conversation.unreadCount > 99 ? "99+" : conversation.unreadCount}
              </span>
            ) : null}
          </span>
        </span>
      </button>
    </li>
  );
});

/** Every Open Media chat and email conversation in one list, newest first, as Open Media shows it. */
const InboxList: React.FC<InboxListProps> = ({ conversations, filtered, unreadOnly, loading, error, selectedId, onSelect, onRetry }) => {
  if (loading && conversations.length === 0 && !filtered) {
    return (
      <div className="om-list" aria-busy="true">
        <p role="status" className="sr-only">
          Loading your inbox…
        </p>
        {[0, 1, 2, 3, 4].map((index) => (
          <div key={index} className="om-row om-row-skeleton" aria-hidden="true">
            <span className="om-avatar om-skeleton" />
            <span className="om-row-main">
              <span className="om-skeleton om-skeleton-line" style={{ width: "45%" }} />
              <span className="om-skeleton om-skeleton-line" style={{ width: "85%" }} />
            </span>
          </div>
        ))}
      </div>
    );
  }
  if (error && conversations.length === 0 && !filtered) {
    return (
      <div className="om-state" data-testid="inbox-error">
        <strong>Couldn&apos;t load your inbox</strong>
        Open Media didn&apos;t answer.
        {onRetry ? (
          <button type="button" className="om-pill-button" onClick={onRetry}>
            Try again
          </button>
        ) : null}
      </div>
    );
  }
  if (conversations.length === 0) {
    if (filtered && unreadOnly) {
      return (
        <div className="om-state" data-testid="inbox-caught-up">
          <strong>You&apos;re all caught up</strong>
          No unread messages or email.
        </div>
      );
    }
    if (filtered) {
      return (
        <div className="om-state" data-testid="inbox-no-match">
          <strong>No matches</strong>
          No conversation matches that search.
        </div>
      );
    }
    return (
      <div className="om-state" data-testid="inbox-empty">
        <strong>No messages yet</strong>
        Chats and email from Open Media show up here. Open an idea and message its founder to start a chat.
      </div>
    );
  }
  return (
    <ul className="om-list-rows" aria-label="Conversations">
      {conversations.map((conversation) => (
        <InboxRow
          key={conversation.conversationId}
          conversation={conversation}
          active={selectedId === conversation.conversationId}
          onSelect={onSelect}
        />
      ))}
    </ul>
  );
};

export default InboxList;
