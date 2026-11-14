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

/** Payload returned by login, signup, password reset and guest upgrade. */
export interface AuthPayload {
  userId: string;
  email: string;
  token: string;
  isGuest: boolean;
}

export interface EmailPasswordVariables {
  email: string;
  password: string;
}

export interface LoginUserData {
  loginUser: AuthPayload | null;
}

export interface SignupUserData {
  signupUser: AuthPayload | null;
}

export interface MessageResult {
  success: boolean;
  message: string;
}

export interface RequestPasswordResetData {
  requestPasswordReset: MessageResult | null;
}

export interface RequestPasswordResetVariables {
  email: string;
}

export interface ResetPasswordData {
  resetPassword: AuthPayload | null;
}

export interface ResetPasswordVariables {
  token: string;
  newPassword: string;
}

export interface StartGuestSessionData {
  startGuestSession: GuestSessionPayload | null;
}

export interface MergeGuestWorkspaceData {
  mergeGuestWorkspace: {
    mergedIdeaCount: number;
  } | null;
}

export interface MergeGuestWorkspaceVariables {
  guestUserId: string;
  mergeSecret: string;
}

export interface CompleteGuestAccountUpgradeData {
  completeGuestAccountUpgrade: AuthPayload | null;
}

export interface CompleteGuestAccountUpgradeVariables {
  token: string;
  password: string;
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
}

export interface GetIntegrationsData {
  integrations: IntegrationRecord[];
}

export interface TotpSetup {
  secret: string;
  otpAuthUrl: string;
  recoveryCodes: string[];
}

export interface BeginTotpSetupData {
  beginTotpSetup: TotpSetup | null;
}

export interface BeginTotpSetupVariables {
  password?: string | null;
}

export interface RevokeOtherAccountSessionsData {
  revokeOtherAccountSessions: number;
}

export interface MfaStatus {
  enabled: boolean;
  enabledAt: string | null;
  recoveryCodesRemaining: number;
}

export interface GetMfaStatusData {
  mfaStatus: MfaStatus | null;
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
}

export interface GetMySessionsData {
  mySessions: SessionInfo[];
}

export interface PrivacyStatus {
  exportAvailable: boolean;
  deletionRequestedAt: string | null;
  guestRetentionDays: number;
  passwordResetRetentionMinutes: number;
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

export interface Conversation {
  conversationId: string;
  otherUserId: string;
  otherUserName: string;
  otherUserAvatar?: string;
  ideaId?: string;
  ideaTitle?: string;
  lastMessageAt: string;
  lastMessagePreview?: string;
  unreadCount: number;
}

export interface GetMyConversationsData {
  myConversations: Conversation[];
}

export interface GetMyConversationsVariables {
  limit?: number | null;
  offset?: number | null;
}

export interface ChatMessage {
  messageId: string;
  content: string;
  isMine: boolean;
  createdAt: string;
  senderName?: string;
  senderAvatar?: string;
}

export interface GetConversationMessagesData {
  conversationMessages: ChatMessage[];
}

export interface GetConversationMessagesVariables {
  conversationId: string;
  limit?: number | null;
  beforeId?: string | null;
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
  email: string | null;
  bio: string | null;
  profilePictureUrl: string | null;
  ideaId: string;
  ideaTitle: string | null;
  isPublished: boolean;
  canMessage: boolean;
}

export interface GetIdeaOwnerData {
  ideaOwner: IdeaOwner | null;
}

export interface StartConversationData {
  startConversation: {
    conversationId: string;
    otherUserId: string;
    otherUserName: string;
    otherUserAvatar: string | null;
    ideaId: string | null;
    lastMessageAt: string;
    unreadCount: number;
  } | null;
}

export interface StartConversationVariables {
  otherUserId: string;
  ideaId?: string | null;
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
