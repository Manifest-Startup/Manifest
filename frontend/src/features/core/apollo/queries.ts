import { gql } from '@apollo/client';
import type { TypedDocumentNode } from '@apollo/client';

import type {
  GetAiKeyStatusData,
  RemoveOpenaiApiKeyData,
  SaveOpenaiApiKeyData,
  SaveOpenaiApiKeyVariables,
  CalculateSweatEquityData,
  CalculateSweatEquityVariables,
  CreateIdeaData,
  CreateIdeaVariables,
  DeleteIdeaData,
  ExportIdeasData,
  ExportIdeasVariables,
  FindSimilarIdeasData,
  FindSimilarIdeasVariables,
  CreatePitchReelCommentData,
  CreatePitchReelCommentVariables,
  GetIdeaCollaboratorsData,
  GetIdeaCoreData,
  GetIdeaData,
  GetIdeaOwnerData,
  GetIdeaVersionsData,
  GetIdeasData,
  GetIntegrationsData,
  StartIntegrationConnectionData,
  StartIntegrationConnectionVars,
  GetMyCollaborationInvitationsData,
  GetMyInboxData,
  GetMyInboxVariables,
  GetInboxConversationData,
  GetInboxConversationVariables,
  ReplyInInboxData,
  ReplyInInboxVariables,
  MarkInboxReadData,
  GetMyPortfolioData,
  GetMySessionsData,
  GetOpenMediaLinkData,
  GetOpenMediaRealtimeTokenData,
  GetPitchReelCommentsData,
  GetPitchReelCommentsVariables,
  GetPitchReelsFeedData,
  GetPitchReelsFeedVariables,
  GetPrivacyStatusData,
  GetUnreadMessageCountData,
  IdeaIdVariables,
  ImportIdeasData,
  ImportIdeasVariables,
  InviteCollaboratorData,
  InviteCollaboratorVariables,
  MarkConversationReadVariables,
  ResharePitchReelData,
  ResharePitchReelVariables,
  RevokeOtherAccountSessionsData,
  StartConversationData,
  StartConversationVariables,
  StartGuestSessionData,
  ToggleFollowData,
  ToggleFollowVariables,
  TogglePitchReelLikeData,
  TogglePitchReelLikeVariables,
  TogglePublishIdeaData,
  ToggleUpvoteData,
  UpdateAccountData,
  UpdateAccountVariables,
  UpdateIdeaData,
  UpdateIdeaVariables,
} from './operationTypes';

/** Variables type for operations that take no arguments. */
type NoVariables = Record<string, never>;

// Shared fragment for idea fields to avoid duplication
export const IDEA_FIELDS = gql`
  fragment IdeaFields on Idea {
    ideaId
    title
    description
    pitchDeck
    productRequirementsDocument
    provisionalPatent
    businessModelCanvas
    similarIdeas
    isPublished
    requiredSkills
  }
`;

export const IDEA_CORE_FIELDS = gql`
  fragment IdeaCoreFields on Idea {
    ideaId
    userId
    title
    description
    isPublished
  }
`;

export const IDEA_DOCUMENT_FIELDS = gql`
  fragment IdeaDocumentFields on Idea {
    ideaId
    pitchDeck
    productRequirementsDocument
    provisionalPatent
    businessModelCanvas
    similarIdeas
  }
`;

/** Workspace list only — matches GraphQL IdeaSummary (small payload). */
export const IDEA_SUMMARY_FIELDS = gql`
  fragment IdeaSummaryFields on IdeaSummary {
    ideaId
    userId
    title
    hasDescription
    createdAt
    isPublished
    generatedAssetCount
  }
`;

export const GET_IDEAS: TypedDocumentNode<GetIdeasData, NoVariables> = gql`
  query GetIdeas {
    ideas {
      ...IdeaSummaryFields
    }
  }
  ${IDEA_SUMMARY_FIELDS}
`;

export const GET_IDEA: TypedDocumentNode<GetIdeaData, IdeaIdVariables> = gql`
  query GetIdea($ideaId: String!) {
    idea(ideaId: $ideaId) {
      ...IdeaFields
    }
  }
  ${IDEA_FIELDS}
`;

export const GET_IDEA_CORE: TypedDocumentNode<GetIdeaCoreData, IdeaIdVariables> = gql`
  query GetIdeaCore($ideaId: String!) {
    idea(ideaId: $ideaId) {
      ...IdeaCoreFields
    }
  }
  ${IDEA_CORE_FIELDS}
`;

export const GET_IDEA_DOCUMENTS = gql`
  query GetIdeaDocuments($ideaId: String!) {
    idea(ideaId: $ideaId) {
      ...IdeaDocumentFields
    }
  }
  ${IDEA_DOCUMENT_FIELDS}
`;

export const CREATE_IDEA: TypedDocumentNode<CreateIdeaData, CreateIdeaVariables> = gql`
  mutation CreateIdea($title: String!, $description: String) {
    createIdea(title: $title, description: $description) {
      ideaId
      title
      description
    }
  }
`;

export const GET_ACCOUNT = gql`
  query GetAccount {
    account {
      userId
      email
      username
      firstName
      lastName
      country
      bio
      address
      state
      gravatarHash
      profilePictureUrl
      skills
    }
  }
`;

