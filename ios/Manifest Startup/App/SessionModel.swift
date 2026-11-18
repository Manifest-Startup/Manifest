import Foundation
import Observation

/// Who is signed in, and the transitions between signed out / guest / member.
@Observable
final class SessionModel {
    enum Phase: Equatable {
        case launching
        case signedOut
        case signedIn
    }

    private(set) var phase: Phase = .launching
    private(set) var user: User?
    private(set) var isWorking = false
    var error: String?

    private let authenticator = WebAuthenticator()

    var isGuest: Bool { user?.isGuest ?? false }

    init() {
        SessionEvents.shared.onSignedOut = { [weak self] in
            guard let self, self.phase == .signedIn else { return }
            self.resetLocalState()
            self.error = APIError.unauthorized.errorDescription
        }
    }

    /// Restore a saved session: paint from cache at once, then confirm with the server.
    func restore() async {
        guard await TokenStore.shared.current != nil else {
            phase = .signedOut
            return
        }
        if let cached = await DiskCache.load(User.self, key: "me") {
            user = cached
            phase = .signedIn
        }
        do {
            let me = try await API.me()
            user = me
            DiskCache.save(me, key: "me")
            phase = .signedIn
        } catch APIError.unauthorized {
            resetLocalState()
        } catch {
            // Offline with a valid token: stay signed in on cached data.
            if user == nil { phase = .signedOut }
        }
    }

    func signIn() async {
        guard !isWorking else { return }
        isWorking = true
        error = nil
        defer { isWorking = false }
        do {
            let clientID = try await OAuth.clientID(deviceName: AppConfig.deviceName)
            let pkce = OAuth.PKCE()
            let callback = try await authenticator.authenticate(url: OAuth.authorizeURL(clientID: clientID, pkce: pkce))
            let code = try OAuth.code(from: callback, expectedState: pkce.state)
            let credentials = try await OAuth.exchange(code: code, pkce: pkce, clientID: clientID)
            await TokenStore.shared.store(credentials)
            try await loadUser()
            Haptics.success()
        } catch APIError.cancelled {
            // The person closed the sheet; nothing to report.
        } catch {
            self.error = error.localizedDescription
            Haptics.error()
        }
    }

    /// A throwaway workspace to try Manifest before signing in.
    func continueAsGuest() async {
        guard !isWorking else { return }
        isWorking = true
        error = nil
        defer { isWorking = false }
        do {
            let guest = try await API.startGuestSession()
            await TokenStore.shared.store(
                Credentials(accessToken: guest.token, refreshToken: nil, expiresAt: .now.addingTimeInterval(7 * 86_400), isGuest: true)
            )
            try await loadUser()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func signOut() async {
        let credentials = await TokenStore.shared.current
        if let credentials {
            if credentials.isGuest {
                try? await API.logout()
            } else {
                await OAuth.revoke(token: credentials.refreshToken ?? credentials.accessToken,
                                   clientID: await TokenStore.shared.clientID)
            }
        }
        resetLocalState()
    }

    func update(_ user: User) {
        self.user = user
        DiskCache.save(user, key: "me")
    }

    private func loadUser() async throws {
        let me = try await API.me()
        update(me)
        phase = .signedIn
    }

    private func resetLocalState() {
        Task { await TokenStore.shared.store(nil) }
        DiskCache.clear()
        user = nil
        phase = .signedOut
    }
}
