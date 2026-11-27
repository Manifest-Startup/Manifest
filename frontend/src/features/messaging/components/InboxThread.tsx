import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
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
import { formatClockTime, threadTimeParts } from "../utils/inboxTime";
import InboxAvatar from "./InboxAvatar";
import "../inbox.css";

const newClientId = () =>
  typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

/** Unsent text per conversation, so switching chats never loses a half-written reply. */
const drafts = new Map<string, string>();

/** The composer grows with the text up to six lines, like Open Media's. */
const COMPOSER_LINE = 20;
const COMPOSER_MAX_LINES = 6;

/** How close to the bottom still counts as "reading the latest" (new messages then scroll into view). */
const NEAR_BOTTOM_PX = 120;

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
        <button type="button" className="om-more" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
          {expanded ? "Show less" : "Show more"}
        </button>
      ) : null}
    </>
  );
};

/** A reply on its way: shown at once, then replaced by Open Media's copy (or marked failed). */
interface PendingReply {
  clientId: string;
  content: string;
  failed?: string;
}

interface InboxThreadProps {
  conversationId: string;
  /** Shown until Open Media answers (for example the person's name from the list). */
  fallbackTitle?: string;
  onBack?: () => void;
}

/** One conversation, chat or email, laid out by Open Media, with a composer that replies through it. */
const InboxThread: React.FC<InboxThreadProps> = ({ conversationId, fallbackTitle, onBack }) => {
  const [draft, setDraftState] = useState(() => drafts.get(conversationId) ?? "");
  const [pending, setPending] = useState<PendingReply[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const stickToBottom = useRef(true);
  const { data, loading, error, refetch } = useQuery(GET_INBOX_CONVERSATION, {
    variables: { conversationId },
    pollInterval: MESSAGES_FALLBACK_POLL_MS,
    fetchPolicy: "cache-and-network",
    notifyOnNetworkStatusChange: false,
  });
  const [reply] = useMutation(REPLY_IN_INBOX, { refetchQueries: [GET_MY_INBOX] });
  const [markRead] = useMutation(MARK_INBOX_READ, { refetchQueries: [GET_MY_INBOX, GET_UNREAD_MESSAGE_COUNT] });

  const thread = data?.inboxConversation;
  const conversation = thread?.conversation;
  const items = useMemo(() => thread?.items ?? [], [thread]);
  const title = conversation?.title || fallbackTitle || "Conversation";
  const isEmail = conversation?.kind === "email";

  const setDraft = useCallback(
    (value: string) => {
      setDraftState(value);
      if (value) drafts.set(conversationId, value);
      else drafts.delete(conversationId);
    },
    [conversationId],
  );

  // Grow the composer with its text (and shrink it back), measured from zero each time.
  useLayoutEffect(() => {
    const node = inputRef.current;
    if (!node) return;
    node.style.height = "0px";
    // Empty: one line (a long placeholder must not make it taller).
    const content = draft ? node.scrollHeight : 0;
    const height = Math.min(Math.max(content, COMPOSER_LINE + 16), COMPOSER_LINE * COMPOSER_MAX_LINES + 16);
    node.style.height = `${height}px`;
    node.style.overflowY = node.scrollHeight > height ? "auto" : "hidden";
  }, [draft, conversation?.canReply]);

  // Scroll only the thread pane (never the page): to the end on open, and when something new
  // arrives while the person is already reading the latest messages.
  const lastKey = items.length ? items[items.length - 1].key : "";
  useLayoutEffect(() => {
    const node = scrollRef.current;
    if (node && stickToBottom.current) node.scrollTop = node.scrollHeight;
  }, [lastKey, pending.length, thread]);

  // Keep the latest message in view when the pane changes size (window resize, composer growing,
  // the phone keyboard opening) while the person is reading the end of the thread.
  useEffect(() => {
    const node = scrollRef.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (stickToBottom.current) node.scrollTop = node.scrollHeight;
    });
    observer.observe(node);
    if (node.firstElementChild) observer.observe(node.firstElementChild);
    return () => observer.disconnect();
  }, [thread]);

  const onScroll = () => {
    const node = scrollRef.current;
    if (node) stickToBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < NEAR_BOTTOM_PX;
  };

  // Ready to type as soon as a conversation opens on a keyboard device.
  useEffect(() => {
    if (window.matchMedia?.("(pointer: fine)").matches) inputRef.current?.focus({ preventScroll: true });
  }, [conversationId, conversation?.canReply]);

  const unread = conversation?.unreadCount ?? 0;
  useEffect(() => {
    if (unread > 0) void Promise.resolve().then(() => markRead({ variables: { conversationId } })).catch(() => undefined);
  }, [conversationId, unread, markRead]);

  const deliver = async (item: PendingReply) => {
    try {
      await reply({ variables: { conversationId, content: item.content, clientId: item.clientId } });
      await refetch();
      setPending((list) => list.filter((p) => p.clientId !== item.clientId));
    } catch (err) {
      const reason = err instanceof Error && err.message ? err.message : "Not delivered.";
      setPending((list) => list.map((p) => (p.clientId === item.clientId ? { ...p, failed: reason } : p)));
    }
  };

  const send = () => {
    const content = draft.trim();
    if (!content) return;
    const item: PendingReply = { clientId: newClientId(), content };
    stickToBottom.current = true;
    setPending((list) => [...list, item]);
    setDraft("");
    void deliver(item);
  };

  const retry = (item: PendingReply) => {
    setPending((list) => list.map((p) => (p.clientId === item.clientId ? { ...item, failed: undefined } : p)));
    void deliver({ ...item, failed: undefined });
  };

  const discard = (item: PendingReply) => {
    setPending((list) => list.filter((p) => p.clientId !== item.clientId));
    if (!draft.trim()) setDraft(item.content);
  };

  const lastMine = [...items].reverse().find((item) => item.kind === "message" && item.isMine);

  return (
    <div className="om-thread-pane" data-testid="inbox-thread">
      <header className="om-thread-header">
        <span className="om-header-side">
          {onBack ? (
            <button type="button" className="om-icon-button om-back" onClick={onBack} aria-label="Back to messages">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
          ) : null}
        </span>
        <div className="om-thread-who">
          <InboxAvatar small name={title} initials={conversation?.initials ?? title.slice(0, 1)} url={conversation?.avatarUrl} />
          <h2 className="om-thread-name">{title}</h2>
          <span className="om-thread-meta">
            {conversation ? (isEmail ? "Email" : "Open Media") : " "}
            {conversation?.ideaTitle ? ` · Re: ${conversation.ideaTitle}` : ""}
          </span>
        </div>
        <span className="om-header-side" />
      </header>

      <div className="om-thread-scroll" ref={scrollRef} onScroll={onScroll}>
        {loading && !thread ? (
          <div className="om-thread-content" aria-busy="true">
            <p role="status" className="sr-only">
              Loading conversation…
            </p>
            {[62, 44, 70, 38].map((width, index) => (
              <div key={index} className="om-message" data-mine={index % 2 === 1} data-start="true">
                <div className="om-bubble om-skeleton" style={{ width: `${width * 5}px` }} />
              </div>
            ))}
          </div>
        ) : error && !thread ? (
          <div className="om-state">
            <strong>Couldn&apos;t open this conversation</strong>
            Open Media didn&apos;t answer.
            <button type="button" className="om-pill-button" onClick={() => void refetch()}>
              Try again
            </button>
          </div>
        ) : items.length === 0 && pending.length === 0 ? (
          <div className="om-state">
            <strong>No messages yet</strong>
            Say hello to {title}.
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
              const sent = item.sentAt ? new Date(item.sentAt) : null;
              return (
                <div
                  key={item.key}
                  className="om-message"
                  data-mine={item.isMine}
                  data-start={item.groupStart}
                  data-end={item.groupEnd}
                  data-email={Boolean(item.subject) || undefined}
                >
                  {!item.isMine && item.groupStart && item.senderName && (conversation?.group || isEmail) ? (
                    <span className="om-sender">{item.senderName}</span>
                  ) : null}
                  <div className="om-bubble" title={sent ? sent.toLocaleString() : undefined}>
                    {item.subject ? <div className="om-bubble-subject">{item.subject}</div> : null}
                    <MessageBody item={item} />
                    {item.attachmentCount > 0 ? (
                      <div className="om-bubble-note">
                        {item.attachmentCount === 1 ? "1 attachment" : `${item.attachmentCount} attachments`} · open in Open Media
                      </div>
                    ) : null}
                  </div>
                  {item === lastMine && pending.length === 0 && sent ? (
                    <span className="om-receipt">Sent {formatClockTime(sent)}</span>
                  ) : null}
                </div>
              );
            })}
            {pending.map((item) => (
              <div key={item.clientId} className="om-message" data-mine="true" data-start="true" data-end="true" data-pending={!item.failed}>
                <div className="om-bubble" data-failed={Boolean(item.failed)}>
                  <div className="om-bubble-text">{item.content}</div>
                </div>
                {item.failed ? (
                  <span className="om-receipt om-receipt-failed" role="alert">
                    Not delivered.{" "}
                    <button type="button" onClick={() => retry(item)}>
                      Try again
                    </button>{" "}
                    ·{" "}
                    <button type="button" onClick={() => discard(item)}>
                      Edit
                    </button>
                  </span>
                ) : (
                  <span className="om-receipt">Sending…</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {!conversation ? null : !conversation.canReply ? (
        <div className="om-composer">
          <p className="om-composer-hint om-composer-hint-solo">
            You can read this here. Replies to this mailbox aren&apos;t set up yet; add its sending settings in Open Media.
          </p>
        </div>
      ) : (
        <div className="om-composer">
          <div className="om-composer-shell">
            <textarea
              ref={inputRef}
              value={draft}
              rows={1}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  send();
                }
              }}
              placeholder={isEmail ? `Reply to ${title}` : "Message"}
              aria-label={isEmail ? `Reply to ${title} by email` : `Message ${title}`}
              data-testid="inbox-composer"
            />
            <button
              type="button"
              className="om-send"
              onClick={send}
              disabled={!draft.trim()}
              aria-label="Send"
              data-testid="inbox-send"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 19V5m0 0l-6 6m6-6l6 6" />
              </svg>
            </button>
          </div>
          <p className="om-composer-hint">
            {isEmail ? "Sends as an email from your mailbox in Open Media. " : ""}
            <span className="om-composer-keys">Enter to send · Shift+Enter for a new line</span>
          </p>
        </div>
      )}
    </div>
  );
};

export default InboxThread;