export const GET_SURVEY_INSIGHTS = gql`
  query GetSurveyInsights($windowDays: Int!) {
    surveyInsights(windowDays: $windowDays) {
      generatedAt
      windowDays
      totalResponses
      researchResponses
      productFeedbackResponses
      researchSignupIntentAvg
      researchFollowUpRate
      productPmfVeryDisappointedPct
      productNpsScore
      productProgressAvg
      productDeliverableAvg
      productSatisfactionAvg
      productEaseAvg
      productSatisfactionTopboxPct
      productAiQualityAvg
      topResearchRoles {
        label
        count
        percentage
      }
      topResearchValueProps {
        label
        count
        percentage
      }
      topResearchBarriers {
        label
        count
        percentage
      }
      topResearchFirstOutputs {
        label
        count
        percentage
      }
      topResearchTrustSignals {
        label
        count
        percentage
      }
      topProductBenefits {
        label
        count
        percentage
      }
      topProductTasks {
        label
        count
        percentage
      }
      topActionThemes {
        theme
        count
      }
    }
  }
`;

export const UPDATE_ACCOUNT: TypedDocumentNode<UpdateAccountData, UpdateAccountVariables> = gql`
  mutation UpdateAccount($input: AccountUpdateInput!) {
    updateAccount(input: $input) {
      userId
      email
      username
      firstName
      lastName
      country
      bio
      address
      state
      gravatarHash
      profilePictureUrl
      skills
    }
  }
`;

export const START_GUEST_SESSION: TypedDocumentNode<StartGuestSessionData, NoVariables> = gql`
  mutation StartGuestSession {
    startGuestSession {
      userId
      email
      token
      mergeSecret
    }
  }
`;

export const GET_INTEGRATIONS: TypedDocumentNode<GetIntegrationsData, NoVariables> = gql`
  query GetIntegrations {
    integrations {
      integrationId
      userId
      serviceName
      serviceId
      connectedAt
      metadata
      linked
    }
  }
`;

export const GET_INTEGRATION = gql`
  query GetIntegration($serviceId: String!) {
    integration(serviceId: $serviceId) {
      integrationId
      userId
      serviceName
      serviceId
      connectedAt
      metadata
    }
  }
`;

export const CONNECT_INTEGRATION = gql`
  mutation ConnectIntegration($input: ConnectIntegrationInput!) {
    connectIntegration(input: $input) {
      integrationId
      userId
      serviceName
      serviceId
      connectedAt
      metadata
    }
  }
`;

export const START_INTEGRATION_CONNECTION: TypedDocumentNode<
  StartIntegrationConnectionData,
  StartIntegrationConnectionVars
> = gql`
  mutation StartIntegrationConnection($serviceId: String!, $name: String) {
    startIntegrationConnection(serviceId: $serviceId, name: $name) {
      serviceId
      status
      message
      connectUrl
    }
  }
`;

export const DISCONNECT_INTEGRATION = gql`
  mutation DisconnectIntegration($serviceId: String!) {
    disconnectIntegration(serviceId: $serviceId)
  }
`;

export const LOGOUT_USER = gql`
  mutation LogoutUser {
    logoutUser
  }
`;

export const REVOKE_ACCOUNT_SESSION = gql`
  mutation RevokeAccountSession($sessionId: String!) {
    revokeAccountSession(sessionId: $sessionId)
  }
`;

export const REVOKE_OTHER_ACCOUNT_SESSIONS: TypedDocumentNode<RevokeOtherAccountSessionsData, NoVariables> = gql`
  mutation RevokeOtherAccountSessions {
    revokeOtherAccountSessions
  }
`;

export const REQUEST_ACCOUNT_DELETION = gql`
  mutation RequestAccountDeletion($confirmEmail: String!) {
    requestAccountDeletion(confirmEmail: $confirmEmail)
  }
`;

export const GET_PROFILE = gql`
  query GetProfile {
    profile {
      userId
      email
      isGuest
    }
  }
`;

export const GET_MY_SESSIONS: TypedDocumentNode<GetMySessionsData, NoVariables> = gql`
  query GetMySessions {
    mySessions {
      sessionId
      current
      createdAt
      expiresAt
      revokedAt
      lastSeenAt
      requestIp
      userAgent
      kind
    }
  }
`;

export const GET_PRIVACY_STATUS: TypedDocumentNode<GetPrivacyStatusData, NoVariables> = gql`
  query GetPrivacyStatus {
    privacyStatus {
      exportAvailable
      deletionRequestedAt
      guestRetentionDays
    }
  }
`;

export const SUBMIT_CONTACT_FORM = gql`
  mutation SubmitContactForm($input: ContactFormInput!) {
    submitContactForm(input: $input)
  }
`;

export const SUBMIT_SURVEY = gql`
  mutation SubmitSurvey($input: SubmitSurveyInput!) {
    submitSurvey(input: $input)
  }
`;

export const FIND_SIMILAR_IDEAS: TypedDocumentNode<FindSimilarIdeasData, FindSimilarIdeasVariables> = gql`
  query FindSimilarIdeas($ideaDescription: String!) {
    findSimilarIdeas(ideaDescription: $ideaDescription) {
      similarIdeas
    }
  }
`;

