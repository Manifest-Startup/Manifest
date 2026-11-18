import Foundation

/// Every GraphQL operation the app sends, typed. Selections are kept to the
/// fields each screen renders, so payloads stay small.
nonisolated enum API {
    private static var client: GraphQLClient { .shared }

    /// Single-field responses: `{ "fieldName": T }`.
    private struct Field<T: Decodable & Sendable>: Decodable, Sendable {
        let value: T
        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: AnyKey.self)
            guard let key = container.allKeys.first else {
                throw DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: "No field"))
            }
            value = try container.decode(T.self, forKey: key)
        }
    }

    private struct AnyKey: CodingKey {
        var stringValue: String
        var intValue: Int? { nil }
        init(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { nil }
    }

    private static func field<T: Decodable & Sendable>(
        _ query: String, _ variables: [String: JSONValue] = [:], timeout: TimeInterval = 30
    ) async throws -> T {
        try await client.run(query, variables, as: Field<T>.self, timeout: timeout).value
    }

    // AI generation can take a couple of minutes on a cold model.
    static let generationTimeout: TimeInterval = 210

    // MARK: Fragments

    static let userFields = "userId email createdAt username firstName lastName country bio state profilePictureUrl skills"
    static let ideaSummaryFields = "ideaId userId title description hasDescription createdAt isPublished generatedAssetCount"
    static let ideaFields = """
        ideaId userId title description createdAt pitchDeck productRequirementsDocument \
        provisionalPatent businessModelCanvas similarIdeas isPublished requiredSkills
        """
    static let reelFields = """
        reelId slug title subtitle thesis description tags videoUrl posterUrl videoStatus accentFrom accentTo createdAt ideaId
        creator { userId handle name role initials avatar followerCount isFollowing }
        stats { likeCount commentCount shareCount }
        viewerState { liked reshared }
        """
    static let inboxConversationFields = """
        conversationId kind source title initials avatarColor avatarUrl group company preview lastMessageAt unreadCount ideaId ideaTitle canReply
        """
    static let qualificationFields = """
        id ideaId initialIdeaText status transcript { role content } nextQuestion turnCount qualificationScore \
        qualificationExplanation ideaMarketNeed ideaFeasibility ideaDefensibility ideaRevenuePotential ideaTargetCustomer ideaRisks createdAt
        """

    // MARK: Account

    static func me() async throws -> User {
        try await field("query Me { me { \(userFields) } }")
    }

    static func updateAccount(_ input: [String: JSONValue]) async throws -> User {
        try await field(
            "mutation UpdateAccount($input: AccountUpdateInput!) { updateAccount(input: $input) { \(userFields) } }",
            ["input": .object(input)]
        )
    }

    static func startGuestSession() async throws -> GuestSession {
        try await field("mutation Guest { startGuestSession { userId token } }")
    }

    static func logout() async throws {
        let _: Bool = try await field("mutation Logout { logoutUser }")
    }

    static func aiKeyStatus() async throws -> AIKeyStatus {
        try await field("query AiKey { aiKeyStatus { configured source last4 } }")
    }

    static func saveAIKey(_ key: String) async throws -> AIKeyStatus {
        try await field(
            "mutation SaveKey($k: String!) { saveOpenaiApiKey(apiKey: $k) { configured source last4 } }",
            ["k": .string(key)]
        )
    }

    static func removeAIKey() async throws -> AIKeyStatus {
        try await field("mutation RemoveKey { removeOpenaiApiKey { configured source last4 } }")
    }

    static func sessions() async throws -> [SessionInfo] {
        try await field("query Sessions { mySessions { sessionId current createdAt lastSeenAt requestIp userAgent kind } }")
    }

    static func revokeSession(_ id: String) async throws {
        let _: Bool = try await field(
            "mutation Revoke($id: String!) { revokeAccountSession(sessionId: $id) }", ["id": .string(id)])
    }

    static func revokeOtherSessions() async throws -> Int {
        try await field("mutation RevokeOthers { revokeOtherAccountSessions }")
    }

    static func openMediaLink() async throws -> OpenMediaLink {
        try await field("query OML { openMediaLink { enabled linked needsReconnect handle displayName avatarUrl connectUrl } }")
    }

    static func integrations() async throws -> [Integration] {
        try await field("query Integrations { integrations { serviceName serviceId connectedAt linked } }")
    }

    static func disconnectIntegration(_ serviceId: String) async throws {
        let _: Bool = try await field(
            "mutation Disconnect($s: String!) { disconnectIntegration(serviceId: $s) }", ["s": .string(serviceId)])
    }

    static func privacyStatus() async throws -> PrivacyStatus {
        try await field("query Privacy { privacyStatus { exportAvailable deletionRequestedAt guestRetentionDays } }")
    }

    static func requestAccountDeletion(email: String) async throws {
        let _: Bool = try await field(
            "mutation Delete($e: String!) { requestAccountDeletion(confirmEmail: $e) }", ["e": .string(email)])
    }

    static func exportIdeas(format: String) async throws -> ExportResult {
        try await field(
            "mutation Export($f: String!) { exportIdeas(format: $f) { content format filename } }", ["f": .string(format)])
    }

    static func importIdeas(content: String, format: String, filename: String) async throws -> ImportResult {
        try await field(
            """
            mutation Import($c: String!, $f: String!, $n: String!) {
              importIdeas(fileContent: $c, fileFormat: $f, filename: $n) { importedCount skippedCount errors }
            }
            """,
            ["c": .string(content), "f": .string(format), "n": .string(filename)]
        )
    }

    static func submitFeedback(firstName: String, lastName: String, email: String, message: String) async throws {
        let _: Bool = try await field(
            "mutation Contact($i: ContactFormInput!) { submitContactForm(input: $i) }",
            [
                "i": [
                    "firstName": .string(firstName), "lastName": .string(lastName),
                    "email": .string(email), "message": .string(message),
                ]
            ]
        )
    }

    static func socialStats(userId: String) async throws -> SocialStats {
        try await field(
            "query Stats($u: String!) { userSocialStats(userId: $u) { followerCount followingCount isFollowing } }",
            ["u": .string(userId)])
    }

    // MARK: Ideas

    static func ideas() async throws -> [IdeaSummary] {
        try await field("query Ideas { ideas(first: 200) { \(ideaSummaryFields) } }")
    }

    static func idea(_ id: String) async throws -> Idea {
        try await field("query Idea($id: String!) { idea(ideaId: $id) { \(ideaFields) } }", ["id": .string(id)])
    }

    static func createIdea(title: String, description: String?) async throws -> Idea {
        try await field(
            "mutation Create($t: String!, $d: String) { createIdea(title: $t, description: $d) { \(ideaFields) } }",
            ["t": .string(title), "d": .optional(description)]
        )
    }

    static func updateIdea(id: String, title: String?, description: String?, skills: [String]? = nil) async throws -> Idea {
        try await field(
            """
            mutation Update($id: String!, $t: String, $d: String, $s: [String!]) {
              updateIdea(ideaId: $id, title: $t, description: $d, requiredSkills: $s) { \(ideaFields) }
            }
            """,
            ["id": .string(id), "t": .optional(title), "d": .optional(description), "s": skills.map(JSONValue.strings) ?? .null]
        )
    }

    static func deleteIdea(_ id: String) async throws {
        let _: Bool = try await field("mutation Del($id: String!) { deleteIdea(ideaId: $id) }", ["id": .string(id)])
    }

    static func togglePublish(_ id: String) async throws -> PublishResult {
        try await field(
            "mutation Pub($id: String!) { togglePublishIdea(ideaId: $id) { ideaId isPublished } }", ["id": .string(id)])
    }

    static func generate(_ kind: DocumentKind, ideaId: String, description: String) async throws -> String {
        let vars: [String: JSONValue] = ["id": .string(ideaId), "d": .string(description)]
        switch kind {
        case .pitchDeck:
            struct R: Decodable, Sendable { let pitchDeck: String }
            let r: R = try await field(
                "mutation G($id: String!, $d: String!) { generatePitchDeck(ideaId: $id, description: $d) { pitchDeck } }",
                vars, timeout: generationTimeout)
            return r.pitchDeck
        case .prd:
            struct R: Decodable, Sendable { let productRequirementsDocument: String }
            let r: R = try await field(
                """
                mutation G($id: String!, $d: String!) {
                  generateProductRequirementsDocument(ideaId: $id, description: $d) { productRequirementsDocument }
                }
                """, vars, timeout: generationTimeout)
            return r.productRequirementsDocument
        case .patent:
            struct R: Decodable, Sendable { let provisionalPatent: String }
            let r: R = try await field(
                "mutation G($id: String!, $d: String!) { generateProvisionalPatent(ideaId: $id, description: $d) { provisionalPatent } }",
                vars, timeout: generationTimeout)
            return r.provisionalPatent
        case .similar:
            let job: EnqueueResult = try await field(
                """
                mutation Q($id: String!, $types: [String!]!) {
                  enqueueBackgroundTasks(ideaId: $id, documentTypes: $types) { jobId status }
                }
                """,
                ["id": .string(ideaId), "types": ["similar_ideas"]]
            )
            try await waitForJob(job.jobId)
            return try await idea(ideaId).similarIdeas ?? ""
        }
    }

    private struct EnqueueResult: Decodable, Sendable { let jobId: String; let status: String }
    private struct Job: Decodable, Sendable { let status: String; let errorMessage: String? }

    /// Polls a durable generation job with gentle backoff.
    private static func waitForJob(_ id: String) async throws {
        var delay: UInt64 = 1_500_000_000
        let deadline = Date().addingTimeInterval(generationTimeout)
        while Date() < deadline {
            try await Task.sleep(nanoseconds: delay)
            let job: Job? = try await field(
                "query J($id: String!) { generationJob(jobId: $id) { status errorMessage } }", ["id": .string(id)])
            switch job?.status {
            case "succeeded": return
            case "failed":
                throw APIError.from(message: job?.errorMessage ?? "Generation failed.")
            default: delay = min(delay * 3 / 2, 6_000_000_000)
            }
        }
        throw APIError.server("Still working on it. Check back in a minute.")
    }

    static func saveDocument(ideaId: String, kind: DocumentKind, content: String) async throws {
        struct R: Decodable, Sendable { let characters: Int }
        let _: R = try await field(
            """
            mutation Save($id: String!, $t: String!, $c: String!) {
              saveIdeaDocument(ideaId: $id, documentType: $t, content: $c) { characters }
            }
            """,
            ["id": .string(ideaId), "t": .string(kind.rawValue), "c": .string(content)]
        )
    }

    // MARK: Canvas

    private static let bmcFields = "sectionName content contentFormat needsUserReview lastGeneratedAt lastUserEditAt"

    static func canvas(ideaId: String) async throws -> [BmcSection] {
        try await field("query BMC($id: String!) { bmcSections(ideaId: $id) { \(bmcFields) } }", ["id": .string(ideaId)])
    }

    static func saveCanvasSection(ideaId: String, section: String, content: String) async throws -> BmcSection {
        try await field(
            """
            mutation SaveBMC($id: String!, $s: String!, $c: String!) {
              saveBmcSection(ideaId: $id, sectionName: $s, content: $c) { \(bmcFields) }
            }
            """,
            ["id": .string(ideaId), "s": .string(section), "c": .string(content)]
        )
    }

    static func regenerateCanvasSection(ideaId: String, section: String) async throws -> BmcSection {
        try await field(
            "mutation RegenBMC($id: String!, $s: String!) { regenerateBmcSection(ideaId: $id, sectionName: $s) { \(bmcFields) } }",
            ["id": .string(ideaId), "s": .string(section)], timeout: generationTimeout)
    }

    static func regenerateCanvas(ideaId: String) async throws -> [BmcSection] {
        try await field(
            "mutation RegenAll($id: String!) { regenerateAllBmcSections(ideaId: $id) { \(bmcFields) } }",
            ["id": .string(ideaId)], timeout: generationTimeout)
    }

    // MARK: Qualification

    static func qualificationSessions() async throws -> [QualificationSession] {
        try await field("query QS { myIdeaQualificationSessions { \(qualificationFields) } }")
    }

    static func startQualification(text: String) async throws -> QualificationSession {
        try await field(
            "mutation SQ($t: String!) { startIdeaQualification(initialIdeaText: $t) { \(qualificationFields) } }",
            ["t": .string(text)], timeout: 90)
    }

    static func continueQualification(sessionId: String, message: String) async throws -> QualificationSession {
        try await field(
            "mutation CQ($s: String!, $m: String!) { continueIdeaQualification(sessionId: $s, userMessage: $m) { \(qualificationFields) } }",
            ["s": .string(sessionId), "m": .string(message)], timeout: 90)
    }

    // MARK: Team, versions, investing

    static func collaborators(ideaId: String) async throws -> [Collaborator] {
        try await field(
            "query C($id: String!) { ideaCollaborators(ideaId: $id) { collaboratorId userId role status userEmail userName userAvatar } }",
            ["id": .string(ideaId)])
    }

    static func invite(ideaId: String, email: String, role: String) async throws -> InviteResult {
        try await field(
            "mutation SendInvite($i: InviteCollaboratorInput!) { inviteCollaborator(input: $i) { success message } }",
            ["i": ["ideaId": .string(ideaId), "email": .string(email), "role": .string(role)]])
    }

    static func removeCollaborator(ideaId: String, userId: String) async throws {
        let _: Bool = try await field(
            "mutation RC($id: String!, $u: String!) { removeCollaborator(ideaId: $id, targetUserId: $u) }",
            ["id": .string(ideaId), "u": .string(userId)])
    }

    static func updateCollaboratorRole(ideaId: String, userId: String, role: String) async throws {
        let _: Bool = try await field(
            "mutation UR($id: String!, $u: String!, $r: String!) { updateCollaboratorRole(ideaId: $id, targetUserId: $u, newRole: $r) }",
            ["id": .string(ideaId), "u": .string(userId), "r": .string(role)])
    }

    static func sharedIdeas() async throws -> [SharedIdea] {
        try await field("query Shared { mySharedIdeas { ideaId title description userRole createdAt } }")
    }

    static func invitations() async throws -> [CollaborationInvitation] {
        try await field(
            "query Invites { myCollaborationInvitations { collaboratorId ideaId role ideaTitle ideaDescription inviterName } }")
    }

    static func respond(ideaId: String, accept: Bool) async throws {
        let _: Bool = try await field(
            "mutation Resp($id: String!, $a: Boolean!) { respondToInvitation(ideaId: $id, accept: $a) }",
            ["id": .string(ideaId), "a": .bool(accept)])
    }

    static func versions(ideaId: String) async throws -> [IdeaVersion] {
        try await field(
            """
            query V($id: String!) {
              ideaVersions(ideaId: $id) { versionId versionNumber title description createdAt changeSummary creatorName versionKind }
            }
            """, ["id": .string(ideaId)])
    }

    static func createVersion(ideaId: String, summary: String?) async throws {
        struct R: Decodable, Sendable { let versionId: String }
        let _: R = try await field(
            "mutation CV($id: String!, $s: String) { createIdeaVersion(ideaId: $id, changeSummary: $s) { versionId } }",
            ["id": .string(ideaId), "s": .optional(summary)])
    }

    static func restoreVersion(ideaId: String, versionId: String) async throws {
        let _: Bool = try await field(
            "mutation RV($id: String!, $v: String!) { restoreIdeaVersion(ideaId: $id, versionId: $v) }",
            ["id": .string(ideaId), "v": .string(versionId)])
    }

    static func portfolio() async throws -> [PortfolioItem] {
        try await field(
            """
            query Portfolio {
              myPortfolio { investmentId ideaId ideaTitle ideaDescription cashAmount sweatEquityValue equityPercentage status createdAt }
            }
            """)
    }

    static func investments(ideaId: String) async throws -> [Investment] {
        try await field(
            """
            query Inv($id: String!) {
              ideaInvestments(ideaId: $id) {
                investmentId investorId cashAmount sweatEquityHours sweatEquityValue equityPercentage investmentType role status notes createdAt investorName investorAvatar
              }
            }
            """, ["id": .string(ideaId)])
    }

    static func capTable(ideaId: String) async throws -> [CapTableEntry] {
        try await field(
            """
            query Cap($id: String!) {
              ideaCapTable(ideaId: $id) { entryId stakeholderType equityPercentage shareClass vestingStatus vestedPercentage stakeholderName }
            }
            """, ["id": .string(ideaId)])
    }

    static func createInvestment(
        ideaId: String, cash: Double, hours: Double, hourlyRate: Double, equity: Double, type: String, role: String?, notes: String?
    ) async throws {
        struct R: Decodable, Sendable { let investmentId: String }
        let _: R = try await field(
            "mutation CI($i: CreateInvestmentInput!) { createInvestment(input: $i) { investmentId } }",
            [
                "i": [
                    "ideaId": .string(ideaId), "cashAmount": .double(cash), "sweatEquityHours": .double(hours),
                    "hourlyRate": .double(hourlyRate), "equityPercentage": .double(equity),
                    "investmentType": .string(type), "role": .optional(role), "notes": .optional(notes),
                ]
            ])
    }

    static func updateInvestmentStatus(id: String, status: String) async throws {
        let _: Bool = try await field(
            "mutation US($id: String!, $s: String!) { updateInvestmentStatus(investmentId: $id, status: $s) }",
            ["id": .string(id), "s": .string(status)])
    }

    // MARK: Pitch shorts

    static func reels(limit: Int = 30) async throws -> [PitchReel] {
        try await field("query Reels($l: Int!) { pitchReelsFeed(limit: $l) { \(reelFields) } }", ["l": .int(limit)])
    }

    static func setLike(reelId: String, liked: Bool) async throws -> LikeResult {
        try await field(
            "mutation Like($r: String!, $l: Boolean!) { togglePitchReelLike(reelId: $r, liked: $l) { liked likeCount } }",
            ["r": .string(reelId), "l": .bool(liked)])
    }

    static func setReshare(reelId: String, reshared: Bool) async throws -> ShareResult {
        try await field(
            "mutation Share($r: String!, $s: Boolean!) { resharePitchReel(reelId: $r, reshared: $s) { reshared shareCount } }",
            ["r": .string(reelId), "s": .bool(reshared)])
    }

    private static let commentFields = "commentId authorName authorHandle authorAvatar body createdAt isMine"

    static func comments(reelId: String) async throws -> [PitchReelComment] {
        try await field(
            "query Comments($r: String!) { pitchReelComments(reelId: $r) { \(commentFields) } }", ["r": .string(reelId)])
    }

    static func addComment(reelId: String, body: String) async throws -> PitchReelComment {
        struct R: Decodable, Sendable { let comment: PitchReelComment }
        let r: R = try await field(
            "mutation AddComment($r: String!, $b: String!) { createPitchReelComment(reelId: $r, body: $b) { comment { \(commentFields) } } }",
            ["r": .string(reelId), "b": .string(body)])
        return r.comment
    }

    static func toggleFollow(userId: String) async throws -> FollowResult {
        try await field(
            "mutation Follow($u: String!) { toggleFollow(followedId: $u) { following followedId } }", ["u": .string(userId)])
    }

    // MARK: Inbox

    static func inbox() async throws -> [InboxConversation] {
        try await field("query Inbox { myInbox(limit: 100) { \(inboxConversationFields) } }")
    }

    static func thread(_ id: String) async throws -> InboxThread {
        try await field(
            """
            query Thread($id: String!) {
              inboxConversation(conversationId: $id) {
                conversation { \(inboxConversationFields) }
                items { kind key at messageId isMine senderName sentAt subject body { text url } attachmentCount quotedHistoryHidden groupStart groupEnd }
              }
            }
            """, ["id": .string(id)])
    }

    static func reply(conversationId: String, text: String, clientId: String) async throws {
        let _: Bool = try await field(
            "mutation Reply($c: String!, $t: String!, $k: String) { replyInInbox(conversationId: $c, content: $t, clientId: $k) }",
            ["c": .string(conversationId), "t": .string(text), "k": .string(clientId)])
    }

    static func markRead(_ conversationId: String) async throws {
        let _: Bool = try await field(
            "mutation Read($c: String!) { markInboxRead(conversationId: $c) }", ["c": .string(conversationId)])
    }

    static func unreadCount() async throws -> Int {
        struct R: Decodable, Sendable { let count: Int }
        let r: R = try await field("query Unread { unreadMessageCount { count } }")
        return r.count
    }

    static func ideaOwner(_ ideaId: String) async throws -> IdeaOwner? {
        try await field(
            """
            query Owner($id: String!) {
              ideaOwner(ideaId: $id) { userId username firstName lastName bio profilePictureUrl canMessage openMediaHandle }
            }
            """, ["id": .string(ideaId)])
    }

    static func startConversation(with userId: String, ideaId: String?) async throws -> Conversation {
        try await field(
            "mutation Start($u: String!, $i: String) { startConversation(otherUserId: $u, ideaId: $i) { conversationId } }",
            ["u": .string(userId), "i": .optional(ideaId)])
    }

    // MARK: Search

    static func search(_ query: String) async throws -> SearchResults {
        try await field(
            """
            query Search($q: String!) {
              universalSearch(query: $q, limit: 8) {
                query assistantSummary
                myIdeas { ideaId title snippet createdAt userId isPublished creatorName }
                publishedIdeas { ideaId title snippet createdAt userId isPublished creatorName }
              }
            }
            """, ["q": .string(query)])
    }
}
