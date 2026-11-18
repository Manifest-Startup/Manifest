import Foundation
import Testing

@testable import Manifest_Startup

@Suite("OAuth")
struct OAuthTests {
    @Test func pkceChallengeIsS256OfVerifier() {
        let pkce = OAuth.PKCE()
        #expect((43...128).contains(pkce.verifier.count))
        #expect(pkce.challenge.count == 43)
        #expect(!pkce.challenge.contains("="))
        #expect(!pkce.challenge.contains("+"))
        #expect(!pkce.challenge.contains("/"))
    }

    @Test func authorizeURLCarriesPKCEAndRedirect() throws {
        let pkce = OAuth.PKCE()
        let url = OAuth.authorizeURL(clientID: "mcp_abc", pkce: pkce)
        let items = try #require(URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems)
        func value(_ name: String) -> String? { items.first { $0.name == name }?.value }
        #expect(url.path == "/api/oauth/authorize")
        #expect(value("code_challenge_method") == "S256")
        #expect(value("code_challenge") == pkce.challenge)
        #expect(value("redirect_uri") == OAuth.redirectURI)
        #expect(value("state") == pkce.state)
    }

    @Test func callbackReturnsCodeWhenStateMatches() throws {
        let url = URL(string: "\(OAuth.callbackScheme):/oauth/callback?code=abc123&state=s1&iss=x")!
        #expect(try OAuth.code(from: url, expectedState: "s1") == "abc123")
    }

    @Test func callbackRejectsMismatchedState() {
        let url = URL(string: "\(OAuth.callbackScheme):/oauth/callback?code=abc123&state=evil")!
        #expect(throws: APIError.self) { try OAuth.code(from: url, expectedState: "s1") }
    }

    @Test func deniedConsentIsTreatedAsCancel() {
        let url = URL(string: "\(OAuth.callbackScheme):/oauth/callback?error=access_denied&state=s1")!
        #expect(throws: APIError.cancelled) { try OAuth.code(from: url, expectedState: "s1") }
    }
}

@Suite("Networking")
struct NetworkingTests {
    @Test(arguments: [
        "2026-11-18T08:59:02.123456+00:00",
        "2026-11-18T08:59:02Z",
        "2026-11-18T08:59:02.123Z",
        "2026-11-18T08:59:02.123456",
        "2026-11-18 08:59:02",
    ])
    func parsesBackendDates(_ raw: String) throws {
        let date = try #require(DateParser.parse(raw))
        let parts = Calendar(identifier: .gregorian).dateComponents(in: TimeZone(identifier: "UTC")!, from: date)
        #expect(parts.year == 2026 && parts.month == 11 && parts.day == 18 && parts.hour == 8)
    }

    @Test func mapsAuthErrors() {
        #expect(APIError.from(message: "Authentication required for Query.ideas") == .unauthorized)
        #expect(APIError.from(message: "Add your OpenAI API key to continue") == .needsAIKey)
        #expect(APIError.from(message: "Idea not found") == .server("Idea not found"))
    }

    @Test func encodesVariablesWithoutAny() throws {
        let value: JSONValue = ["a": 1, "b": "x", "c": .null, "d": [true, 2.5]]
        let data = try JSONEncoder().encode(value)
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(object["a"] as? Int == 1)
        #expect(object["b"] as? String == "x")
        #expect(object["c"] is NSNull)
        #expect((object["d"] as? [Any])?.count == 2)
    }
}

@Suite("Markdown")
struct MarkdownTests {
    @Test func parsesDocumentStructure() {
        let blocks = MarkdownBlock.parse("""
            # Title
            Intro **bold** line
            continues here.

            - one
            - two
            1. first

            > quote

            | A | B |
            |---|---|
            | 1 | 2 |

            ---
            ```
            code
            ```
            """)
        var headings = 0, paragraphs = 0, bullets = 0, quotes = 0, tables = 0, rules = 0, code = 0
        for block in blocks {
            switch block {
            case .heading: headings += 1
            case .paragraph: paragraphs += 1
            case .bullet: bullets += 1
            case .quote: quotes += 1
            case .table(_, let rows): tables += 1; #expect(rows.count == 1)
            case .rule: rules += 1
            case .code(let text): code += 1; #expect(text == "code")
            }
        }
        #expect(headings == 1)
        #expect(paragraphs == 1)
        #expect(bullets == 3)
        #expect(quotes == 1)
        #expect(tables == 1)
        #expect(rules == 1)
        #expect(code == 1)
    }

    @Test func hashWithoutSpaceIsParagraph() {
        let blocks = MarkdownBlock.parse("#hashtag")
        guard case .paragraph = blocks.first else {
            Issue.record("Expected a paragraph")
            return
        }
    }
}

@Suite("Models")
struct ModelTests {
    @Test func ideaSummaryCountsDocuments() {
        let idea = Idea(
            ideaId: "1", userId: "u", title: "T", description: "D", createdAt: .now,
            pitchDeck: "# Deck", productRequirementsDocument: "  ", provisionalPatent: nil,
            businessModelCanvas: nil, similarIdeas: "x", isPublished: false, requiredSkills: [])
        #expect(idea.summary.generatedAssetCount == 2)
        #expect(idea.content(for: .prd) == nil)
    }

    @Test func displayNameFallsBack() {
        var user = User(userId: "u", email: "ada@example.com", createdAt: nil, username: nil, firstName: nil,
                        lastName: nil, country: nil, bio: nil, state: nil, profilePictureUrl: nil, skills: [])
        #expect(user.displayName == "ada")
        user.firstName = "Ada"
        user.lastName = "Lovelace"
        #expect(user.displayName == "Ada Lovelace")
        #expect(user.initials == "AL")
    }

    @Test func guestEmailIsDetected() {
        let guest = User(userId: "g", email: "guest+abc@guest.manifest", createdAt: nil, username: nil, firstName: nil,
                         lastName: nil, country: nil, bio: nil, state: nil, profilePictureUrl: nil, skills: [])
        #expect(guest.isGuest)
    }

    @Test func canvasOrderCoversEverySection() {
        #expect(Set(CanvasSection.readingOrder) == Set(CanvasSection.allCases))
    }

    @Test func reelShareURLUsesCanonicalPath() {
        let url = PitchReel.shareURL(for: "abc")
        #expect(url.absoluteString == "https://manifeststartup.com/pitch-reels?clip=abc")
    }
}