export const GENERATE_PITCH_DECK = gql`
  mutation GeneratePitchDeck($ideaId: String!, $description: String!) {
    generatePitchDeck(ideaId: $ideaId, description: $description) {
      pitchDeck
    }
  }
`;

export const GET_PITCH_DECK = gql`
  query GetPitchDeck($ideaId: String!) {
    pitchDeck(ideaId: $ideaId) {
      pitchDeck
    }
  }
`;

export const GENERATE_PRODUCT_REQUIREMENTS_DOCUMENT = gql`
  mutation GenerateProductRequirementsDocument($ideaId: String!, $description: String!) {
    generateProductRequirementsDocument(ideaId: $ideaId, description: $description) {
      productRequirementsDocument
    }
  }
`;

export const GET_PRODUCT_REQUIREMENTS_DOCUMENT = gql`
  query GetProductRequirementsDocument($ideaId: String!) {
    productRequirementsDocument(ideaId: $ideaId) {
      productRequirementsDocument
    }
  }
`;

export const GENERATE_PROVISIONAL_PATENT = gql`
  mutation GenerateProvisionalPatent($ideaId: String!, $description: String!) {
    generateProvisionalPatent(ideaId: $ideaId, description: $description) {
      provisionalPatent
    }
  }
`;

export const GET_PROVISIONAL_PATENT = gql`
  query GetProvisionalPatent($ideaId: String!) {
    provisionalPatent(ideaId: $ideaId) {
      provisionalPatent
      coversheetPdf
      specificationPdf
    }
  }
`;

export const UPDATE_IDEA: TypedDocumentNode<UpdateIdeaData, UpdateIdeaVariables> = gql`
  mutation UpdateIdea($ideaId: String!, $title: String, $description: String, $requiredSkills: [String!]) {
    updateIdea(ideaId: $ideaId, title: $title, description: $description, requiredSkills: $requiredSkills) {
      ...IdeaFields
    }
  }
  ${IDEA_FIELDS}
`;

export const GET_AVAILABLE_SKILLS = gql`
  query GetAvailableSkills {
    availableSkills
  }
`;

export const DELETE_IDEA: TypedDocumentNode<DeleteIdeaData, IdeaIdVariables> = gql`
  mutation DeleteIdea($ideaId: String!) {
    deleteIdea(ideaId: $ideaId)
  }
`;

export const TOGGLE_PUBLISH_IDEA: TypedDocumentNode<TogglePublishIdeaData, IdeaIdVariables> = gql`
  mutation TogglePublishIdea($ideaId: String!) {
    togglePublishIdea(ideaId: $ideaId) {
      ideaId
      isPublished
    }
  }
`;

export const RUN_BACKGROUND_TASKS = gql`
  mutation RunBackgroundTasks($ideaId: String!, $description: String!) {
    runBackgroundTasks(ideaId: $ideaId, description: $description)
  }
`;

export const EXPORT_IDEAS: TypedDocumentNode<ExportIdeasData, ExportIdeasVariables> = gql`
  mutation ExportIdeas($format: String!) {
    exportIdeas(format: $format) {
      content
      format
      filename
    }
  }
`;

export const IMPORT_IDEAS: TypedDocumentNode<ImportIdeasData, ImportIdeasVariables> = gql`
  mutation ImportIdeas($fileContent: String!, $fileFormat: String!, $filename: String!) {
    importIdeas(fileContent: $fileContent, fileFormat: $fileFormat, filename: $filename) {
      importedCount
      skippedCount
      errors
    }
  }
`;

export const INVESTMENT_FIELDS = gql`
  fragment InvestmentFields on Investment {
    investmentId
    ideaId
    investorId
    cashAmount
    sweatEquityHours
    sweatEquityValue
    equityPercentage
    investmentType
    role
    status
    notes
    createdAt
    investorName
    investorAvatar
  }
`;

export const GET_IDEA_INVESTMENTS = gql`
  query GetIdeaInvestments($ideaId: String!) {
    ideaInvestments(ideaId: $ideaId) {
      ...InvestmentFields
    }
  }
  ${INVESTMENT_FIELDS}
`;

export const GET_IDEA_CAP_TABLE = gql`
  query GetIdeaCapTable($ideaId: String!) {
    ideaCapTable(ideaId: $ideaId) {
      entryId
      ideaId
      stakeholderId
      stakeholderType
      equityPercentage
      sharesOwned
      shareClass
      vestingStatus
      vestedPercentage
      stakeholderName
      stakeholderAvatar
    }
  }
`;

export const GET_MY_PORTFOLIO: TypedDocumentNode<GetMyPortfolioData, NoVariables> = gql`
  query GetMyPortfolio {
    myPortfolio {
      investmentId
      ideaId
      ideaTitle
      ideaDescription
      cashAmount
      sweatEquityValue
      equityPercentage
      status
      createdAt
    }
  }
`;

export const GET_USER_FOLLOWERS = gql`
  query GetUserFollowers($userId: String!) {
    userFollowers(userId: $userId) {
      followId
      followerId
      followedId
      createdAt
      userName
      userAvatar
    }
  }
`;

export const GET_USER_FOLLOWING = gql`
  query GetUserFollowing($userId: String!) {
    userFollowing(userId: $userId) {
      followId
      followerId
      followedId
      createdAt
      userName
      userAvatar
    }
  }
`;

