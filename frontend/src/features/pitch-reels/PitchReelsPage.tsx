import React, {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useReactiveVar } from "@apollo/client/react";

import { GET_PITCH_REELS_FEED } from "features/core/apollo/queries";
import { userVar } from "features/core/apollo/localState";
import Button from "features/common-ui/Button";

import { createLogger } from "features/core/logError";
import { subscribeToVoiceShortsCommand } from "features/voice/voiceCommandEvents";

import { htmlToPlainText } from "./htmlToPlainText";
import { mapPitchReelToShortClip } from "./mapPitchReelToShortClip";
import PitchReelVideo from "./PitchReelVideo";
import type { ShortClip } from "./types";
import { usePersistentShortsState } from "./usePersistentShortsState";

const InvestmentModal = lazy(
  () => import("features/investments/components/InvestmentModal"),
);

const logger = createLogger("PitchReelsPage");
const INITIAL_FEED_LIMIT = 12;
const FEED_PAGE_SIZE = 12;
const MAX_FEED_LIMIT = 48;

const formatCount = (value: number) => {
  if (value >= 1000) {
    const compact = value / 1000;
    return `${compact % 1 === 0 ? compact.toFixed(0) : compact.toFixed(1)}K`;
  }
  return value.toString();
};

const timeAgoLabel = (createdAt: string) => {
  const deltaMs = Date.now() - new Date(createdAt).getTime();
  const deltaMinutes = Math.max(1, Math.floor(deltaMs / 60000));

  if (deltaMinutes < 60) {
    return `${deltaMinutes}m ago`;
  }

  const deltaHours = Math.floor(deltaMinutes / 60);
  if (deltaHours < 24) {
    return `${deltaHours}h ago`;
  }

  return `${Math.floor(deltaHours / 24)}d ago`;
};

const VolumeIcon = ({ muted }: { muted: boolean }) => (
  <svg
    className="h-5 w-5"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
  >
    {muted ? (
      <>
        <path
          d="M11 5 6.5 9H3v6h3.5l4.5 4V5Z"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.9}
        />
        <path
          d="m16 9 5 6M21 9l-5 6"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.9}
        />
      </>
    ) : (
      <>
        <path
          d="M11 5 6.5 9H3v6h3.5l4.5 4V5Z"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.9}
        />
        <path
          d="M16 9.5a4 4 0 0 1 0 5"
          strokeLinecap="round"
          strokeWidth={1.9}
        />
        <path
          d="M18.7 6.8a7.5 7.5 0 0 1 0 10.4"
          strokeLinecap="round"
          strokeWidth={1.9}
        />
      </>
    )}
  </svg>
);

const HeartIcon = ({ active }: { active: boolean }) => (
  <svg
    className="h-6 w-6"
    fill={active ? "currentColor" : "none"}
    viewBox="0 0 24 24"
    stroke="currentColor"
  >
    <path
      d="M12 20.5 4.7 13.7A4.8 4.8 0 1 1 11.5 6.9L12 7.4l.5-.5a4.8 4.8 0 1 1 6.8 6.8L12 20.5Z"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={active ? 0 : 1.9}
    />
  </svg>
);

const CommentIcon = () => (
  <svg
    className="h-6 w-6"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
  >
    <path
      d="M7 18.5 3.5 21V6.5A2.5 2.5 0 0 1 6 4h12A2.5 2.5 0 0 1 20.5 6.5v8A2.5 2.5 0 0 1 18 17H7Z"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.9}
    />
  </svg>
);

const ShareIcon = () => (
  <svg
    className="h-6 w-6"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
  >
    <path d="M8 12 16 7" strokeLinecap="round" strokeWidth={1.9} />
    <path d="m8 12 8 5" strokeLinecap="round" strokeWidth={1.9} />
    <circle cx="18" cy="6" r="2.5" strokeWidth={1.9} />
    <circle cx="6" cy="12" r="2.5" strokeWidth={1.9} />
    <circle cx="18" cy="18" r="2.5" strokeWidth={1.9} />
  </svg>
);

const SaveIcon = ({ active }: { active: boolean }) => (
  <svg
    className="h-6 w-6"
    fill={active ? "currentColor" : "none"}
    viewBox="0 0 24 24"
    stroke="currentColor"
  >
    <path
      d="M7 4.5h10A1.5 1.5 0 0 1 18.5 6v13l-6.5-3.7L5.5 19V6A1.5 1.5 0 0 1 7 4.5Z"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={active ? 0 : 1.9}
    />
  </svg>
);

