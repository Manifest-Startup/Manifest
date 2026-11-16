export interface ShortClip {
  id: string;
  creatorId: string;
  creatorHandle: string;
  creatorName: string;
  creatorRole: string;
  creatorInitials: string;
  accentFrom: string;
  accentTo: string;
  title: string;
  subtitle: string;
  thesis: string;
  description: string;
  tags: string[];
  src: string;
  workspacePath: string;
  /** Open Media counts for the clip (shareCount = reshares). */
  likeCount: number;
  shareCount: number;
  commentCount: number;
  liked: boolean;
  reshared: boolean;
  creatorFollowing: boolean;
  posterUrl?: string;
  /** Linked idea for invest / workspace flows (empty if missing) */
  ideaId?: string;
  /** From API: ready | pending | processing | failed | needs_open_media */
  videoStatus?: string;
}