export const GET_USER_SOCIAL_STATS = gql`
  query GetUserSocialStats($userId: String!) {
    userSocialStats(userId: $userId) {
      followerCount
      followingCount
      isFollowing
    }
  }
`;

export const UNIVERSAL_SEARCH = gql`
  query UniversalSearch($query: String!, $limit: Int, $includeWeb: Boolean) {
    universalSearch(query: $query, limit: $limit, includeWeb: $includeWeb) {
      query
      assistantSummary
      webSummary
      myIdeas {
        ideaId
        title
        snippet
        matchedIn
        createdAt
        userId
        isPublished
      }
      publishedIdeas {
        ideaId
        title
        snippet
        matchedIn
        createdAt
        userId
        isPublished
        creatorName
        creatorAvatar
      }
      webSources {
        title
        url
        hostname
      }
    }
  }
`;

export const CALCULATE_SWEAT_EQUITY: TypedDocumentNode<CalculateSweatEquityData, CalculateSweatEquityVariables> = gql`
  query CalculateSweatEquity($hours: Float!, $hourlyRate: Float, $totalValuation: Float) {
    calculateSweatEquity(hours: $hours, hourlyRate: $hourlyRate, totalValuation: $totalValuation) {
      sweatValue
      equityPercentage
      hours
      hourlyRate
    }
  }
`;

export const CREATE_INVESTMENT = gql`
  mutation CreateInvestment($input: CreateInvestmentInput!) {
    createInvestment(input: $input) {
      ...InvestmentFields
    }
  }
  ${INVESTMENT_FIELDS}
`;

export const ADD_INVESTMENT_CONTRIBUTION = gql`
  mutation AddInvestmentContribution($input: AddContributionInput!) {
    addInvestmentContribution(input: $input)
  }
`;

export const UPDATE_INVESTMENT_STATUS = gql`
  mutation UpdateInvestmentStatus($investmentId: String!, $status: String!) {
    updateInvestmentStatus(investmentId: $investmentId, status: $status)
  }
`;

export const FOLLOW_USER = gql`
  mutation FollowUser($followedId: String!) {
    followUser(followedId: $followedId) {
      following
      followedId
    }
  }
`;

export const UNFOLLOW_USER = gql`
  mutation UnfollowUser($followedId: String!) {
    unfollowUser(followedId: $followedId) {
      following
      followedId
    }
  }
`;

export const TOGGLE_FOLLOW: TypedDocumentNode<ToggleFollowData, ToggleFollowVariables> = gql`
  mutation ToggleFollow($followedId: String!) {
    toggleFollow(followedId: $followedId) {
      following
      followedId
    }
  }
`;

export const UPVOTE_IDEA = gql`
  mutation UpvoteIdea($ideaId: String!) {
    upvoteIdea(ideaId: $ideaId) {
      voted
      ideaId
      voteCount
    }
  }
`;

export const REMOVE_VOTE = gql`
  mutation RemoveVote($ideaId: String!) {
    removeVote(ideaId: $ideaId) {
      voted
      ideaId
      voteCount
    }
  }
`;

export const TOGGLE_UPVOTE: TypedDocumentNode<ToggleUpvoteData, IdeaIdVariables> = gql`
  mutation ToggleUpvote($ideaId: String!) {
    toggleUpvote(ideaId: $ideaId) {
      voted
      ideaId
      voteCount
    }
  }
`;

export const PITCH_REEL_FIELDS = gql`
  fragment PitchReelFields on PitchReel {
    reelId
    slug
    ideaId
    title
    subtitle
    thesis
    description
    tags
    videoUrl
    posterUrl
    videoStatus
    workspacePath
    accentFrom
    accentTo
    createdAt
    creator {
      userId
      handle
      name
      role
      initials
      avatar
      followerCount
      isFollowing
    }
    stats {
      likeCount
      commentCount
      shareCount
    }
    viewerState {
      liked
      reshared
    }
  }
`;

export const GET_PITCH_REELS_FEED: TypedDocumentNode<GetPitchReelsFeedData, GetPitchReelsFeedVariables> = gql`
  query GetPitchReelsFeed($limit: Int) {
    pitchReelsFeed(limit: $limit) {
      ...PitchReelFields
    }
  }
  ${PITCH_REEL_FIELDS}
`;

const PITCH_REEL_COMMENT_FIELDS = `
  commentId
  reelId
  authorId
  authorName
  authorHandle
  authorAvatar
  body
  createdAt
  isMine
`;

export const GET_PITCH_REEL_COMMENTS: TypedDocumentNode<GetPitchReelCommentsData, GetPitchReelCommentsVariables> = gql`
  query GetPitchReelComments($reelId: String!, $limit: Int) {
    pitchReelComments(reelId: $reelId, limit: $limit) {
      ${PITCH_REEL_COMMENT_FIELDS}
    }
  }
`;

export const TOGGLE_PITCH_REEL_LIKE: TypedDocumentNode<TogglePitchReelLikeData, TogglePitchReelLikeVariables> = gql`
  mutation TogglePitchReelLike($reelId: String!, $liked: Boolean!) {
    togglePitchReelLike(reelId: $reelId, liked: $liked) {
      reelId
      liked
      likeCount
    }
  }
`;

