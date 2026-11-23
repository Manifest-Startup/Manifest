/**
 * Result and variable shapes for the GraphQL operations in `./queries.ts`.
 *
 * Each shape mirrors the fields the matching gql document selects, so the
 * documents can be exported as `TypedDocumentNode`s and Apollo hooks infer
 * `data` / `variables` without per-call-site generics. Keep a shape in sync
 * when you change the selection set of its document.
 */
import type { GuestSessionPayload } from "features/auth/guestSessionBootstrap";
import type { PitchReelFeedRow } from "features/pitch-reels/mapPitchReelToShortClip";

// ------------------------------ Ideas ------------------------------------

/** `IdeaFields` fragment. */
export interface IdeaRecord {
  ideaId: string;
  title: string;
  description: string | null;
  pitchDeck: string | null;
  productRequirementsDocument: string | null;
  provisionalPatent: string | null;
  businessModelCanvas: string | null;
  similarIdeas: string | null;
  isPublished: boolean;
  requiredSkills: string[] | null;
}

/** `IdeaCoreFields` fragment. */
export interface IdeaCore {
  ideaId: string;
  userId: string;
  title: string;
  description: string | null;
  isPublished: boolean;
}

/** `IdeaSummaryFields` fragment (workspace list). */
export interface IdeaSummary {
  ideaId: string;
  userId: string;
  title: string;
  hasDescription: boolean;
  createdAt: string;
  isPublished: boolean;
  generatedAssetCount: number | null;
}

export interface IdeaIdVariables {
  ideaId: string;
}

export interface GetIdeasData {
  ideas: IdeaSummary[];
}

export interface GetIdeaData {
  idea: IdeaRecord | null;
}

export interface GetIdeaCoreData {
  idea: IdeaCore | null;
}

export interface CreateIdeaData {
  createIdea: {
    ideaId: string;
    title: string;
    description: string | null;
  } | null;
}

export interface CreateIdeaVariables {
  title: string;
  description?: string | null;
}

export interface UpdateIdeaData {
  updateIdea: IdeaRecord | null;
}

export interface UpdateIdeaVariables {
  ideaId: string;
  title?: string | null;
  description?: string | null;
  requiredSkills?: string[] | null;
}

export interface DeleteIdeaData {
  deleteIdea: boolean;
}

export interface TogglePublishIdeaData {
  togglePublishIdea: {
    ideaId: string;
    isPublished: boolean;
  } | null;
}

export interface FindSimilarIdeasData {
  findSimilarIdeas: {
    similarIdeas: string;
  };
}

export interface FindSimilarIdeasVariables {
  ideaDescription: string;
}

export interface ExportIdeasData {
  exportIdeas: {
    content: string;
    format: string;
    filename: string;
  } | null;
}

export interface ExportIdeasVariables {
  format: string;
}

export interface ImportIdeasData {
  importIdeas: {
    importedCount: number;
    skippedCount: number;
    errors: string[];
  } | null;
}

export interface ImportIdeasVariables {
  fileContent: string;
  fileFormat: string;
  filename: string;
}

// ------------------------------ Auth -------------------------------------

export interface MessageResult {
  success: boolean;
  message: string;
}

export interface StartGuestSessionData {
  startGuestSession: GuestSessionPayload | null;
}

// ----------------------------- Account -----------------------------------

/** Selection shared by `account` and `updateAccount`. */
export interface AccountProfile {
  userId: string;
  email: string;
  username: string | null;
  firstName: string | null;
  lastName: string | null;
  country: string | null;
  bio: string | null;
  address: string | null;
  state: string | null;
  gravatarHash: string | null;
  profilePictureUrl: string | null;
  skills: string[] | null;
}

export interface UpdateAccountData {
  updateAccount: AccountProfile | null;
}

export interface UpdateAccountVariables {
  input: {
    firstName?: string | null;
    lastName?: string | null;
    email?: string | null;
    username?: string | null;
    country?: string | null;
    bio?: string | null;
    address?: string | null;
    state?: string | null;
    gravatarHash?: string | null;
    profilePictureUrl?: string | null;
    skills?: string[] | null;
  };
}

