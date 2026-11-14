import React from "react";
import { Link } from "react-router-dom";
import { useMessage } from "../context/MessageContext";

const MessageBanner = () => {
  const { message, clearMessage } = useMessage();

  if (!message.text) {
    return null;
  }

  const tone =
    message.type === "error"
      ? {
          container:
            "bg-red-100 bg-red-100/95 text-red-800 border-red-200 dark:bg-red-950/80 dark:text-red-200 dark:border-red-900/70",
          icon: (
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M12 9v3.75m0 3.75h.008v.008H12v-.008zm8.25-.75A8.25 8.25 0 113.75 12a8.25 8.25 0 0116.5 0z" />
            </svg>
          ),
          title: "Action needed",
        }
      : message.type === "success"
        ? {
            container:
              "bg-green-100 bg-green-100/95 text-green-800 border-green-200 dark:bg-green-950/70 dark:text-green-100 dark:border-green-900/70",
            icon: (
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="m9 12.75 2.25 2.25L15 9.75m6 2.25a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            ),
            title: "Saved",
          }
        : {
            container:
              "bg-gray200 bg-gray200/95 text-neutral900 border-stone200 dark:bg-neutral900/95 dark:text-white dark:border-neutral700",
            icon: (
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M11.25 11.25 12 11.25v5.25h.75m-.75-9h.008v.008H12V7.5zM21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            ),
            title: "Notice",
          };

  return (
    <div
      className={`fixed left-1/2 z-[60] w-[min(calc(100%-1rem),36rem)] max-w-[calc(100%-1rem)] -translate-x-1/2 rounded-[24px] border shadow-panel backdrop-blur-xl top-[max(5rem,calc(env(safe-area-inset-top,0px)+4.5rem))] md:left-auto md:right-[max(1.5rem,env(safe-area-inset-right,0px))] md:top-[max(6rem,calc(env(safe-area-inset-top,0px)+5rem))] md:w-full md:max-w-xl md:translate-x-0 ${tone.container}`}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-start gap-3 px-4 py-3.5 sm:px-5">
        <div className="mt-0.5 shrink-0">{tone.icon}</div>
        <div className="min-w-0 flex-1">
          <p className="text-[0.7rem] font-bold uppercase tracking-[0.16em] opacity-75">{tone.title}</p>
          <p className="mt-1 text-sm font-medium leading-6">{message.text}</p>
          {message.link && (
            <Link
              to={message.link.url}
              onClick={clearMessage}
              className="mt-1.5 inline-flex items-center gap-1 text-xs font-semibold underline underline-offset-2 opacity-90 hover:opacity-100"
            >
              {message.link.label}
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
              </svg>
            </Link>
          )}
        </div>
        <button
          onClick={clearMessage}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-current/10 bg-white/50 text-current hover:bg-white/80 dark:bg-white/5 dark:hover:bg-white/10"
          aria-label="Dismiss"
          type="button"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </div>
    </div>
  );
};

export default MessageBanner;