export const RESHARE_PITCH_REEL: TypedDocumentNode<ResharePitchReelData, ResharePitchReelVariables> = gql`
  mutation ResharePitchReel($reelId: String!, $reshared: Boolean!) {
    resharePitchReel(reelId: $reelId, reshared: $reshared) {
      reelId
      reshared
      shareCount
    }
  }
`;

export const CREATE_PITCH_REEL_COMMENT: TypedDocumentNode<CreatePitchReelCommentData, CreatePitchReelCommentVariables> = gql`
  mutation CreatePitchReelComment($reelId: String!, $body: String!) {
    createPitchReelComment(reelId: $reelId, body: $body) {
      comment {
        ${PITCH_REEL_COMMENT_FIELDS}
      }
    }
  }
`;

// ==================== MESSAGING QUERIES (Open Media) ====================

const CONVERSATION_FIELDS = `
  conversationId
  otherUserId
  otherUserName
  otherUserHandle
  otherUserAvatar
  ideaId
  ideaTitle
  lastMessageAt
  lastMessagePreview
  unreadCount
`;

const INBOX_CONVERSATION_FIELDS = `
  conversationId
  kind
  source
  title
  initials
  avatarColor
  avatarUrl
  group
  company
  preview
  lastMessageAt
  unreadCount
  ideaId
  ideaTitle
  canReply
`;

export const GET_MY_INBOX: TypedDocumentNode<GetMyInboxData, GetMyInboxVariables> = gql`
  query GetMyInbox($limit: Int) {
    myInbox(limit: $limit) {
      ${INBOX_CONVERSATION_FIELDS}
    }
  }
`;

export const GET_INBOX_CONVERSATION: TypedDocumentNode<GetInboxConversationData, GetInboxConversationVariables> = gql`
  query GetInboxConversation($conversationId: String!) {
    inboxConversation(conversationId: $conversationId) {
      conversation {
        ${INBOX_CONVERSATION_FIELDS}
      }
      items {
        kind
        key
        at
        messageId
        isMine
        senderName
        sentAt
        source
        subject
        body {
          text
          url
        }
        attachmentCount
        quotedHistoryHidden
        groupStart
        groupEnd
      }
    }
  }
`;

export const REPLY_IN_INBOX: TypedDocumentNode<ReplyInInboxData, ReplyInInboxVariables> = gql`
  mutation ReplyInInbox($conversationId: String!, $content: String!, $replyToMessageId: String, $clientId: String) {
    replyInInbox(conversationId: $conversationId, content: $content, replyToMessageId: $replyToMessageId, clientId: $clientId)
  }
`;

export const MARK_INBOX_READ: TypedDocumentNode<MarkInboxReadData, { conversationId: string }> = gql`
  mutation MarkInboxRead($conversationId: String!) {
    markInboxRead(conversationId: $conversationId)
  }
`;

export const GET_UNREAD_MESSAGE_COUNT: TypedDocumentNode<GetUnreadMessageCountData, NoVariables> = gql`
  query GetUnreadMessageCount {
    unreadMessageCount {
      count
    }
  }
`;

export const GET_IDEA_OWNER: TypedDocumentNode<GetIdeaOwnerData, IdeaIdVariables> = gql`
  query GetIdeaOwner($ideaId: String!) {
    ideaOwner(ideaId: $ideaId) {
      userId
      username
      firstName
      lastName
      bio
      profilePictureUrl
      ideaId
      ideaTitle
      isPublished
      canMessage
      openMediaHandle
    }
  }
`;

export const START_CONVERSATION: TypedDocumentNode<StartConversationData, StartConversationVariables> = gql`
  mutation StartConversation($otherUserId: String!, $ideaId: String) {
    startConversation(otherUserId: $otherUserId, ideaId: $ideaId) {
      ${CONVERSATION_FIELDS}
    }
  }
`;

// ==================== OPEN MEDIA ACCOUNT LINK ====================

const OPEN_MEDIA_LINK_FIELDS = `
  enabled
  linked
  needsReconnect
  handle
  displayName
  connectUrl
`;

export const GET_OPEN_MEDIA_LINK: TypedDocumentNode<GetOpenMediaLinkData, NoVariables> = gql`
  query GetOpenMediaLink {
    openMediaLink {
      ${OPEN_MEDIA_LINK_FIELDS}
    }
  }
`;

export const GET_OPEN_MEDIA_REALTIME_TOKEN: TypedDocumentNode<GetOpenMediaRealtimeTokenData, NoVariables> = gql`
  query GetOpenMediaRealtimeToken {
    openMediaRealtimeToken {
      supabaseUrl
      anonKey
      accessToken
      expiresAt
      omUserId
    }
  }
`;

// ==================== COLLABORATION QUERIES ====================

export const GET_IDEA_COLLABORATORS: TypedDocumentNode<GetIdeaCollaboratorsData, IdeaIdVariables> = gql`
  query GetIdeaCollaborators($ideaId: String!) {
    ideaCollaborators(ideaId: $ideaId) {
      collaboratorId
      ideaId
      userId
      role
      status
      userEmail
      userName
      userAvatar
      invitedAt
      acceptedAt
    }
  }
`;

