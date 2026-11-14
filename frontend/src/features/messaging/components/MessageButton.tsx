import React, { useState } from "react";
import { useMutation, useReactiveVar } from "@apollo/client/react";

import { userVar } from "features/core/apollo/localState";
import { START_CONVERSATION } from "features/core/apollo/queries";
import { createLogger } from "features/core/logError";
import { useMessage } from "features/notifications/context/MessageContext";

import ChatPanel from "./ChatPanel";

const logger = createLogger("MessageButton");

interface MessageButtonProps {
  userId: string;
  userName: string;
  userAvatar?: string | null;
  ideaId?: string;
  ideaTitle?: string;
  variant?: "button" | "icon";
  size?: "sm" | "md" | "lg";
  className?: string;
}

const MessageButton: React.FC<MessageButtonProps> = ({
  userId,
  userName,
  userAvatar,
  ideaId,
  ideaTitle,
  variant = "button",
  size = "md",
  className = "",
}) => {
  const [showChat, setShowChat] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const { userData } = useReactiveVar(userVar);
  const { setMessage } = useMessage();
  const isSelf = Boolean(userData?.userId && userData.userId === userId);

  const [startConversation, { loading }] = useMutation(START_CONVERSATION);

  const handleClick = async () => {
    if (isSelf) {
      return;
    }

    try {
      const result = await startConversation({
        variables: {
          otherUserId: userId,
          ideaId,
        },
      });

      if (result.data?.startConversation?.conversationId) {
        setConversationId(result.data.startConversation.conversationId);
        setShowChat(true);
      }
    } catch (err) {
      logger.error("Failed to start conversation:", err);
      setMessage("Unable to start a conversation right now.", "error");
    }
  };

  const iconSizes = {
    sm: "h-4 w-4",
    md: "h-5 w-5",
    lg: "h-6 w-6",
  };

  const buttonSizes = {
    sm: "px-3 py-2 text-xs",
    md: "px-4 py-2.5 text-sm",
    lg: "px-5 py-3 text-base",
  };

  if (showChat && conversationId) {
    return (
      <div className="manifest-modal-backdrop">
        <div className="manifest-modal manifest-modal-compact h-[min(78vh,42rem)] w-full max-w-2xl overflow-hidden">
          <ChatPanel
            conversationId={conversationId}
            otherUserName={userName}
            otherUserAvatar={userAvatar}
            ideaTitle={ideaTitle}
            onBack={() => setShowChat(false)}
          />
        </div>
      </div>
    );
  }

  if (variant === "icon") {
    return (
      <button
        onClick={handleClick}
        disabled={loading || isSelf}
        className={`inline-flex items-center justify-center rounded-2xl border border-stone200 bg-white/88 p-2.5 text-neutral900 shadow-none hover:bg-stone50 dark:hover:bg-neutral800 hover:border-stone300 dark:border-neutral700 dark:bg-neutral900/84 dark:text-white dark:hover:border-neutral600 disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
        aria-label={isSelf ? "Your profile" : `Message ${userName}`}
        title={isSelf ? "You cannot message yourself" : undefined}
      >
        {loading ? (
          <svg className={`animate-spin ${iconSizes[size]}`} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
        ) : (
          <svg className={iconSizes[size]} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        )}
      </button>
    );
  }

  return (
    <button
      onClick={handleClick}
      disabled={loading || isSelf}
      className={`inline-flex items-center gap-2 rounded-2xl bg-neutral900 font-semibold text-white shadow-none hover:bg-stone50 dark:hover:bg-neutral800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-neutral900 ${buttonSizes[size]} ${className}`}
      title={isSelf ? "You cannot message yourself" : undefined}
    >
      {loading ? (
        <svg className={`animate-spin ${iconSizes[size]}`} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      ) : (
        <svg className={iconSizes[size]} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      )}
      <span>{isSelf ? "You" : "Message"}</span>
    </button>
  );
};

export default MessageButton;
