import Foundation

/// OAuth tokens for this device. Access tokens last 24 h; refresh tokens rotate on use.
nonisolated struct Credentials: Codable, Sendable, Equatable {
    var accessToken: String
    var refreshToken: String?
    var expiresAt: Date
    /// Guest workspaces get a plain session token and cannot refresh.
    var isGuest: Bool = false

    var isExpiringSoon: Bool { expiresAt.timeIntervalSinceNow < 120 }
}

/// Owns the credentials and coalesces concurrent refreshes, so a burst of
/// requests that all hit an expired token triggers exactly one refresh.
actor TokenStore {
    static let shared = TokenStore()

    private static let credentialsKey = "credentials.v1"
    private static let clientKey = "oauth.client.v1"

    private var credentials: Credentials?
    private var refreshTask: Task<Credentials, Error>?

    init() {
        credentials = Keychain.value(Credentials.self, for: Self.credentialsKey)
        #if DEBUG
        if Fixtures.isEnabled && !DemoScreen.is(.signIn) { credentials = Fixtures.demoCredentials }
        #endif
    }

    var current: Credentials? { credentials }

    func store(_ new: Credentials?) {
        credentials = new
        Keychain.set(value: new, for: Self.credentialsKey)
    }

    var clientID: String? {
        Keychain.data(for: Self.clientKey).flatMap { String(data: $0, encoding: .utf8) }
    }

    func storeClientID(_ id: String?) {
        Keychain.set(id?.data(using: .utf8), for: Self.clientKey)
    }

    /// A usable access token, refreshing first when it is about to expire.
    func validAccessToken() async throws -> String? {
        guard let credentials else { return nil }
        if credentials.isExpiringSoon, credentials.refreshToken != nil {
            return try await refresh().accessToken
        }
        return credentials.accessToken
    }

    /// Refresh once even if many callers ask at the same time.
    @discardableResult
    func refresh() async throws -> Credentials {
        if let refreshTask { return try await refreshTask.value }
        guard let refreshToken = credentials?.refreshToken, let clientID else {
            throw APIError.unauthorized
        }
        let task = Task { try await OAuth.refresh(refreshToken: refreshToken, clientID: clientID) }
        refreshTask = task
        defer { refreshTask = nil }
        do {
            let fresh = try await task.value
            store(fresh)
            return fresh
        } catch let error as APIError where error == .unauthorized {
            store(nil)
            throw error
        }
    }
}
