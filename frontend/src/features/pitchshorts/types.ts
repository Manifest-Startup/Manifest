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
  likeCount: number;
  shareCount: number;
  saveCount: number;
  commentCount: number;
  /** Linked idea for invest / workspace flows (empty if missing) */
  ideaId?: string;
  /** From API: ready | pending | processing | failed */
  videoStatus?: string;
}

export interface ShortComment {
  id: string;
  clipId: string;
  author: string;
  body: string;
  createdAt: string;
}

export interface PersistentShortsState {
  muted: boolean;
  likedClipIds: string[];
  savedClipIds: string[];
  followedCreatorIds: string[];
  commentsByClipId: Record<string, ShortComment[]>;
}