export interface IntegrationRecord {
  integrationId: string;
  userId: string;
  serviceName: string;
  serviceId: string;
  connectedAt: string;
  metadata: string | null;
  /** The partner's own sign-in completed (Manifest holds credentials). */
  linked?: boolean;
}

export interface StartIntegrationConnectionData {
  startIntegrationConnection: {
    serviceId: string;
    status: 'connected' | 'already_connected' | 'needs_browser';
    message: string;
    connectUrl: string | null;
  };
}

export interface StartIntegrationConnectionVars {
  serviceId: string;
  name?: string | null;
}

export interface GetIntegrationsData {
  integrations: IntegrationRecord[];
}

export interface RevokeOtherAccountSessionsData {
  revokeOtherAccountSessions: number;
}

export interface SessionInfo {
  sessionId: string;
  current: boolean;
  createdAt?: string | null;
  expiresAt?: string | null;
  revokedAt?: string | null;
  lastSeenAt?: string | null;
  requestIp?: string | null;
  userAgent?: string | null;
  /** `browser`, or `cli` for a Manifest CLI session (its label is in `userAgent`). */
  kind?: string | null;
}

export interface GetMySessionsData {
  mySessions: SessionInfo[];
}

export interface PrivacyStatus {
  exportAvailable: boolean;
  deletionRequestedAt: string | null;
  guestRetentionDays: number;
}

export interface GetPrivacyStatusData {
  privacyStatus: PrivacyStatus | null;
}

// --------------------------- Investments ---------------------------------

export interface PortfolioItem {
  investmentId: string;
  ideaId: string;
  ideaTitle: string;
  ideaDescription: string | null;
  cashAmount: number;
  sweatEquityValue: number;
  equityPercentage: number;
  status: string;
  createdAt: string;
}

export interface GetMyPortfolioData {
  myPortfolio: PortfolioItem[];
}

export interface CalculateSweatEquityData {
  calculateSweatEquity: {
    sweatValue: number;
    equityPercentage: number;
    hours: number;
    hourlyRate: number;
  } | null;
}

export interface CalculateSweatEquityVariables {
  hours: number;
  hourlyRate?: number | null;
  totalValuation?: number | null;
}

// ----------------------------- Social ------------------------------------

export interface ToggleFollowData {
  toggleFollow: {
    following: boolean;
    followedId: string;
  } | null;
}

export interface ToggleFollowVariables {
  followedId: string;
}

export interface ToggleUpvoteData {
  toggleUpvote: {
    voted: boolean;
    ideaId: string;
    voteCount: number;
  } | null;
}

export interface GetPitchReelsFeedData {
  pitchReelsFeed: PitchReelFeedRow[];
}

export interface GetPitchReelsFeedVariables {
  limit?: number | null;
}

// ---------------------------- Messaging ----------------------------------
// Messages live in Open Media; conversation, message and other-user ids are Open Media ids.

export interface Conversation {
  conversationId: string;
  otherUserId: string;
  otherUserName: string;
  otherUserHandle?: string | null;
  otherUserAvatar?: string | null;
  ideaId?: string | null;
  ideaTitle?: string | null;
  lastMessageAt: string;
  lastMessagePreview?: string | null;
  unreadCount: number;
}

export interface InboxConversation {
  conversationId: string;
  kind: "chat" | "email" | "bridged" | string;
  source: string;
  title: string;
  initials: string;
  avatarColor?: string | null;
  avatarUrl?: string | null;
  group: boolean;
  company?: string | null;
  preview?: string | null;
  lastMessageAt: string;
  unreadCount: number;
  ideaId?: string | null;
  ideaTitle?: string | null;
  canReply: boolean;
}

export interface InboxTextSegment {
  text: string;
  url?: string | null;
}

