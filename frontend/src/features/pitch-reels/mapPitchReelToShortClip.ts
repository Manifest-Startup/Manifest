import type { ShortClip } from "./types";

/** GraphQL `pitchReelsFeed` row (camelCase) */
export interface PitchReelFeedRow {
  reelId: string;
  slug: string;
  ideaId?: string | null;
  title: string;
  subtitle?: string | null;
  thesis?: string | null;
  description?: string | null;
  tags: string[];
  videoUrl: string;
  posterUrl?: string | null;
  videoStatus?: string | null;
  workspacePath: string;
  accentFrom: string;
  accentTo: string;
  createdAt: string;
  creator: {
    userId: string;
    handle?: string | null;
    name: string;
    role?: string | null;
    initials: string;
    avatar?: string | null;
    followerCount?: number;
    isFollowing?: boolean;
  };
  stats?: {
    likeCount?: number;
    commentCount?: number;
    shareCount?: number;
  };
  viewerState?: {
    liked?: boolean;
    reshared?: boolean;
  };
}

const VIDEO_STATUSES = new Set(["pending", "processing", "failed", "ready", "needs_open_media"]);

export function mapPitchReelToShortClip(reel: PitchReelFeedRow): ShortClip {
  const v = (reel.videoStatus || "ready").toLowerCase();
  const videoStatus = VIDEO_STATUSES.has(v) ? v : "ready";

  const ideaIdRaw = reel.ideaId != null ? String(reel.ideaId).trim() : "";
  const creator = reel.creator ?? ({} as PitchReelFeedRow["creator"]);
  const stats = reel.stats ?? {};
  const viewer = reel.viewerState ?? {};

  return {
    id: reel.reelId,
    ideaId: ideaIdRaw || undefined,
    creatorId: creator.userId ?? "",
    creatorHandle: creator.handle || "",
    creatorName: creator.name ?? "Manifest founder",
    creatorRole: creator.role || "Founder",
    creatorInitials: creator.initials || "M",
    accentFrom: reel.accentFrom,
    accentTo: reel.accentTo,
    title: reel.title,
    subtitle: reel.subtitle || "",
    thesis: reel.thesis || "",
    description: reel.description || "",
    tags: reel.tags || [],
    src: reel.videoUrl,
    posterUrl: reel.posterUrl || undefined,
    workspacePath: reel.workspacePath || "/ideas",
    likeCount: Number(stats.likeCount ?? 0),
    shareCount: Number(stats.shareCount ?? 0),
    commentCount: Number(stats.commentCount ?? 0),
    liked: Boolean(viewer.liked),
    reshared: Boolean(viewer.reshared),
    creatorFollowing: Boolean(creator.isFollowing),
    videoStatus,
  };
}
