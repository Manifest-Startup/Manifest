import Foundation

// Mirrors of the GraphQL types in backend/app/graphql (field names match the
// camelCase schema). Only the fields the app selects are declared.

nonisolated struct User: Codable, Sendable, Equatable {
    var userId: String
    var email: String
    var createdAt: Date?
    var username: String?
    var firstName: String?
    var lastName: String?
    var country: String?
    var bio: String?
    var state: String?
    var profilePictureUrl: String?
    var skills: [String]

    var displayName: String {
        let name = [firstName, lastName].compactMap { $0?.trimmed.nilIfEmpty }.joined(separator: " ")
        if !name.isEmpty { return name }
        if let username = username?.nilIfEmpty { return username }
        return email.components(separatedBy: "@").first ?? email
    }

    var initials: String { displayName.initials }

    /// Guest workspaces use a synthetic address.
    var isGuest: Bool { email.hasSuffix("@guest.manifest") }
}

nonisolated struct IdeaSummary: Codable, Sendable, Identifiable, Hashable {
    var ideaId: String
    var userId: String
    var title: String
    var description: String?
    var hasDescription: Bool
    var createdAt: Date
    var isPublished: Bool
    var generatedAssetCount: Int

    var id: String { ideaId }
}

nonisolated struct Idea: Codable, Sendable, Identifiable, Equatable {
    var ideaId: String
    var userId: String
    var title: String
    var description: String?
    var createdAt: Date
    var pitchDeck: String?
    var productRequirementsDocument: String?
    var provisionalPatent: String?
    var businessModelCanvas: String?
    var similarIdeas: String?
    var isPublished: Bool
    var requiredSkills: [String]

    var id: String { ideaId }

    func content(for kind: DocumentKind) -> String? {
        let raw: String? =
            switch kind {
            case .pitchDeck: pitchDeck
            case .prd: productRequirementsDocument
            case .patent: provisionalPatent
            case .similar: similarIdeas
            }
        return raw?.trimmed.nilIfEmpty
    }

    var summary: IdeaSummary {
        IdeaSummary(
            ideaId: ideaId, userId: userId, title: title, description: description,
            hasDescription: !(description ?? "").isEmpty, createdAt: createdAt,
            isPublished: isPublished,
            generatedAssetCount: DocumentKind.allCases.filter { content(for: $0) != nil }.count
        )
    }
}

/// The AI documents an idea can grow into.
nonisolated enum DocumentKind: String, CaseIterable, Identifiable, Sendable, Codable {
    case pitchDeck = "pitch_deck"
    case prd = "product_requirements_document"
    case patent = "provisional_patent"
    case similar = "similar_ideas"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .pitchDeck: "Pitch Deck"
        case .prd: "Product Requirements"
        case .patent: "Provisional Patent"
        case .similar: "Landscape"
        }
    }

    var subtitle: String {
        switch self {
        case .pitchDeck: "The story investors read in three minutes"
        case .prd: "What to build first, and why"
        case .patent: "A draft to protect what's novel"
        case .similar: "Comparable companies and open questions"
        }
    }

    var symbol: String {
        switch self {
        case .pitchDeck: "rectangle.on.rectangle.angled"
        case .prd: "list.bullet.clipboard"
        case .patent: "seal"
        case .similar: "binoculars"
        }
    }

    var gradient: (String, String) {
        switch self {
        case .pitchDeck: ("#0A84FF", "#5E5CE6")
        case .prd: ("#30B0C7", "#0A84FF")
        case .patent: ("#FF9F0A", "#FF375F")
        case .similar: ("#34C759", "#30B0C7")
        }
    }
}

nonisolated struct PublishResult: Codable, Sendable { var ideaId: String; var isPublished: Bool }

nonisolated struct BmcSection: Codable, Sendable, Identifiable, Equatable {
    var sectionName: String
    var content: String?
    var contentFormat: String
    var needsUserReview: Bool
    var lastGeneratedAt: String?
    var lastUserEditAt: String?

    var id: String { sectionName }
    var meta: CanvasSection { CanvasSection(rawValue: sectionName) ?? .valuePropositions }
    var hasContent: Bool { !(content ?? "").trimmed.isEmpty }
}

