import React from "react";

import type { EmailThread } from "features/core/apollo/operationTypes";

import { formatListTime } from "../utils/formatListTime";

interface EmailThreadsListProps {
  threads: EmailThread[];
  loading?: boolean;
  error?: unknown;
  selectedThreadId?: string;
  onSelectThread: (thread: EmailThread) => void;
}

/** Email threads from the mailboxes connected in Open Media (read-only). */
const EmailThreadsList: React.FC<EmailThreadsListProps> = ({
  threads,
  loading,
  error,
  selectedThreadId,
  onSelectThread,
}) => {
  if (loading && threads.length === 0) {
    return (
      <p role="status" className="p-4 text-sm text-gray500 dark:text-gray400">
        Loading email…
      </p>
    );
  }

  if (error) {
    return (
      <div className="p-4">
        <div className="manifest-empty px-5 py-6 text-center" data-testid="email-error">
          <p className="text-sm font-semibold text-neutral900 dark:text-white">Couldn&apos;t load email</p>
          <p className="mt-1 text-sm text-gray500 dark:text-gray400">Open Media didn&apos;t answer. Try again in a moment.</p>
        </div>
      </div>
    );
  }

  if (threads.length === 0) {
    return (
      <div className="p-4">
        <div className="manifest-empty px-5 py-8 text-center" data-testid="email-empty">
          <p className="text-sm font-semibold text-neutral900 dark:text-white">No email yet</p>
          <p className="mt-1 text-sm text-gray500 dark:text-gray400">
            Connect a mailbox in Open Media and its email shows up here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-1 p-2">
      {threads.map((thread) => {
        const isSelected = selectedThreadId === thread.threadId;
        return (
          <button
            key={thread.threadId}
            onClick={() => onSelectThread(thread)}
            data-testid={`email-thread-${thread.threadId}`}
            aria-pressed={isSelected}
            className={`w-full rounded-lg border border-transparent px-3 py-3 text-left transition-colors ${
              isSelected
                ? "bg-accent-50 dark:bg-accent-900/20"
                : "bg-transparent hover:bg-white dark:hover:bg-neutral800"
            }`}
          >
            <div className="flex items-center justify-between gap-3">
              <p className="truncate text-sm font-semibold text-neutral900 dark:text-white">
                {thread.participants.join(", ") || "Unknown sender"}
                {thread.messageCount > 1 ? (
                  <span className="ml-1 font-normal text-gray500 dark:text-gray400">{thread.messageCount}</span>
                ) : null}
              </p>
              <span className="shrink-0 text-xs font-medium text-gray500 dark:text-gray400">
                {formatListTime(thread.lastMessageAt)}
              </span>
            </div>
            <p className="mt-1 truncate text-sm text-neutral900 dark:text-gray200">{thread.subject}</p>
            {thread.preview ? (
              <p className="mt-1 truncate text-sm text-gray500 dark:text-gray400">{thread.preview}</p>
            ) : null}
          </button>
        );
      })}
    </div>
  );
};

export default EmailThreadsList;