export interface InboxItem {
  kind: "time" | "message" | string;
  key: string;
  at?: string | null;
  messageId?: string | null;
  isMine: boolean;
  senderName?: string | null;
  sentAt?: string | null;
  source?: string | null;
  subject?: string | null;
  body: InboxTextSegment[];
  attachmentCount: number;
  quotedHistoryHidden: boolean;
  groupStart: boolean;
  groupEnd: boolean;
}

export interface GetMyInboxData {
  myInbox: InboxConversation[];
}

export interface GetMyInboxVariables {
  limit?: number | null;
}

export interface GetInboxConversationData {
  inboxConversation: { conversation: InboxConversation; items: InboxItem[] };
}

export interface GetInboxConversationVariables {
  conversationId: string;
}

export interface ReplyInInboxData {
  replyInInbox: boolean;
}

export interface ReplyInInboxVariables {
  conversationId: string;
  content: string;
  replyToMessageId?: string | null;
  clientId?: string | null;
}

/** Goals that run (ADR 0020): steps, approvals waiting for the person, and a progress report. */
export interface GoalApproval {
  id: string;
  goalId: string;
  summary: string;
  consequences: string;
  riskTier: number;
  scopeSha256: string;
  status: string;
}

export interface GoalReport {
  completed: string[];
  inProgress: string[];
  waiting: string[];
  needsYou: string[];
  next: string[];
}

export interface GoalSummary {
  id: string;
  title: string;
  status: string;
  approvals: GoalApproval[];
  report: GoalReport | null;
}

export interface GetGoalsData {
  goals: GoalSummary[];
}

export interface DecideApprovalVariables {
  approvalId: string;
  approve: boolean;
  scopeSha256: string;
}

export interface DecideApprovalData {
  decideApproval: GoalSummary;
}

export interface MarkInboxReadData {
  markInboxRead: boolean;
}

export interface MarkConversationReadVariables {
  conversationId: string;
}

export interface GetUnreadMessageCountData {
  unreadMessageCount: {
    count: number;
  } | null;
}

export interface IdeaOwner {
  userId: string;
  username: string | null;
  firstName: string | null;
  lastName: string | null;
  bio: string | null;
  profilePictureUrl: string | null;
  ideaId: string;
  ideaTitle: string | null;
  isPublished: boolean;
  canMessage: boolean;
  /** Founder's Open Media handle; null until they link Open Media. */
  openMediaHandle: string | null;
}

export interface GetIdeaOwnerData {
  ideaOwner: IdeaOwner | null;
}

export interface StartConversationData {
  startConversation: Conversation | null;
}

export interface StartConversationVariables {
  otherUserId: string;
  ideaId?: string | null;
}

// ---------------------------- Open Media ---------------------------------

export interface OpenMediaLinkStatus {
  enabled: boolean;
  linked: boolean;
  needsReconnect: boolean;
  handle: string | null;
  displayName: string | null;
  connectUrl: string;
}

export interface GetOpenMediaLinkData {
  openMediaLink: OpenMediaLinkStatus | null;
}

export interface GetOpenMediaRealtimeTokenData {
  openMediaRealtimeToken: {
    supabaseUrl: string;
    anonKey: string;
    accessToken: string;
    expiresAt: string | null;
    omUserId: string | null;
  } | null;
}

// ---------------------------- Pitch reels --------------------------------

export interface PitchReelCommentRow {
  commentId: string;
  reelId: string;
  authorId: string;
  authorName: string;
  authorHandle?: string | null;
  authorAvatar?: string | null;
  body: string;
  createdAt: string;
  isMine: boolean;
}

export interface GetPitchReelCommentsData {
  pitchReelComments: PitchReelCommentRow[];
}

export interface GetPitchReelCommentsVariables {
  reelId: string;
  limit?: number | null;
}

export interface TogglePitchReelLikeData {
  togglePitchReelLike: { reelId: string; liked: boolean; likeCount: number | null } | null;
}

export interface TogglePitchReelLikeVariables {
  reelId: string;
  liked: boolean;
}

export interface ResharePitchReelData {
  resharePitchReel: { reelId: string; reshared: boolean; shareCount: number | null } | null;
}

export interface ResharePitchReelVariables {
  reelId: string;
  reshared: boolean;
}