nonisolated enum CanvasSection: String, CaseIterable, Sendable {
    case keyPartners = "key_partners"
    case keyActivities = "key_activities"
    case keyResources = "key_resources"
    case valuePropositions = "value_propositions"
    case customerRelationships = "customer_relationships"
    case channels
    case customerSegments = "customer_segments"
    case costStructure = "cost_structure"
    case revenueStreams = "revenue_streams"

    var title: String {
        switch self {
        case .keyPartners: "Key Partners"
        case .keyActivities: "Key Activities"
        case .keyResources: "Key Resources"
        case .valuePropositions: "Value Propositions"
        case .customerRelationships: "Customer Relationships"
        case .channels: "Channels"
        case .customerSegments: "Customer Segments"
        case .costStructure: "Cost Structure"
        case .revenueStreams: "Revenue Streams"
        }
    }

    var prompt: String {
        switch self {
        case .keyPartners: "Who helps you deliver?"
        case .keyActivities: "What must you do brilliantly?"
        case .keyResources: "What assets make it possible?"
        case .valuePropositions: "Why will people choose you?"
        case .customerRelationships: "How do you win and keep them?"
        case .channels: "How do you reach them?"
        case .customerSegments: "Who is this for?"
        case .costStructure: "What does it cost to run?"
        case .revenueStreams: "How does money come in?"
        }
    }

    var symbol: String {
        switch self {
        case .keyPartners: "link"
        case .keyActivities: "bolt"
        case .keyResources: "shippingbox"
        case .valuePropositions: "sparkles"
        case .customerRelationships: "heart"
        case .channels: "paperplane"
        case .customerSegments: "person.2"
        case .costStructure: "chart.bar.xaxis"
        case .revenueStreams: "dollarsign.circle"
        }
    }

    /// Reading order: who it's for → why → how → economics.
    static let readingOrder: [CanvasSection] = [
        .customerSegments, .valuePropositions, .channels, .customerRelationships,
        .revenueStreams, .keyResources, .keyActivities, .keyPartners, .costStructure,
    ]
}

nonisolated struct IdeaVersion: Codable, Sendable, Identifiable {
    var versionId: String
    var versionNumber: Int
    var title: String?
    var description: String?
    var createdAt: Date
    var changeSummary: String?
    var creatorName: String?
    var versionKind: String?
    var id: String { versionId }
}

nonisolated struct Collaborator: Codable, Sendable, Identifiable {
    var collaboratorId: String?
    var userId: String
    var role: String
    var status: String
    var userEmail: String?
    var userName: String?
    var userAvatar: String?
    var id: String { userId }
    var name: String { userName?.nilIfEmpty ?? userEmail ?? "Collaborator" }
}

nonisolated struct InviteResult: Codable, Sendable { var success: Bool; var message: String }

nonisolated struct SharedIdea: Codable, Sendable, Identifiable, Hashable {
    var ideaId: String
    var title: String
    var description: String?
    var userRole: String
    var createdAt: Date
    var id: String { ideaId }
}

nonisolated struct CollaborationInvitation: Codable, Sendable, Identifiable {
    var collaboratorId: String
    var ideaId: String
    var role: String
    var ideaTitle: String?
    var ideaDescription: String?
    var inviterName: String?
    var id: String { collaboratorId }
}

// MARK: Qualification interview

nonisolated struct QualificationMessage: Codable, Sendable, Hashable {
    var role: String
    var content: String
}

nonisolated struct QualificationSession: Codable, Sendable, Identifiable {
    var id: String
    var ideaId: String?
    var initialIdeaText: String
    var status: String
    var transcript: [QualificationMessage]
    var nextQuestion: String?
    var turnCount: Int
    var qualificationScore: Int?
    var qualificationExplanation: String?
    var ideaMarketNeed: Int?
    var ideaFeasibility: Int?
    var ideaDefensibility: Int?
    var ideaRevenuePotential: Int?
    var ideaTargetCustomer: String?
    var ideaRisks: String?
    var createdAt: String?

    var isComplete: Bool { status != "in_progress" }
}

