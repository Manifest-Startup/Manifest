import React, { useState } from "react";
import { useMutation, useQuery, useReactiveVar } from "@apollo/client/react";

import Button from "features/common-ui/Button";
import { ChevronLeftIcon, ChevronRightIcon } from "features/common-ui/icons";
import SimilarIdeas from "features/ideas/components/SimilarIdeas";
import { userVar } from "features/core/apollo/localState";
import { GET_IDEA_CORE, GET_IDEA_OWNER, START_CONVERSATION } from "features/core/apollo/queries";
import { resolveBackendAssetUrl } from "features/core/network/urls";
import { createLogger } from "features/core/logError";
import { useMessage } from "features/notifications/context/MessageContext";

import ChatPanel from "./ChatPanel";

const logger = createLogger("IdeaOwnerPanel");

interface IdeaOwnerPanelProps {
  ideaId: string;
  similarIdeas?: string;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  onClose?: () => void;
}

const IdeaOwnerPanel: React.FC<IdeaOwnerPanelProps> = ({
  ideaId,
  similarIdeas,
  collapsed = false,
  onToggleCollapse,
}) => {
  const [showChat, setShowChat] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const { userData } = useReactiveVar(userVar);
  const { setMessage } = useMessage();

  const {
    data: coreData,
    loading: coreLoading,
  } = useQuery(GET_IDEA_CORE, {
    variables: { ideaId },
    skip: !ideaId,
  });

  const coreIdea = coreData?.idea;
  const isOwnFromCore = Boolean(
    coreIdea?.userId && userData?.userId && coreIdea.userId === userData.userId,
  );

  const {
    data: ownerData,
    loading: ownerLoading,
    error: ownerError,
  } = useQuery(GET_IDEA_OWNER, {
    variables: { ideaId },
    skip: !ideaId || coreLoading || isOwnFromCore,
  });

  const [startConversation, { loading: startingConversation }] = useMutation(START_CONVERSATION);

  const owner = ownerData?.ideaOwner;
  const isOwnIdea =
    isOwnFromCore || Boolean(owner?.userId && userData?.userId && owner.userId === userData.userId);

  const renderScrollableContent = (content: React.ReactNode) => (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="manifest-context-content min-h-0 flex-1 overflow-y-auto overflow-x-hidden" data-testid="idea-owner-panel-scroll">
        <div className="space-y-4">{content}</div>
      </div>
    </div>
  );

  const collapseAction = onToggleCollapse ? (
    <Button
      aria-expanded
      aria-label="Collapse similar ideas"
      className="manifest-panel-toggle h-11 w-11 p-0"
      onClick={onToggleCollapse}
      title="Collapse similar ideas"
      type="button"
      variant="ghost"
    >
      <ChevronRightIcon className="h-5 w-5" />
    </Button>
  ) : null;

  if (collapsed) {
    return (
      <aside className="manifest-panel flex h-full flex-col overflow-hidden">
        <div className="border-b border-gray200 px-3 py-4 dark:border-neutral700">
          <div className="flex flex-col items-center gap-2">
            <Button
              aria-expanded={false}
              aria-label="Expand similar ideas"
              className="h-12 w-12 rounded-lg p-0"
              onClick={onToggleCollapse}
              title="Expand similar ideas"
              type="button"
              variant="secondary"
            >
              <ChevronLeftIcon className="h-6 w-6" />
            </Button>
          </div>
        </div>

        <div className="flex flex-1 items-center justify-center px-2 py-4">
          <p className="text-center text-[0.7rem] font-medium text-gray500 dark:text-gray400">
            Similar
          </p>
        </div>
      </aside>
    );
  }

  if (coreLoading) {
    return renderScrollableContent(
      <SimilarIdeas compact headerAction={collapseAction} ideaId={ideaId} similarIdeas={similarIdeas} />,
    );
  }

  if (isOwnIdea) {
    return renderScrollableContent(
      <SimilarIdeas compact headerAction={collapseAction} ideaId={ideaId} similarIdeas={similarIdeas} />,
    );
  }

  const canMessageFounder = Boolean(owner?.canMessage) && !isOwnIdea;

  const handleStartChat = async () => {
    if (!owner || isOwnIdea || !owner.canMessage) {
      return;
    }

    try {
      const result = await startConversation({
        variables: {
          otherUserId: owner.userId,
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

  if (showChat && conversationId && owner) {
    return (
      <ChatPanel
        conversationId={conversationId}
        otherUserAvatar={owner.profilePictureUrl}
        otherUserName={`${owner.firstName || ""} ${owner.lastName || ""}`.trim() || owner.username || "Owner"}
        ideaTitle={owner.ideaTitle}
        onBack={() => setShowChat(false)}
      />
    );
  }

  if (ownerLoading) {
    return renderScrollableContent(
      <>
        <SimilarIdeas compact headerAction={collapseAction} ideaId={ideaId} similarIdeas={similarIdeas} />
        <div className="manifest-panel flex h-full flex-col overflow-hidden">
          <div className="border-b border-gray200 px-5 py-4 dark:border-neutral700">
            <h3 className="text-base font-semibold text-neutral900 dark:text-white">Founder</h3>
          </div>
          <div className="flex flex-1 items-center justify-center px-5 py-8">
            <div className="flex items-center gap-3 text-gray500 dark:text-gray400">
              <svg className="h-5 w-5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span className="text-sm font-medium">Loading founder...</span>
            </div>
          </div>
        </div>
      </>
    );
  }

  if (ownerError || !owner) {
    return renderScrollableContent(
      <>
        <SimilarIdeas compact headerAction={collapseAction} ideaId={ideaId} similarIdeas={similarIdeas} />
        <div className="manifest-empty px-5 py-6 text-sm leading-6">
          Founder details are unavailable right now.
        </div>
      </>
    );
  }

  const ownerName = `${owner.firstName || ""} ${owner.lastName || ""}`.trim() || owner.username || "Anonymous";
  const initials = ownerName
    .split(" ")
    .map((part: string) => part[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return renderScrollableContent(
    <>
      <SimilarIdeas compact headerAction={collapseAction} ideaId={ideaId} similarIdeas={similarIdeas} />

      <div className="manifest-panel overflow-hidden">
        <div className="border-b border-gray200 px-5 py-4 dark:border-neutral700">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-base font-semibold text-neutral900 dark:text-white">Founder</h3>
            <span className="manifest-pill">Founder</span>
          </div>
        </div>

        <div className="space-y-5 px-5 py-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            {owner.profilePictureUrl ? (
              <img
                src={resolveBackendAssetUrl(owner.profilePictureUrl)}
                alt={ownerName}
                className="h-20 w-20 rounded-lg border border-stone200 object-cover shadow-none dark:border-neutral700"
              />
            ) : (
              <div className="flex h-20 w-20 items-center justify-center rounded-lg bg-neutral900 text-2xl font-bold text-white shadow-none">
                {initials}
              </div>
            )}

            <div className="min-w-0 flex-1">
              <h4 className="text-xl font-semibold tracking-[-0.02em] text-neutral900 dark:text-white">{ownerName}</h4>
              <div className="mt-2 flex flex-wrap gap-2">
                <span className="manifest-pill">{canMessageFounder ? "Open to messages" : "Not published"}</span>
                {owner.ideaTitle ? <span className="manifest-pill">{owner.ideaTitle}</span> : null}
              </div>
              {owner.bio ? <p className="mt-3 text-sm leading-6 text-gray500 dark:text-gray400">{owner.bio}</p> : null}
            </div>
          </div>

          <div className="manifest-panel-muted p-4">
            <p className="text-sm font-semibold text-neutral900 dark:text-white">
              {canMessageFounder ? "Message founder" : "Founder messaging"}
            </p>
            <p className="mt-2 text-sm leading-6 text-gray500 dark:text-gray400">
              {canMessageFounder
                ? "Ask questions or discuss next steps."
                : "This idea is not published yet, so only the owner can see full collaboration options."}
            </p>
            <button
              className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-neutral900 px-4 py-3 text-sm font-semibold text-white shadow-none hover:bg-stone50 dark:hover:bg-neutral800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-neutral900"
              disabled={startingConversation || !canMessageFounder}
              onClick={handleStartChat}
              data-testid="message-founder-button"
            >
              {startingConversation ? (
                <>
                  <svg className="h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <span>Starting chat...</span>
                </>
              ) : (
                <>
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                  <span>{canMessageFounder ? "Message founder" : "Publish to message"}</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </>
  );
};

export default IdeaOwnerPanel;