export const GET_MY_SHARED_IDEAS = gql`
  query GetMySharedIdeas {
    mySharedIdeas {
      ideaId
      title
      description
      userRole
      createdAt
    }
  }
`;

export const GET_MY_COLLABORATION_INVITATIONS: TypedDocumentNode<GetMyCollaborationInvitationsData, NoVariables> = gql`
  query GetMyCollaborationInvitations {
    myCollaborationInvitations {
      collaboratorId
      ideaId
      role
      status
      ideaTitle
      ideaDescription
      inviterName
      invitedAt
    }
  }
`;

export const GET_IDEA_VERSIONS: TypedDocumentNode<GetIdeaVersionsData, IdeaIdVariables> = gql`
  query GetIdeaVersions($ideaId: String!) {
    ideaVersions(ideaId: $ideaId) {
      versionId
      ideaId
      versionNumber
      title
      description
      createdBy
      createdAt
      changeSummary
      creatorName
      creatorAvatar
      versionKind
    }
  }
`;

export const CHECK_IDEA_ACCESS = gql`
  query CheckIdeaAccess($ideaId: String!) {
    checkIdeaAccess(ideaId: $ideaId) {
      hasAccess
      role
    }
  }
`;

export const INVITE_COLLABORATOR: TypedDocumentNode<InviteCollaboratorData, InviteCollaboratorVariables> = gql`
  mutation InviteCollaborator($input: InviteCollaboratorInput!) {
    inviteCollaborator(input: $input) {
      success
      message
    }
  }
`;

export const RESPOND_TO_INVITATION = gql`
  mutation RespondToInvitation($ideaId: String!, $accept: Boolean!) {
    respondToInvitation(ideaId: $ideaId, accept: $accept)
  }
`;

export const UPDATE_COLLABORATOR_ROLE = gql`
  mutation UpdateCollaboratorRole($ideaId: String!, $targetUserId: String!, $newRole: String!) {
    updateCollaboratorRole(ideaId: $ideaId, targetUserId: $targetUserId, newRole: $newRole)
  }
`;

export const REMOVE_COLLABORATOR = gql`
  mutation RemoveCollaborator($ideaId: String!, $targetUserId: String!) {
    removeCollaborator(ideaId: $ideaId, targetUserId: $targetUserId)
  }
`;

export const CREATE_IDEA_VERSION = gql`
  mutation CreateIdeaVersion($ideaId: String!, $changeSummary: String) {
    createIdeaVersion(ideaId: $ideaId, changeSummary: $changeSummary) {
      versionId
      versionNumber
      changeSummary
      createdAt
      versionKind
    }
  }
`;

export const RESTORE_IDEA_VERSION = gql`
  mutation RestoreIdeaVersion($ideaId: String!, $versionId: String!) {
    restoreIdeaVersion(ideaId: $ideaId, versionId: $versionId)
  }
`;

// ===== Idea Qualification (pre-build conversational agent) =====

export const QUALIFICATION_SESSION_FIELDS = gql`
  fragment QualificationSessionFields on IdeaQualificationSession {
    id
    userId
    status
    initialIdeaText
    nextQuestion
    turnCount
    qualificationScore
    qualificationExplanation
    transcript {
      role
      content
      ts
    }
    userSeriousness
    userDomainKnowledge
    userGoals
    userBudget
    userTimeline
    userExecutionAbility
    ideaMarketNeed
    ideaTargetCustomer
    ideaFeasibility
    ideaDefensibility
    ideaRevenuePotential
    ideaCompetition
    ideaRisks
    createdAt
    updatedAt
  }
`;

export const START_IDEA_QUALIFICATION = gql`
  mutation StartIdeaQualification($initialIdeaText: String!) {
    startIdeaQualification(initialIdeaText: $initialIdeaText) {
      ...QualificationSessionFields
    }
  }
  ${QUALIFICATION_SESSION_FIELDS}
`;

export const CONTINUE_IDEA_QUALIFICATION = gql`
  mutation ContinueIdeaQualification($sessionId: String!, $userMessage: String!) {
    continueIdeaQualification(sessionId: $sessionId, userMessage: $userMessage) {
      ...QualificationSessionFields
    }
  }
  ${QUALIFICATION_SESSION_FIELDS}
`;

export const GET_IDEA_QUALIFICATION_SESSION = gql`
  query IdeaQualificationSession($sessionId: String!) {
    ideaQualificationSession(sessionId: $sessionId) {
      ...QualificationSessionFields
    }
  }
  ${QUALIFICATION_SESSION_FIELDS}
`;

export const GET_MY_IDEA_QUALIFICATION_SESSIONS = gql`
  query MyIdeaQualificationSessions {
    myIdeaQualificationSessions {
      id
      status
      initialIdeaText
      turnCount
      qualificationScore
      createdAt
      updatedAt
    }
  }
`;

// ===== Cost tracking + billing dashboard =====

export const AGENT_RUN_SUMMARY_FIELDS = gql`
  fragment AgentRunSummaryFields on AgentRunSummary {
    id
    agentKind
    status
    startedAt
    completedAt
    totalModelCostUsd
    totalBillableCostUsd
    totalInputTokens
    totalOutputTokens
    errorMessage
    qualificationSessionId
    ideaId
  }
`;