// MARK: Pitch shorts

nonisolated struct PitchReel: Codable, Sendable, Identifiable, Equatable {
    var reelId: String
    var slug: String
    var title: String
    var subtitle: String?
    var thesis: String?
    var description: String?
    var tags: [String]
    var videoUrl: String
    var posterUrl: String?
    var videoStatus: String
    var accentFrom: String
    var accentTo: String
    var createdAt: Date
    var creator: Creator
    var stats: Stats
    var viewerState: ViewerState
    var ideaId: String?

    var id: String { reelId }

    nonisolated struct Creator: Codable, Sendable, Equatable {
        var userId: String
        var handle: String?
        var name: String
        var role: String?
        var initials: String
        var avatar: String?
        var followerCount: Int
        var isFollowing: Bool
    }

    nonisolated struct Stats: Codable, Sendable, Equatable {
        var likeCount: Int
        var commentCount: Int
        var shareCount: Int
    }

    nonisolated struct ViewerState: Codable, Sendable, Equatable {
        var liked: Bool
        var reshared: Bool
    }

    var videoURL: URL? { URL(string: videoUrl, relativeTo: AppConfig.baseURL)?.absoluteURL }
    var posterURL: URL? { posterUrl.flatMap { URL(string: $0, relativeTo: AppConfig.baseURL)?.absoluteURL } }
    var shareURL: URL { Self.shareURL(for: reelId) }

    /// The canonical web link for a short (`/shorts` redirects here).
    static func shareURL(for reelId: String) -> URL {
        var components = URLComponents(url: AppConfig.baseURL.appending(path: "pitch-reels"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "clip", value: reelId)]
        return components.url!
    }
}

nonisolated struct PitchReelComment: Codable, Sendable, Identifiable, Equatable {
    var commentId: String
    var authorName: String
    var authorHandle: String?
    var authorAvatar: String?
    var body: String
    var createdAt: Date
    var isMine: Bool
    var id: String { commentId }
}

nonisolated struct LikeResult: Codable, Sendable { var liked: Bool; var likeCount: Int? }
nonisolated struct ShareResult: Codable, Sendable { var reshared: Bool; var shareCount: Int? }
nonisolated struct FollowResult: Codable, Sendable { var following: Bool; var followedId: String }

// MARK: Portfolio

nonisolated struct PortfolioItem: Codable, Sendable, Identifiable, Hashable {
    var investmentId: String
    var ideaId: String
    var ideaTitle: String
    var ideaDescription: String?
    var cashAmount: Double
    var sweatEquityValue: Double
    var equityPercentage: Double
    var status: String
    var createdAt: Date

    var id: String { investmentId }
    var totalValue: Double { cashAmount + sweatEquityValue }
}

nonisolated struct Investment: Codable, Sendable, Identifiable {
    var investmentId: String
    var investorId: String
    var cashAmount: Double
    var sweatEquityHours: Double
    var sweatEquityValue: Double
    var equityPercentage: Double
    var investmentType: String
    var role: String?
    var status: String
    var notes: String?
    var createdAt: Date
    var investorName: String?
    var investorAvatar: String?
    var id: String { investmentId }
}

nonisolated struct CapTableEntry: Codable, Sendable, Identifiable {
    var entryId: String
    var stakeholderType: String
    var equityPercentage: Double
    var shareClass: String
    var vestingStatus: String
    var vestedPercentage: Double
    var stakeholderName: String?
    var id: String { entryId }
}

// MARK: Inbox

nonisolated struct InboxConversation: Codable, Sendable, Identifiable, Hashable {
    var conversationId: String
    var kind: String
    var source: String
    var title: String
    var initials: String
    var avatarColor: String?
    var avatarUrl: String?
    var group: Bool
    var company: String?
    var preview: String?
    var lastMessageAt: Date
    var unreadCount: Int
    var ideaId: String?
    var ideaTitle: String?
    var canReply: Bool

    var id: String { conversationId }
}