export interface CreatePitchReelCommentData {
  createPitchReelComment: { comment: PitchReelCommentRow } | null;
}

export interface CreatePitchReelCommentVariables {
  reelId: string;
  body: string;
}

// -------------------------- Collaboration --------------------------------

export interface Collaborator {
  collaboratorId: string | null;
  ideaId: string;
  userId: string;
  role: string;
  status: string;
  userEmail: string | null;
  userName: string | null;
  userAvatar: string | null;
}

export interface GetIdeaCollaboratorsData {
  ideaCollaborators: Collaborator[];
}

export interface CollaborationInvitation {
  collaboratorId: string;
  ideaId: string;
  role: string;
  status: string;
  ideaTitle: string | null;
  ideaDescription: string | null;
  inviterName: string | null;
  invitedAt: string | null;
}

export interface GetMyCollaborationInvitationsData {
  myCollaborationInvitations: CollaborationInvitation[];
}

export interface IdeaVersion {
  versionId: string;
  ideaId: string;
  versionNumber: number;
  title: string | null;
  description: string | null;
  createdBy: string;
  createdAt: string;
  changeSummary: string | null;
  creatorName: string | null;
  creatorAvatar: string | null;
  versionKind?: string | null;
}

export interface GetIdeaVersionsData {
  ideaVersions: IdeaVersion[];
}

export interface InviteCollaboratorVariables {
  input: {
    ideaId: string;
    email: string;
    role: string;
  };
}

export interface InviteCollaboratorData {
  inviteCollaborator: MessageResult | null;
}

// --------------------------- Bring your own key --------------------------
/** `source`: "user" (customer's own key), "platform" (operator fallback) or "none". */
export interface AiKeyStatus {
  configured: boolean;
  source: "user" | "platform" | "none";
  last4: string | null;
}

export interface GetAiKeyStatusData {
  aiKeyStatus: AiKeyStatus;
}

export interface SaveOpenaiApiKeyData {
  saveOpenaiApiKey: AiKeyStatus;
}

export interface SaveOpenaiApiKeyVariables {
  apiKey: string;
}

export interface RemoveOpenaiApiKeyData {
  removeOpenaiApiKey: AiKeyStatus;
}

export interface ApolloKeyStatus {
  connected: boolean;
  last4?: string | null;
}

export interface GetApolloKeyStatusData {
  apolloKeyStatus: ApolloKeyStatus;
}

export interface SaveApolloApiKeyData {
  saveApolloApiKey: ApolloKeyStatus;
}

export interface SaveApolloApiKeyVariables {
  apiKey: string;
}

export interface RemoveApolloApiKeyData {
  removeApolloApiKey: ApolloKeyStatus;
}

// --------------------------- Memory (ADR 0021) ---------------------------
/** One lasting fact, kept as a Markdown file in the person's vault (Memory/…). */
export interface MemoryItem {
  id: string;
  text: string;
  kind: string;
  ideaId: string | null;
  ideaTitle: string | null;
  source: string | null;
  conversation: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  path: string;
}

export interface RecallData {
  recall: MemoryItem[];
}

export interface RecallVariables {
  query?: string;
  ideaId?: string | null;
  limit?: number;
}

export interface GetMemoriesData {
  memories: MemoryItem[];
}

export interface UpdateMemoryData {
  updateMemory: MemoryItem;
}

export interface UpdateMemoryVariables {
  memoryId: string;
  text: string;
}

export interface ForgetMemoryData {
  forgetMemory: MemoryItem;
}

export interface ForgetMemoryVariables {
  memoryId: string;
}

export interface ConversationTurn {
  role: 'user' | 'assistant';
  text: string;
}

export interface SaveVoiceConversationData {
  saveVoiceConversation: { path: string | null; turns: number; memories: MemoryItem[] };
}

export interface SaveVoiceConversationVariables {
  turns: ConversationTurn[];
  ideaId?: string | null;
  startedAt?: string | null;
  agent?: string | null;
  extract?: boolean;
}