export const GET_MY_COST_DASHBOARD = gql`
  query MyCostDashboard {
    myCostDashboard {
      remainingUsd
      pctOfCap
      warnLevel
      estimatedTotalWithSubscriptionUsd
      limits {
        monthlyVariableCapUsd
        paused
        baseSubscriptionUsd
        currency
      }
      spend {
        monthStart
        totalBillableUsd
        totalModelCostUsd
        totalInputTokens
        totalOutputTokens
        eventCount
        byAgentKind {
          label
          billableUsd
        }
        byModel {
          label
          billableUsd
        }
      }
      recentRuns {
        ...AgentRunSummaryFields
      }
    }
  }
  ${AGENT_RUN_SUMMARY_FIELDS}
`;

export const GET_MY_AGENT_RUNS = gql`
  query MyAgentRuns($limit: Int) {
    myAgentRuns(limit: $limit) {
      ...AgentRunSummaryFields
    }
  }
  ${AGENT_RUN_SUMMARY_FIELDS}
`;

export const SET_VARIABLE_COST_CAP = gql`
  mutation SetVariableCostCap($monthlyCapUsd: Float, $paused: Boolean) {
    setVariableCostCap(monthlyCapUsd: $monthlyCapUsd, paused: $paused) {
      monthlyVariableCapUsd
      paused
      baseSubscriptionUsd
      currency
    }
  }
`;

export const GET_MY_COST_PREFLIGHT = gql`
  query MyCostPreflight($agentKind: String, $estCostUsd: Float) {
    myCostPreflight(agentKind: $agentKind, estCostUsd: $estCostUsd) {
      allowed
      reason
      monthlyUsageUsd
      capUsd
      remainingUsd
      estimatedCostUsd
      paused
      agentKind
    }
  }
`;

// ===== BMC per-section sub-agents =====

export const BMC_SECTION_FIELDS = gql`
  fragment BmcSectionFields on BmcSection {
    sectionName
    content
    contentFormat
    needsUserReview
    generatedByRunId
    lastGeneratedAt
    lastUserEditAt
  }
`;

export const GET_BMC_SECTIONS = gql`
  query BmcSections($ideaId: String!) {
    bmcSections(ideaId: $ideaId) {
      ...BmcSectionFields
    }
  }
  ${BMC_SECTION_FIELDS}
`;

export const REGENERATE_BMC_SECTION = gql`
  mutation RegenerateBmcSection($ideaId: String!, $sectionName: String!) {
    regenerateBmcSection(ideaId: $ideaId, sectionName: $sectionName) {
      ...BmcSectionFields
    }
  }
  ${BMC_SECTION_FIELDS}
`;

export const REGENERATE_ALL_BMC_SECTIONS = gql`
  mutation RegenerateAllBmcSections($ideaId: String!) {
    regenerateAllBmcSections(ideaId: $ideaId) {
      ...BmcSectionFields
    }
  }
  ${BMC_SECTION_FIELDS}
`;

// ===== Admin cost dashboard =====

export const ADMIN_AGENT_RUN_SUMMARY_FIELDS = gql`
  fragment AdminAgentRunSummaryFields on AdminAgentRunRow {
    id
    userId
    userEmail
    agentKind
    status
    startedAt
    completedAt
    totalBillableCostUsd
    totalInputTokens
    totalOutputTokens
    errorMessage
    qualificationSessionId
    ideaId
  }
`;

export const GET_ADMIN_COST_OVERVIEW = gql`
  query AdminCostOverview($windowDays: Int) {
    adminCostOverview(windowDays: $windowDays) {
      windowDays
      windowStart
      generatedAt
      burnRatePerDayUsd
      monthToDateBillableUsd
      projectedMonthBillableUsd
      totals {
        totalBillableUsd
        totalModelCostUsd
        totalInputTokens
        totalOutputTokens
        totalRuns
        failedRuns
        activeUsers
      }
      dailySeries {
        date
        billableUsd
        modelCostUsd
        eventCount
      }
      topUsers {
        userId
        email
        billableUsd
        eventCount
      }
      byAgentKind {
        label
        billableUsd
      }
      byModel {
        label
        billableUsd
      }
      expensiveRuns {
        id
        userId
        userEmail
        agentKind
        status
        billableUsd
        inputTokens
        outputTokens
        startedAt
      }
    }
  }
`;

export const GET_ADMIN_AGENT_RUNS = gql`
  query AdminAgentRuns($limit: Int, $agentKind: String, $status: String) {
    adminAgentRuns(limit: $limit, agentKind: $agentKind, status: $status) {
      ...AdminAgentRunSummaryFields
    }
  }
  ${ADMIN_AGENT_RUN_SUMMARY_FIELDS}
`;

export const GET_ADMIN_PRODUCTION_TEST_STATS = gql`
  query AdminProductionTestStats($hours: Int) {
    adminProductionTestStats(hours: $hours) {
      windowHours
      totalRuns
      passCount
      failCount
      flakyCount
      errorCount
      skippedCount
      failureRate
      issuesOpened
      issuesDeduped
      topFailingTests {
        testName
        failures
      }
    }
  }
`;

// ===== Partner discovery agent =====