const ArrowIcon = () => (
  <svg
    className="h-4 w-4"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
  >
    <path
      d="m9 5 7 7-7 7"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
    />
  </svg>
);

const CloseIcon = () => (
  <svg
    className="h-5 w-5"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
  >
    <path
      d="m6 6 12 12M18 6 6 18"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.9}
    />
  </svg>
);

interface ActionButtonProps {
  icon: React.ReactNode;
  ariaLabel: string;
  /** Shown under the icon when `count` is omitted (e.g. "Invest"). */
  caption?: string;
  count?: number;
  onClick: () => void;
  active?: boolean;
  testId?: string;
}

const ActionButton: React.FC<ActionButtonProps> = ({
  icon,
  ariaLabel,
  caption,
  count,
  onClick,
  active = false,
  testId,
}) => {
  const visibleText =
    count !== undefined ? formatCount(count) : (caption ?? ariaLabel);
  return (
    <button
      type="button"
      onClick={onClick}
      className={`manifest-reel-action ${active ? "is-active" : ""}`}
      aria-label={ariaLabel}
      data-testid={testId}
    >
      {icon}
      <span>{visibleText}</span>
    </button>
  );
};

type ClipPlainText = {
  titlePlain: string;
  subtitlePlain: string;
  thesisPlain: string;
  descriptionPlain: string;
};

