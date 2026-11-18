#if DEBUG
import Foundation

/// Synthetic data for previews, UI tests and design review (`-demo` launch
/// argument). Debug builds only; nothing here talks to a server.
nonisolated enum Fixtures {
    static var isEnabled: Bool { ProcessInfo.processInfo.arguments.contains("-demo") }

    static let demoCredentials = Credentials(accessToken: "demo", refreshToken: "demo", expiresAt: .distantFuture)

    private static let now = Date()
    private static func iso(_ daysAgo: Double) -> String {
        now.addingTimeInterval(-daysAgo * 86_400).formatted(.iso8601)
    }

    /// The `data` object for an operation: `{ rootField: value }`.
    static func data(for query: String) -> [String: Any] {
        let name = query.split(whereSeparator: { " ({".contains($0) }).dropFirst().first.map(String.init) ?? ""
        let afterBrace = query.split(separator: "{", maxSplits: 1).dropFirst().first ?? ""
        let field = afterBrace.split(whereSeparator: { " ({\n".contains($0) }).first.map(String.init) ?? name
        let all = candidates(for: name)
        return [field: all[field] ?? true]
    }

    private static func candidates(for name: String) -> [String: Any] {
        switch name {
        case "Me", "UpdateAccount": return ["me": user, "updateAccount": user]
        case "Ideas": return ["ideas": ideas]
        case "Shared": return ["mySharedIdeas": [["ideaId": "shared-1", "title": "Open-source grid batteries", "description": "Community-owned storage.", "userRole": "editor", "createdAt": iso(12)]]]
        case "Invites": return ["myCollaborationInvitations": [] as [Any]]
        case "Idea", "Update", "Create": return ["idea": idea, "updateIdea": idea, "createIdea": idea]
        case "BMC": return ["bmcSections": canvas]
        case "Reels": return ["pitchReelsFeed": reels]
        case "Comments": return ["pitchReelComments": [comment("Love the wedge into clinics first.", 0.1), comment("What does onboarding look like?", 0.4)]]
        case "Inbox": return ["myInbox": inbox]
        case "Thread": return ["inboxConversation": ["conversation": inbox[0], "items": thread]]
        case "Unread": return ["unreadMessageCount": ["count": 2]]
        case "Portfolio": return ["myPortfolio": portfolio]
        case "AiKey": return ["aiKeyStatus": ["configured": true, "source": "user", "last4": "9fQa"]]
        case "Stats": return ["userSocialStats": ["followerCount": 1284, "followingCount": 211, "isFollowing": false]]
        case "OML": return ["openMediaLink": ["enabled": true, "linked": true, "needsReconnect": false, "handle": "avery", "displayName": "Avery Chen", "avatarUrl": NSNull(), "connectUrl": "/api/auth/open-media/start"]]
        case "Integrations": return ["integrations": [] as [Any]]
        case "Sessions": return ["mySessions": [
            ["sessionId": "s1", "current": true, "createdAt": iso(2), "lastSeenAt": iso(0), "requestIp": "203.0.113.4", "userAgent": "Manifest for iPhone", "kind": "agent"],
            ["sessionId": "s2", "current": false, "createdAt": iso(20), "lastSeenAt": iso(1), "requestIp": "198.51.100.7", "userAgent": "Mozilla/5.0 (Macintosh) Safari/605", "kind": "browser"],
        ]]
        case "C": return ["ideaCollaborators": [
            ["collaboratorId": "c1", "userId": "u2", "role": "editor", "status": "accepted", "userEmail": "sam@example.com", "userName": "Sam Okafor", "userAvatar": NSNull()],
            ["collaboratorId": "c2", "userId": "u3", "role": "viewer", "status": "pending", "userEmail": "lee@example.com", "userName": NSNull(), "userAvatar": NSNull()],
        ]]
        case "V": return ["ideaVersions": [
            ["versionId": "v2", "versionNumber": 2, "title": "Clinic Copilot", "description": "", "createdAt": iso(1), "changeSummary": "Edited on iPhone", "creatorName": "Avery", "versionKind": "manual"],
            ["versionId": "v1", "versionNumber": 1, "title": "Clinic notes AI", "description": "", "createdAt": iso(6), "changeSummary": "Created", "creatorName": "Avery", "versionKind": "auto"],
        ]]
        case "Cap": return ["ideaCapTable": [
            ["entryId": "e1", "stakeholderType": "founder", "equityPercentage": 72, "shareClass": "common", "vestingStatus": "vesting", "vestedPercentage": 25, "stakeholderName": "Avery Chen"],
            ["entryId": "e2", "stakeholderType": "investor", "equityPercentage": 18, "shareClass": "preferred", "vestingStatus": "none", "vestedPercentage": 100, "stakeholderName": "Northwind Angels"],
            ["entryId": "e3", "stakeholderType": "contributor", "equityPercentage": 6, "shareClass": "common", "vestingStatus": "vesting", "vestedPercentage": 10, "stakeholderName": "Sam Okafor"],
        ]]
        case "Inv": return ["ideaInvestments": [
            ["investmentId": "i1", "investorId": "u9", "cashAmount": 50000, "sweatEquityHours": 0, "sweatEquityValue": 0, "equityPercentage": 18, "investmentType": "cash", "role": NSNull(), "status": "confirmed", "notes": NSNull(), "createdAt": iso(30), "investorName": "Northwind Angels", "investorAvatar": NSNull()],
            ["investmentId": "i2", "investorId": "u2", "cashAmount": 0, "sweatEquityHours": 240, "sweatEquityValue": 12000, "equityPercentage": 6, "investmentType": "sweat_equity", "role": "CTO", "status": "pending", "notes": NSNull(), "createdAt": iso(9), "investorName": "Sam Okafor", "investorAvatar": NSNull()],
        ]]
        case "Search": return ["universalSearch": [
            "query": "clinic", "assistantSummary": "Two of your ideas and one published idea mention **clinics**.",
            "myIdeas": [["ideaId": "idea-1", "title": "Clinic Copilot", "snippet": "Ambient notes for small clinics…", "createdAt": iso(6), "userId": "me", "isPublished": true, "creatorName": NSNull()]],
            "publishedIdeas": [["ideaId": "p-1", "title": "Rural telehealth kiosks", "snippet": "Solar-powered booths that connect villages to…", "createdAt": iso(40), "userId": "u7", "isPublished": true, "creatorName": "Priya N."]],
        ]]
        case "QS", "SQ", "CQ": return ["startIdeaQualification": qualification, "continueIdeaQualification": qualification, "myIdeaQualificationSessions": [qualification]]
        case "Pub": return ["togglePublishIdea": ["ideaId": "idea-1", "isPublished": false]]
        case "Like": return ["togglePitchReelLike": ["liked": true, "likeCount": 129]]
        default: return [:]
        }
    }

    private static var user: [String: Any] { [
        "userId": "me", "email": "avery@example.com", "createdAt": iso(90), "username": "avery",
        "firstName": "Avery", "lastName": "Chen", "country": "United States", "bio": "Building tools for small clinics.",
        "state": NSNull(), "profilePictureUrl": NSNull(), "skills": ["Product", "Swift", "Healthcare"],
    ] }

    private static var ideas: [[String: Any]] { [
        ["ideaId": "idea-1", "userId": "me", "title": "Clinic Copilot", "description": "Ambient note-taking for independent clinics, so doctors look at patients instead of screens.", "hasDescription": true, "createdAt": iso(6), "isPublished": true, "generatedAssetCount": 3],
        ["ideaId": "idea-2", "userId": "me", "title": "Tool library for apartment buildings", "description": "Residents share drills, ladders and sewing machines through a lockbox in the lobby.", "hasDescription": true, "createdAt": iso(15), "isPublished": false, "generatedAssetCount": 1],
        ["ideaId": "idea-3", "userId": "me", "title": "Carbon receipts", "description": "Every card purchase shows its footprint and a cheaper, cleaner swap.", "hasDescription": true, "createdAt": iso(41), "isPublished": false, "generatedAssetCount": 0],
    ] }

    private static var idea: [String: Any] { [
        "ideaId": "idea-1", "userId": "me", "title": "Clinic Copilot",
        "description": "Ambient note-taking for independent clinics, so doctors look at patients instead of screens. Starts with family practices of 2–10 doctors.",
        "createdAt": iso(6),
        "pitchDeck": "# Clinic Copilot\n\n## Problem\nDoctors in small practices spend **two hours a day** on notes.\n\n- Burnout is the #1 reason they leave\n- Scribes cost $40k a year\n\n## Solution\nAn ambient assistant that listens, drafts the note and files it to the EHR.\n\n> \"I got my evenings back.\" — pilot physician\n\n## Market\n| Segment | Practices | ARPA |\n|---|---|---|\n| Family | 92,000 | $3,600 |\n| Pediatrics | 18,000 | $3,000 |\n\n## Business model\n1. $300 per doctor per month\n2. Free 30-day pilot\n",
        "productRequirementsDocument": "# PRD\n\n## Goals\n- Draft a note within 30 seconds of the visit ending\n- Zero setup beyond a phone on the desk\n\n## Non-goals\n- Billing codes in v1\n",
        "provisionalPatent": NSNull(),
        "businessModelCanvas": NSNull(),
        "similarIdeas": "# Similar Landscape\n\n## Comparable Companies\n### Abridge\n- Summary: Enterprise ambient notes\n- Why Similar: Same core job\n",
        "isPublished": true, "requiredSkills": ["Speech AI", "EHR integration", "Sales to clinics"],
    ] }

    private static var canvas: [[String: Any]] { [
        ("customer_segments", "Independent family practices with 2–10 doctors in the US."),
        ("value_propositions", "Two hours a day back. Notes that read like the doctor wrote them."),
        ("channels", "Practice-management resellers, physician communities, referral credits."),
        ("customer_relationships", "White-glove onboarding, then self-serve."),
        ("revenue_streams", "$300 per doctor per month, annual discount."),
        ("key_resources", ""), ("key_activities", "Model tuning on specialty vocabulary; EHR connectors."),
        ("key_partners", ""), ("cost_structure", "Inference, compliance audits, onboarding staff."),
    ].map { name, content in
        ["sectionName": name, "content": content, "contentFormat": "markdown", "needsUserReview": name == "channels", "lastGeneratedAt": iso(2), "lastUserEditAt": NSNull()]
    } }

    private static func reel(_ id: String, _ title: String, _ subtitle: String, _ from: String, _ to: String, _ creator: String, liked: Bool) -> [String: Any] {
        [
            "reelId": id, "slug": id, "title": title, "subtitle": subtitle, "thesis": NSNull(), "description": NSNull(),
            "tags": ["healthtech", "ai"], "videoUrl": "https://devstreaming-cdn.apple.com/videos/streaming/examples/img_bipbop_adv_example_fmp4/master.m3u8",
            "posterUrl": NSNull(), "videoStatus": "ready", "accentFrom": from, "accentTo": to, "createdAt": iso(1), "ideaId": "idea-1",
            "creator": ["userId": "u-\(id)", "handle": creator.lowercased(), "name": creator, "role": "Founder", "initials": String(creator.prefix(1)), "avatar": NSNull(), "followerCount": 812, "isFollowing": false],
            "stats": ["likeCount": 128, "commentCount": 14, "shareCount": 9],
            "viewerState": ["liked": liked, "reshared": false],
        ]
    }

    private static var reels: [[String: Any]] { [
        reel("r1", "Clinic Copilot", "Doctors get two hours a day back.", "#0A84FF", "#5E5CE6", "Avery", liked: false),
        reel("r2", "Tool library", "Borrow a drill from the lobby, not the store.", "#FF9F0A", "#FF375F", "Jordan", liked: true),
    ] }

    private static func comment(_ body: String, _ daysAgo: Double) -> [String: Any] {
        ["commentId": UUID().uuidString, "authorName": "Riley Park", "authorHandle": "riley", "authorAvatar": NSNull(), "body": body, "createdAt": iso(daysAgo), "isMine": false]
    }

    private static var inbox: [[String: Any]] { [
        ["conversationId": "cv1", "kind": "direct", "source": "manifest", "title": "Sam Okafor", "initials": "SO", "avatarColor": "#5E5CE6", "avatarUrl": NSNull(), "group": false, "company": NSNull(), "preview": "Happy to take the EHR side. When can we talk?", "lastMessageAt": iso(0.02), "unreadCount": 2, "ideaId": "idea-1", "ideaTitle": "Clinic Copilot", "canReply": true],
        ["conversationId": "cv2", "kind": "direct", "source": "open_media", "title": "Northwind Angels", "initials": "NA", "avatarColor": "#30B0C7", "avatarUrl": NSNull(), "group": false, "company": "Northwind", "preview": "Sent over the term sheet.", "lastMessageAt": iso(2), "unreadCount": 0, "ideaId": NSNull(), "ideaTitle": NSNull(), "canReply": true],
    ] }

    private static var thread: [[String: Any]] { [
        ["kind": "day", "key": "d1", "at": iso(1), "messageId": NSNull(), "isMine": false, "senderName": NSNull(), "sentAt": NSNull(), "subject": NSNull(), "body": [["text": "Yesterday", "url": NSNull()]], "attachmentCount": 0, "quotedHistoryHidden": false, "groupStart": true, "groupEnd": true],
        ["kind": "message", "key": "m1", "at": iso(1), "messageId": "m1", "isMine": true, "senderName": "Avery", "sentAt": iso(1), "subject": NSNull(), "body": [["text": "Saw your work on FHIR connectors. Want to build Clinic Copilot with me?", "url": NSNull()]], "attachmentCount": 0, "quotedHistoryHidden": false, "groupStart": true, "groupEnd": true],
        ["kind": "message", "key": "m2", "at": iso(0.03), "messageId": "m2", "isMine": false, "senderName": "Sam", "sentAt": iso(0.03), "subject": NSNull(), "body": [["text": "Yes! I've wanted this for years.", "url": NSNull()]], "attachmentCount": 0, "quotedHistoryHidden": false, "groupStart": true, "groupEnd": false],
        ["kind": "message", "key": "m3", "at": iso(0.02), "messageId": "m3", "isMine": false, "senderName": "Sam", "sentAt": iso(0.02), "subject": NSNull(), "body": [["text": "Happy to take the EHR side. When can we talk?", "url": NSNull()]], "attachmentCount": 0, "quotedHistoryHidden": false, "groupStart": false, "groupEnd": true],
    ] }

    private static var portfolio: [[String: Any]] { [
        ["investmentId": "p1", "ideaId": "p-1", "ideaTitle": "Rural telehealth kiosks", "ideaDescription": NSNull(), "cashAmount": 25000, "sweatEquityValue": 0, "equityPercentage": 2.5, "status": "confirmed", "createdAt": iso(60)],
        ["investmentId": "p2", "ideaId": "p-2", "ideaTitle": "Open-source grid batteries", "ideaDescription": NSNull(), "cashAmount": 0, "sweatEquityValue": 9000, "equityPercentage": 1.2, "status": "pending", "createdAt": iso(20)],
        ["investmentId": "p3", "ideaId": "p-3", "ideaTitle": "Kids' coding clubs", "ideaDescription": NSNull(), "cashAmount": 5000, "sweatEquityValue": 2000, "equityPercentage": 0.8, "status": "confirmed", "createdAt": iso(110)],
    ] }

    private static var qualification: [String: Any] { [
        "id": "q1", "ideaId": "idea-1", "initialIdeaText": "Clinic Copilot", "status": "in_progress",
        "transcript": [["role": "assistant", "content": "Who feels this problem most sharply, and what do they do about it today?"]],
        "nextQuestion": "Who feels this problem most sharply?", "turnCount": 1, "qualificationScore": NSNull(),
        "qualificationExplanation": NSNull(), "ideaMarketNeed": NSNull(), "ideaFeasibility": NSNull(), "ideaDefensibility": NSNull(),
        "ideaRevenuePotential": NSNull(), "ideaTargetCustomer": NSNull(), "ideaRisks": NSNull(), "createdAt": iso(0),
    ] }
}
#endif

#if DEBUG
/// `-screen <name>` (with `-demo`) opens the app straight on one screen, for
/// screenshots and design review without driving the UI.
nonisolated enum DemoScreen: String {
    case ideas, idea, document, canvas, interview, newIdea, captable, shorts, inbox, thread, portfolio, search, account, signIn

    static var current: DemoScreen? {
        let args = ProcessInfo.processInfo.arguments
        guard let i = args.firstIndex(of: "-screen"), i + 1 < args.count else { return nil }
        return DemoScreen(rawValue: args[i + 1])
    }

    static func `is`(_ screen: DemoScreen) -> Bool { current == screen }
}
#endif