export const PARTNER_CANDIDATE_FIELDS = gql`
  fragment PartnerCandidateFields on PartnerCandidate {
    id
    ideaId
    name
    website
    category
    whyRelevant
    suggestedUse
    integrationType
    dataRequired
    actionsPossible
    pricingNotes
    riskNotes
    implementationDifficulty
    recommendedNextStep
    rank
    relevanceScore
    confidence
    approved
    approvedAt
    lastGeneratedAt
  }
`;

export const GET_PARTNER_CANDIDATES = gql`
  query PartnerCandidates($ideaId: String!) {
    partnerCandidates(ideaId: $ideaId) {
      ...PartnerCandidateFields
    }
  }
  ${PARTNER_CANDIDATE_FIELDS}
`;

export const RUN_PARTNER_DISCOVERY = gql`
  mutation RunPartnerDiscovery($ideaId: String!, $maxCandidates: Int) {
    runPartnerDiscovery(ideaId: $ideaId, maxCandidates: $maxCandidates) {
      ...PartnerCandidateFields
    }
  }
  ${PARTNER_CANDIDATE_FIELDS}
`;

export const APPROVE_PARTNER_CANDIDATE = gql`
  mutation ApprovePartnerCandidate($candidateId: String!, $approved: Boolean!) {
    approvePartnerCandidate(candidateId: $candidateId, approved: $approved) {
      ...PartnerCandidateFields
    }
  }
  ${PARTNER_CANDIDATE_FIELDS}
`;

// Bring your own key: the customer's OpenAI key powers every AI feature.
const AI_KEY_STATUS_FIELDS = `
  configured
  source
  last4
`;

export const GET_AI_KEY_STATUS: TypedDocumentNode<GetAiKeyStatusData, Record<string, never>> = gql`
  query GetAiKeyStatus {
    aiKeyStatus { ${AI_KEY_STATUS_FIELDS} }
  }
`;

export const SAVE_OPENAI_API_KEY: TypedDocumentNode<SaveOpenaiApiKeyData, SaveOpenaiApiKeyVariables> = gql`
  mutation SaveOpenaiApiKey($apiKey: String!) {
    saveOpenaiApiKey(apiKey: $apiKey) { ${AI_KEY_STATUS_FIELDS} }
  }
`;

export const REMOVE_OPENAI_API_KEY: TypedDocumentNode<RemoveOpenaiApiKeyData, Record<string, never>> = gql`
  mutation RemoveOpenaiApiKey {
    removeOpenaiApiKey { ${AI_KEY_STATUS_FIELDS} }
  }
`;

export interface KnowledgeIdeaRef {
  ideaId: string;
  title: string;
  path: string;
  concepts: string[];
  /** Why the ideas are related (related ideas only). */
  reason?: string | null;
}

export interface IdeaKnowledgeGraphData {
  ideaKnowledgeGraph: {
    ideaId: string;
    ideaPath: string;
    passages: { id: string; kind: string; text: string }[];
    concepts: {
      label: string;
      path: string;
      passageIds: string[];
      documentTypes: string[];
      ideas: KnowledgeIdeaRef[];
      /** Other names for the concept, highlighted in the note too. */
      aliases: string[];
    }[];
    related: KnowledgeIdeaRef[];
    documents: { documentType: string; markdown: string }[];
  } | null;
}

/** What the app needs from an idea's knowledge graph: passages, concept names and cited
 * documents, to link documents back to the note (ADR 0006, ADR 0010). Agents and the CLI
 * read the full graph (roles, relations, reasons). */
export const GET_IDEA_KNOWLEDGE_GRAPH: TypedDocumentNode<
  IdeaKnowledgeGraphData,
  { ideaId: string }
> = gql`
  query GetIdeaKnowledgeGraph($ideaId: String!) {
    ideaKnowledgeGraph(ideaId: $ideaId) {
      ideaId
      ideaPath
      passages { id kind text }
      concepts {
        label
        path
        passageIds
        documentTypes
        ideas { ideaId title path concepts }
        aliases
      }
      related { ideaId title path concepts }
      documents { documentType markdown }
    }
  }
`;

// ==================== VAULT CLOUD SYNC (ADR 0012) ====================

/** One page of the account's ideas with when each last changed, for vault sync. */
export const VAULT_SYNC_IDEAS = gql`
  query VaultSyncIdeas($first: Int!, $after: String) {
    ideas(first: $first, after: $after) {
      ideaId
      title
      createdAt
      updatedAt
    }
  }
`;

/** Everything vault sync copies for one idea. */
export const VAULT_SYNC_IDEA = gql`
  query VaultSyncIdea($ideaId: String!) {
    idea(ideaId: $ideaId) {
      ideaId
      title
      description
      requiredSkills
      createdAt
      updatedAt
      pitchDeck
      productRequirementsDocument
      provisionalPatent
      businessModelCanvas
      similarIdeas
    }
  }
`;

/** Save a document's Markdown on an idea (vault sync pushes documents with it). */
export const SAVE_IDEA_DOCUMENT = gql`
  mutation SaveIdeaDocument($ideaId: String!, $documentType: String!, $content: String!) {
    saveIdeaDocument(ideaId: $ideaId, documentType: $documentType, content: $content) {
      ideaId
      documentType
    }
  }
`;