const PitchReelsPage: React.FC = () => {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const slideRefs = useRef<Array<HTMLElement | null>>([]);
  const videoRefs = useRef<Array<HTMLVideoElement | null>>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [openCommentsClipId, setOpenCommentsClipId] = useState<string | null>(
    null,
  );
  const [openInvestClipId, setOpenInvestClipId] = useState<string | null>(null);
  const [commentDraft, setCommentDraft] = useState("");
  const [videoErrors, setVideoErrors] = useState<Record<string, boolean>>({});
  const [feedLimit, setFeedLimit] = useState(INITIAL_FEED_LIMIT);
  const [feedLoadStalled, setFeedLoadStalled] = useState(false);
  const { userData } = useReactiveVar(userVar);
  const viewerUserId = userData?.userId ?? "";

  const {
    state,
    likedClipIds,
    savedClipIds,
    followedCreatorIds,
    toggleLike,
    toggleSave,
    toggleFollow,
    setMuted,
    addComment,
  } = usePersistentShortsState();

  const {
    data: feedData,
    loading: feedLoading,
    error: feedError,
    refetch,
    startPolling,
    stopPolling,
  } = useQuery(GET_PITCH_REELS_FEED, {
    variables: { limit: feedLimit },
    notifyOnNetworkStatusChange: true,
    fetchPolicy: "cache-and-network",
    nextFetchPolicy: "cache-first",
  });

  const clips = useMemo(() => {
    const rows = feedData?.pitchReelsFeed;
    if (rows && rows.length > 0) {
      return rows.map(mapPitchReelToShortClip);
    }
    return [];
  }, [feedData]);

  const clipTextById = useMemo(
    () =>
      new Map<string, ClipPlainText>(
        clips.map((clip: ShortClip) => [
          clip.id,
          {
            titlePlain: htmlToPlainText(clip.title),
            subtitlePlain: htmlToPlainText(clip.subtitle),
            thesisPlain: htmlToPlainText(clip.thesis),
            descriptionPlain: htmlToPlainText(clip.description),
          },
        ]),
      ),
    [clips],
  );

  const visibleClipRange = useMemo(
    () => ({
      start: Math.max(0, activeIndex - 1),
      end: Math.min(clips.length - 1, activeIndex + 1),
    }),
    [activeIndex, clips.length],
  );

  const hasProcessingReels = clips
    .slice(visibleClipRange.start, visibleClipRange.end + 1)
    .some(
      (clip: ShortClip) =>
        clip.videoStatus === "pending" || clip.videoStatus === "processing",
    );
  const initialFeedLoading =
    clips.length === 0 && feedLoading && !feedError && !feedLoadStalled;

  useEffect(() => {
    if (hasProcessingReels) {
      startPolling(8000);
    } else {
      stopPolling();
    }
    return () => stopPolling();
  }, [hasProcessingReels, startPolling, stopPolling]);

  useEffect(() => {
    if (!feedLoading || clips.length > 0) {
      setFeedLoadStalled(false);
      return;
    }

    const timeout = window.setTimeout(() => {
      setFeedLoadStalled(true);
    }, 10000);

    return () => window.clearTimeout(timeout);
  }, [clips.length, feedLoading]);

  const commentsForOpenClip = openCommentsClipId
    ? state.commentsByClipId[openCommentsClipId] || []
    : [];

  const investTargetClip = useMemo(
    () =>
      openInvestClipId
        ? clips.find((c: ShortClip) => c.id === openInvestClipId)
        : undefined,
    [clips, openInvestClipId],
  );

  const showFeedback = useCallback((message: string) => {
    setFeedbackMessage(message);
    window.setTimeout(() => {
      setFeedbackMessage((current) => (current === message ? null : current));
    }, 2200);
  }, []);

  const scrollToClip = useCallback(
    (index: number) => {
      const boundedIndex = Math.max(0, Math.min(index, clips.length - 1));
      const container = containerRef.current;
      const slide = slideRefs.current[boundedIndex];
      if (container && slide) {
        container.scrollTo({
          top: slide.offsetTop - container.offsetTop,
          behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)")
            ?.matches
            ? "auto"
            : "smooth",
        });
      }
    },
    [clips.length],
  );

  useEffect(() => {
    setActiveIndex((i) => Math.min(i, Math.max(0, clips.length - 1)));
  }, [clips.length]);

  useEffect(() => {
    if (feedLimit >= MAX_FEED_LIMIT) {
      return;
    }
    if (clips.length < feedLimit) {
      return;
    }
    if (activeIndex < Math.max(0, clips.length - 3)) {
      return;
    }
    setFeedLimit((current) =>
      Math.min(MAX_FEED_LIMIT, current + FEED_PAGE_SIZE),
    );
  }, [activeIndex, clips.length, feedLimit]);

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined" || !containerRef.current) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const mostVisibleEntry = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];

        if (!mostVisibleEntry) {
          return;
        }

        const nextIndex = Number(
          (mostVisibleEntry.target as HTMLElement).dataset.index || 0,
        );
        setActiveIndex(nextIndex);
      },
      {
        root: containerRef.current,
        threshold: [0.45, 0.7, 0.92],
      },
    );

    slideRefs.current.forEach((slide) => {
      if (slide) {
        observer.observe(slide);
      }
    });

    return () => observer.disconnect();
  }, [clips.length]);

  useEffect(() => {
    videoRefs.current.forEach((video, index) => {
      if (!video) {
        return;
      }

      video.muted = state.muted;
      if (index === activeIndex) {
        const playResult = video.play();
        if (playResult && typeof playResult.catch === "function") {
          playResult.catch((error: unknown) =>
            logger.log("video play blocked", error),
          );
        }
      } else {
        video.pause();
      }
    });
  }, [activeIndex, state.muted]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (openInvestClipId) {
        if (event.key === "Escape") {
          setOpenInvestClipId(null);
        }
        return;
      }

      if (openCommentsClipId) {
        if (event.key === "Escape") {
          setOpenCommentsClipId(null);
        }
        return;
      }

      if (
        event.target instanceof HTMLElement &&
        event.target.closest(
          'input, textarea, select, [contenteditable="true"]',
        )
      )
        return;

      if (event.key === "ArrowDown" || event.key.toLowerCase() === "j") {
        event.preventDefault();
        scrollToClip(activeIndex + 1);
      }

      if (event.key === "ArrowUp" || event.key.toLowerCase() === "k") {
        event.preventDefault();
        scrollToClip(activeIndex - 1);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeIndex, openCommentsClipId, openInvestClipId, scrollToClip]);

  const handleShare = useCallback(
    async (clipId: string) => {
      const clip = clips.find((item: ShortClip) => item.id === clipId);
      if (!clip) {
        return;
      }

      const text = clipTextById.get(clip.id);

      const payload = {
        title: text?.titlePlain || htmlToPlainText(clip.title),
        text: text?.subtitlePlain || htmlToPlainText(clip.subtitle),
        // #25: share the canonical /pitch-reels URL. /shorts still redirects.
        url: `${window.location.origin}/pitch-reels?clip=${clip.id}`,
      };

      try {
        if (navigator.share) {
          await navigator.share(payload);
          showFeedback("Share sheet opened.");
          return;
        }

        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(payload.url);
          showFeedback("Link copied.");
          return;
        }

        showFeedback("Sharing is not available here.");
      } catch (error) {
        logger.log("share failed", error);
        showFeedback("Unable to share right now.");
      }
    },
    [clipTextById, clips, showFeedback],
  );

  const handleOpenWorkspace = useCallback(
    (workspacePath: string) => {
      navigate(workspacePath);
    },
    [navigate],
  );

  const handleSubmitComment = useCallback(() => {
    if (!openCommentsClipId) {
      return;
    }

    const result = addComment(openCommentsClipId, commentDraft);
    if (!result) {
      return;
    }

    setCommentDraft("");
    showFeedback("Comment added.");
  }, [addComment, commentDraft, openCommentsClipId, showFeedback]);

  useEffect(() => {
    return subscribeToVoiceShortsCommand(({ action, body }) => {
      const activeClip = clips[activeIndex];
      if (!activeClip) {
        return;
      }

      if (action === "next") {
        scrollToClip(activeIndex + 1);
        return;
      }

      if (action === "previous") {
        scrollToClip(activeIndex - 1);
        return;
      }

      if (action === "toggle_like") {
        toggleLike(activeClip.id);
        showFeedback(
          likedClipIds.has(activeClip.id) ? "Removed like." : "Liked reel.",
        );
        return;
      }

      if (action === "toggle_save") {
        toggleSave(activeClip.id);
        showFeedback(
          savedClipIds.has(activeClip.id)
            ? "Removed from saved."
            : "Saved reel.",
        );
        return;
      }

      if (action === "toggle_follow") {
        toggleFollow(activeClip.creatorId);
        showFeedback(
          followedCreatorIds.has(activeClip.creatorId)
            ? `Unfollowed ${activeClip.creatorName}.`
            : `Following ${activeClip.creatorName}.`,
        );
        return;
      }

      if (action === "open_comments") {
        setOpenInvestClipId(null);
        setOpenCommentsClipId(activeClip.id);
        return;
      }

      if (action === "open_invest") {
        setOpenCommentsClipId(null);
        if (activeClip.ideaId && activeClip.creatorId !== viewerUserId) {
          setOpenInvestClipId(activeClip.id);
          return;
        }
        showFeedback(
          activeClip.ideaId
            ? "You can't invest in your own reel."
            : "Invest isn't available for this reel.",
        );
        return;
      }

      if (action === "close_comments") {
        setOpenCommentsClipId(null);
        return;
      }

      if (action === "share") {
        void handleShare(activeClip.id);
        return;
      }

      if (action === "open_workspace") {
        handleOpenWorkspace(activeClip.workspacePath);
        return;
      }

      if (action === "mute") {
        setMuted(true);
        return;
      }

      if (action === "unmute") {
        setMuted(false);
        return;
      }

      if (action === "comment") {
        setOpenCommentsClipId(activeClip.id);
        if (body?.trim()) {
          const result = addComment(activeClip.id, body);
          if (result) {
            showFeedback("Comment added.");
          }
        }
      }
    });
  }, [
    activeIndex,
    addComment,
    clips,
    followedCreatorIds,
    handleOpenWorkspace,
    handleShare,
    likedClipIds,
    savedClipIds,
    scrollToClip,
    setMuted,
    showFeedback,
    toggleFollow,
    toggleLike,
    toggleSave,
    viewerUserId,
  ]);

  return (
    <div className="manifest-reels" data-testid="shorts-page">
      <header className="manifest-reels-header">
        <div className="flex items-center gap-3">
          <h1>Pitch Reels</h1>
          {clips.length > 0 && (
            <span className="manifest-reels-count">
              {activeIndex + 1} / {clips.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            className="h-11 w-11 p-0"
            aria-label="Previous reel"
            disabled={activeIndex === 0}
            onClick={() => scrollToClip(activeIndex - 1)}
          >
            <span className="rotate-180">
              <ArrowIcon />
            </span>
          </Button>
          <Button
            variant="ghost"
            className="h-11 w-11 p-0"
            aria-label="Next reel"
            disabled={activeIndex >= clips.length - 1}
            onClick={() => scrollToClip(activeIndex + 1)}
          >
            <ArrowIcon />
          </Button>
        </div>
      </header>
      {feedbackMessage && (
        <div
          role="status"
          className="manifest-reels-feedback"
          data-testid="shorts-feedback"
        >
          {feedbackMessage}
        </div>
      )}
      <div ref={containerRef} className="manifest-reels-scroll">
        {initialFeedLoading && (
          <div role="status" className="manifest-reels-empty">
            <p>Loading pitch reels…</p>
          </div>
        )}
        {clips.length === 0 && (feedError || feedLoadStalled) && (
          <div role="alert" className="manifest-reels-empty">
            <p>
              {feedError
                ? "We couldn't load pitch reels"
                : "Pitch reels are taking longer than expected"}
            </p>
            <Button
              variant="secondary"
              onClick={() => {
                setFeedLoadStalled(false);
                void refetch();
              }}
            >
              Retry
            </Button>
          </div>
        )}
        {clips.length === 0 && !feedLoading && !feedError && (
          <div className="manifest-reels-empty">
            <h2>No pitch reels yet</h2>
            <p>Published ideas will appear here.</p>
            <Button variant="secondary" onClick={() => navigate("/ideas")}>
              Your ideas
            </Button>
          </div>
        )}
        {clips.map((clip: ShortClip, index: number) => {
          const isLiked = likedClipIds.has(clip.id);
          const isSaved = savedClipIds.has(clip.id);
          const isFollowed = followedCreatorIds.has(clip.creatorId);
          const commentCount =
            clip.commentCount + (state.commentsByClipId[clip.id]?.length || 0);
          const {
            titlePlain = "",
            subtitlePlain = "",
            thesisPlain = "",
            descriptionPlain = "",
          } = clipTextById.get(clip.id) || {};
          const summary = subtitlePlain || thesisPlain || descriptionPlain;
          const detail = [thesisPlain, descriptionPlain].find(
            (text) => text && text !== summary && text !== titlePlain,
          );
          const hasVideo = Boolean(clip.src) && !videoErrors[clip.id];
          const processing =
            clip.videoStatus === "pending" || clip.videoStatus === "processing";
          return (
            <section
              key={clip.id}
              ref={(element) => {
                slideRefs.current[index] = element;
              }}
              data-index={index}
              className="manifest-reel"
              data-testid={`short-clip-${clip.id}`}
            >
              <article className="manifest-reel-content">
                <div
                  className={`manifest-reel-media ${hasVideo ? "" : "manifest-reel-media-empty"}`}
                >
                  {hasVideo ? (
                    <>
                      <PitchReelVideo
                        ref={(element) => {
                          videoRefs.current[index] = element;
                        }}
                        src={index === activeIndex ? clip.src : undefined}
                        onError={() =>
                          setVideoErrors((current) => ({
                            ...current,
                            [clip.id]: true,
                          }))
                        }
                        className="h-full w-full object-contain"
                        loop
                        autoPlay={index === activeIndex}
                        muted={state.muted}
                        playsInline
                        controls
                        preload={index === activeIndex ? "auto" : "none"}
                        aria-label={`Pitch video for ${titlePlain}`}
                        data-testid={`short-video-${clip.id}`}
                      />
                      <button
                        type="button"
                        onClick={() => setMuted(!state.muted)}
                        className="manifest-reel-sound"
                        aria-label={state.muted ? "Enable sound" : "Mute sound"}
                      >
                        <VolumeIcon muted={state.muted} />
                      </button>
                    </>
                  ) : (
                    <div className="manifest-reel-video-note">
                      <span aria-hidden="true">▶</span>
                      <p>
                        {processing
                          ? "Video is being prepared"
                          : "No video available yet"}
                      </p>
                    </div>
                  )}
                </div>
                <div className="manifest-reel-details">
                  <div className="manifest-reel-creator">
                    <span className="manifest-reel-avatar">
                      {clip.creatorInitials}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p>{clip.creatorName}</p>
                      <span>{clip.creatorRole}</span>
                    </div>
                    {clip.creatorId !== viewerUserId && (
                      <Button
                        variant="ghost"
                        onClick={() => toggleFollow(clip.creatorId)}
                        data-testid={`short-follow-${clip.id}`}
                        aria-label={`${isFollowed ? "Unfollow" : "Follow"} ${clip.creatorName}`}
                      >
                        {isFollowed ? "Following" : "Follow"}
                      </Button>
                    )}
                  </div>
                  <h2>{titlePlain}</h2>
                  {summary && summary !== titlePlain && (
                    <p className="manifest-reel-summary">{summary}</p>
                  )}
                  {detail && (
                    <p className="manifest-reel-description">{detail}</p>
                  )}
                  {clip.tags.length > 0 && (
                    <div className="manifest-reel-tags">
                      {clip.tags.map((tag) => (
                        <span key={tag}>{tag}</span>
                      ))}
                    </div>
                  )}
                  <div className="manifest-reel-actions">
                    <ActionButton
                      icon={<HeartIcon active={isLiked} />}
                      ariaLabel={`${isLiked ? "Unlike" : "Like"} ${titlePlain}`}
                      count={clip.likeCount + (isLiked ? 1 : 0)}
                      onClick={() => toggleLike(clip.id)}
                      active={isLiked}
                      testId={`short-like-${clip.id}`}
                    />
                    <ActionButton
                      icon={<CommentIcon />}
                      ariaLabel={`Comment on ${titlePlain}`}
                      count={commentCount}
                      onClick={() => {
                        setOpenInvestClipId(null);
                        setOpenCommentsClipId(clip.id);
                      }}
                      testId={`short-comment-${clip.id}`}
                    />
                    <ActionButton
                      icon={<SaveIcon active={isSaved} />}
                      ariaLabel={`${isSaved ? "Unsave" : "Save"} ${titlePlain}`}
                      count={clip.saveCount + (isSaved ? 1 : 0)}
                      onClick={() => toggleSave(clip.id)}
                      active={isSaved}
                      testId={`short-save-${clip.id}`}
                    />
                    <ActionButton
                      icon={<ShareIcon />}
                      ariaLabel={`Share ${titlePlain}`}
                      caption="Share"
                      onClick={() => void handleShare(clip.id)}
                      testId={`short-share-${clip.id}`}
                    />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="secondary"
                      onClick={() => handleOpenWorkspace(clip.workspacePath)}
                      aria-label={`Open workspace for ${titlePlain}`}
                    >
                      Open idea <ArrowIcon />
                    </Button>
                    {clip.ideaId && clip.creatorId !== viewerUserId && (
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setOpenCommentsClipId(null);
                          setOpenInvestClipId(clip.id);
                        }}
                        aria-label={`Invest in ${titlePlain}`}
                        data-testid={`short-invest-${clip.id}`}
                      >
                        Invest
                      </Button>
                    )}
                  </div>
                </div>
              </article>
            </section>
          );
        })}
      </div>

      {openCommentsClipId ? (
        <div
          className="manifest-reels-overlay"
          data-testid="short-comments-overlay"
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Comments"
            className="manifest-reels-comments"
            data-testid="short-comments-modal"
          >
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <p className="text-sm">Comments</p>
                <h2 className="mt-1 text-xl font-semibold">
                  {htmlToPlainText(
                    clips.find((c: ShortClip) => c.id === openCommentsClipId)
                      ?.title,
                  )}
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setOpenCommentsClipId(null)}
                className="flex h-11 w-11 items-center justify-center rounded-md"
                aria-label="Close comments"
                data-testid="short-comments-close"
              >
                <CloseIcon />
              </button>
            </div>

            <div className="max-h-[42vh] space-y-3 overflow-y-auto pr-1">
              {commentsForOpenClip.length ? (
                commentsForOpenClip.map((comment) => (
                  <div key={comment.id} className="manifest-reels-comment">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold">{comment.author}</p>
                      <span className="text-xs font-medium text-gray500">
                        {timeAgoLabel(comment.createdAt)}
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-7 text-gray500">
                      {comment.body}
                    </p>
                  </div>
                ))
              ) : (
                <div className="py-8 text-center">
                  <p className="text-lg font-semibold">No comments yet</p>
                  <p className="mt-2 text-sm leading-7 text-gray500">
                    Start the conversation.
                  </p>
                </div>
              )}
            </div>

            <div className="mt-4 flex gap-3">
              <textarea
                value={commentDraft}
                onChange={(event) => setCommentDraft(event.target.value)}
                className="manifest-reels-comment-input"
                aria-label="Comment"
                placeholder="Add a comment…"
                data-testid="short-comments-input"
              />
              <button
                type="button"
                onClick={handleSubmitComment}
                className="manifest-reels-post"
                data-testid="short-comments-submit"
              >
                Post
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {investTargetClip?.ideaId ? (
        <Suspense
          fallback={
            <div role="status" className="manifest-reels-feedback">
              Opening investment…
            </div>
          }
        >
          <InvestmentModal
            ideaId={investTargetClip.ideaId}
            ideaTitle={htmlToPlainText(investTargetClip.title)}
            isOpen
            tone="light"
            onClose={() => setOpenInvestClipId(null)}
            onSuccess={() => showFeedback("Investment submitted.")}
          />
        </Suspense>
      ) : null}
    </div>
  );
};

export default PitchReelsPage;
