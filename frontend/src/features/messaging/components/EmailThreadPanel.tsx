import React from "react";

import type { EmailThread } from "features/core/apollo/operationTypes";

interface EmailThreadPanelProps {
  thread: EmailThread;
  onBack?: () => void;
}

const formatSent = (value: string) =>
  new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

/** One email thread, oldest first. Replies happen in Open Media, which holds the mailbox. */
const EmailThreadPanel: React.FC<EmailThreadPanelProps> = ({ thread, onBack }) => (
  <div className="flex min-h-0 flex-1 flex-col" data-testid="email-thread-panel">
    <header className="border-b border-gray200 px-4 py-4 dark:border-neutral700 sm:px-5">
      <div className="flex items-center gap-3">
        {onBack ? (
          <button
            onClick={onBack}
            className="rounded-2xl p-2 text-gray500 hover:bg-white/80 hover:text-neutral900 dark:hover:bg-neutral800 dark:hover:text-white md:hidden"
            aria-label="Back"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
        ) : null}
        <div className="min-w-0 flex-1">
          <p className="text-base font-semibold text-neutral900 dark:text-white">{thread.subject}</p>
          <div className="mt-1 flex flex-wrap gap-2">
            <span className="manifest-pill">Email via Open Media</span>
            {thread.account ? <span className="manifest-pill">{thread.account}</span> : null}
          </div>
        </div>
        <a
          href={thread.replyUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="manifest-control manifest-control-primary shrink-0"
          data-testid="email-reply-link"
        >
          Reply in Open Media
        </a>
      </div>
    </header>

    <div className="flex-1 space-y-3 overflow-y-auto bg-theme-primary px-4 py-5 sm:px-5">
      {thread.messages.map((message) => (
        <article
          key={message.messageId || message.sentAt}
          className="rounded-lg border border-gray200 bg-white/92 px-4 py-3 dark:border-neutral700 dark:bg-neutral800"
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-sm font-semibold text-neutral900 dark:text-white" title={message.sender}>
              {message.senderName}
              {message.senderVerified ? (
                <span className="ml-1 text-xs font-normal text-gray500 dark:text-gray400">verified sender</span>
              ) : null}
            </p>
            <span className="text-xs text-gray500 dark:text-gray400">{formatSent(message.sentAt)}</span>
          </div>
          {message.recipients.length ? (
            <p className="mt-1 truncate text-xs text-gray500 dark:text-gray400">To {message.recipients.join(", ")}</p>
          ) : null}
          <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-neutral900 dark:text-white">
            {message.text || "(no text)"}
          </p>
          {message.attachmentCount > 0 ? (
            <p className="mt-2 text-xs text-gray500 dark:text-gray400">
              {message.attachmentCount === 1 ? "1 attachment" : `${message.attachmentCount} attachments`}, open in Open Media
            </p>
          ) : null}
        </article>
      ))}
    </div>
  </div>
);

export default EmailThreadPanel;