nonisolated struct InboxThread: Codable, Sendable {
    var conversation: InboxConversation
    var items: [InboxItem]
}

nonisolated struct InboxItem: Codable, Sendable, Identifiable, Equatable {
    var kind: String
    var key: String
    var at: Date?
    var messageId: String?
    var isMine: Bool
    var senderName: String?
    var sentAt: Date?
    var subject: String?
    var body: [Segment]
    var attachmentCount: Int
    var quotedHistoryHidden: Bool
    var groupStart: Bool
    var groupEnd: Bool

    var id: String { key }
    var isMessage: Bool { kind == "message" }
    var text: String { body.map(\.text).joined() }

    nonisolated struct Segment: Codable, Sendable, Equatable {
        var text: String
        var url: String?
    }
}

nonisolated struct IdeaOwner: Codable, Sendable {
    var userId: String
    var username: String?
    var firstName: String?
    var lastName: String?
    var bio: String?
    var profilePictureUrl: String?
    var canMessage: Bool
    var openMediaHandle: String?
    var name: String {
        let n = [firstName, lastName].compactMap { $0?.nilIfEmpty }.joined(separator: " ")
        return n.isEmpty ? (username ?? "Founder") : n
    }
}

nonisolated struct Conversation: Codable, Sendable { var conversationId: String }

// MARK: Account

nonisolated struct AIKeyStatus: Codable, Sendable, Equatable {
    var configured: Bool
    var source: String
    var last4: String?
}

nonisolated struct SessionInfo: Codable, Sendable, Identifiable {
    var sessionId: String
    var current: Bool
    var createdAt: Date?
    var lastSeenAt: Date?
    var requestIp: String?
    var userAgent: String?
    var kind: String
    var id: String { sessionId }
}

nonisolated struct OpenMediaLink: Codable, Sendable {
    var enabled: Bool
    var linked: Bool
    var needsReconnect: Bool
    var handle: String?
    var displayName: String?
    var avatarUrl: String?
    var connectUrl: String
}

nonisolated struct Integration: Codable, Sendable, Identifiable {
    var serviceName: String
    var serviceId: String
    var connectedAt: Date
    var linked: Bool
    var id: String { serviceId }
}

nonisolated struct SocialStats: Codable, Sendable {
    var followerCount: Int
    var followingCount: Int
    var isFollowing: Bool
}

nonisolated struct ExportResult: Codable, Sendable { var content: String; var format: String; var filename: String }
nonisolated struct ImportResult: Codable, Sendable { var importedCount: Int; var skippedCount: Int; var errors: [String] }

nonisolated struct PrivacyStatus: Codable, Sendable {
    var exportAvailable: Bool
    var deletionRequestedAt: Date?
    var guestRetentionDays: Int
}

// MARK: Search

nonisolated struct SearchResults: Codable, Sendable {
    var query: String
    var myIdeas: [SearchIdea]
    var publishedIdeas: [SearchIdea]
    var assistantSummary: String?
}

nonisolated struct SearchIdea: Codable, Sendable, Identifiable, Hashable {
    var ideaId: String
    var title: String
    var snippet: String
    var createdAt: Date
    var userId: String
    var isPublished: Bool
    var creatorName: String?
    var id: String { ideaId }
}

nonisolated struct GuestSession: Codable, Sendable {
    var userId: String
    var token: String
}

// MARK: Helpers

nonisolated extension String {
    var trimmed: String { trimmingCharacters(in: .whitespacesAndNewlines) }
    var nilIfEmpty: String? { trimmed.isEmpty ? nil : self }
    var initials: String {
        let parts = split(separator: " ").prefix(2)
        let letters = parts.compactMap(\.first).map(String.init).joined()
        return letters.isEmpty ? "M" : letters.uppercased()
    }
}
