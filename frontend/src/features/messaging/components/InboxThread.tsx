import React, { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@apollo/client/react";

import {
  GET_INBOX_CONVERSATION,
  GET_MY_INBOX,
  GET_UNREAD_MESSAGE_COUNT,
  MARK_INBOX_READ,
  REPLY_IN_INBOX,
} from "features/core/apollo/queries";
import type { InboxItem } from "features/core/apollo/operationTypes";

import { MESSAGES_FALLBACK_POLL_MS } from "../hooks/useLiveMessages";
import { threadTimeParts } from "../utils/inboxTime";
import InboxAvatar from "./InboxAvatar";
import "../inbox.css";

const newClientId = () =>
  typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

/** Open Media collapses long email to ten lines with "Show more". */
const isLong = (item: InboxItem) => {
  const text = item.body.map((segment) => segment.text).join("");
  return text.length > 600 || text.split("\n").length > 10;
};

const MessageBody: React.FC<{ item: InboxItem }> = ({ item }) => {
  const long = isLong(item);
  const [expanded, setExpanded] = useState(false);
  return (
    <>
      <div className="om-bubble-text" data-collapsed={long && !expanded}>
        {item.body.map((segment, index) =>
          segment.url ? (
            <a key={index} href={segment.url} target="_blank" rel="noopener noreferrer nofollow">
              {segment.text}
            </a>
          ) : (
            <React.Fragment key={index}>{segment.text}</React.Fragment>
          ),
        )}
      </div>
      {long ? (
        <button type="button" className="om-more" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "Show less" : "Show more"}
        </button>
      ) : null}
    </>
  );
};

interface InboxThreadProps {
  conversationId: string;
  /** Shown until Open Media answers (for example the founder's name on an idea). */
  fallbackTitle?: string;
  onBack?: () => void;
}

/** One conversation, chat or email, laid out by Open Media, with a composer that replies through it. */
const InboxThread: React.FC<InboxThreadProps> = ({ conversationId, fallbackTitle, onBack }) => {
  const [draft, setDraft] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const { data, loading, error } = useQuery(GET_INBOX_CONVERSATION, {
    variables: { conversationId },
    pollInterval: MESSAGES_FALLBACK_POLL_MS,
    fetchPolicy: "cache-and-network",
  });
  const [reply, { loading: sending }] = useMutation(REPLY_IN_INBOX, {
    refetchQueries: [GET_INBOX_CONVERSATION, GET_MY_INBOX],
    awaitRefetchQueries: true,
  });
  const [markRead] = useMutation(MARK_INBOX_READ, { refetchQueries: [GET_MY_INBOX, GET_UNREAD_MESSAGE_COUNT] });

  const thread = data?.inboxConversation;
  const conversation = thread?.conversation;
  const items = useMemo(() => thread?.items ?? [], [thread]);
  const title = conversation?.title || fallbackTitle || "Conversation";
  const isEmail = conversation?.kind === "email";

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [items.length, conversationId]);

  const unread = conversation?.unreadCount ?? 0;
  useEffect(() => {
    if (unread > 0) void Promise.resolve().then(() => markRead({ variables: { conversationId } })).catch(() => undefined);
  }, [conversationId, unread, markRead]);

  const send = async () => {
    const content = draft.trim();
    if (!content || sending) return;
    setSendError(null);
    try {
      await reply({ variables: { conversationId, content, clientId: newClientId() } });
      setDraft("");
    } catch (err) {
      setSendError(err instanceof Error && err.message ? err.message : "Not sent. Try again.");
    }
  };

  return (
    <div className="om-thread-pane" data-testid="inbox-thread">
      <header className="om-thread-header">
        <span className="om-header-side">
          {onBack ? (
            <button type="button" className="om-icon-button om-back" onClick={onBack} aria-label="Back">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
          ) : null}
        </span>
        <div className="om-thread-who">
          <InboxAvatar small name={title} initials={conversation?.initials ?? title.slice(0, 1)} url={conversation?.avatarUrl} />
          <span className="om-thread-name">{title}</span>
          <span className="om-thread-meta">
            {isEmail ? "Email" : "Open Media"}
            {conversation?.ideaTitle ? ` · Re: ${conversation.ideaTitle}` : ""}
          </span>
        </div>
        <span className="om-header-side" />
      </header>

      <div className="om-thread-scroll">
        {loading && !thread ? (
          <p role="status" className="om-state">
            Loading…
          </p>
        ) : error && !thread ? (
          <div className="om-state">
            <strong>Couldn&apos;t open this conversation</strong>
            Try again in a moment.
          </div>
        ) : (
          <div className="om-thread-content">
            {items.map((item) => {
              if (item.kind === "time") {
                const parts = item.at ? threadTimeParts(new Date(item.at)) : null;
                return parts ? (
                  <p key={item.key} className="om-time">
                    <span className="om-time-day">{parts.day}</span> <span className="om-time-clock">{parts.time}</span>
                  </p>
                ) : null;
              }
              return (
                <div
                  key={item.key}
                  className="om-message"
                  data-mine={item.isMine}
                  data-start={item.groupStart}
                  data-end={item.groupEnd}
                >
                  {conversation?.group && !item.isMine && item.groupStart && item.senderName ? (
                    <span className="om-sender">{item.senderName}</span>
                  ) : null}
                  <div className="om-bubble">
                    {item.subject ? <div className="om-bubble-subject">{item.subject}</div> : null}
                    <MessageBody item={item} />
                    {item.attachmentCount > 0 ? (
                      <div className="om-bubble-note">
                        {item.attachmentCount === 1 ? "1 attachment" : `${item.attachmentCount} attachments`} in Open Media
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
            <div ref={endRef} />
          </div>
        )}
      </div>

      {!conversation ? null : !conversation.canReply ? (
        <div className="om-composer">
          <p className="om-composer-hint">This mailbox can&apos;t send email yet. Add its sending settings in Open Media.</p>
        </div>
      ) : (
        <div className="om-composer">
          <div className="om-composer-shell">
            <textarea
              value={draft}
              rows={1}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
              placeholder={isEmail ? `Reply to ${title}` : "Message"}
              aria-label={isEmail ? "Reply by email" : "Message"}
              data-testid="inbox-composer"
            />
            <button
              type="button"
              className="om-send"
              onClick={() => void send()}
              disabled={!draft.trim() || sending}
              aria-label="Send"
              data-testid="inbox-send"
            >
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 19V5m0 0l-6 6m6-6l6 6" />
              </svg>
            </button>
          </div>
          {sendError ? (
            <p role="alert" className="om-composer-error">
              {sendError}
            </p>
          ) : isEmail ? (
            <p className="om-composer-hint">Sent as an email from your mailbox in Open Media.</p>
          ) : null}
        </div>
      )}
    </div>
  );
};

export default InboxThread;
