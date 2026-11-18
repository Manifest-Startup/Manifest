import AuthenticationServices
import CryptoKit
import Foundation
#if os(macOS)
import AppKit
#else
import UIKit
#endif

/// Native sign-in through Manifest's OAuth 2.1 server (RFC 8252: public client,
/// PKCE S256, private-use URI scheme). The web page handles "Continue with Open
/// Media", so the app never sees a password.
nonisolated enum OAuth {
    static let callbackScheme = "com.manifeststartup.ios"
    static let redirectURI = "\(callbackScheme):/oauth/callback"

    private struct Registration: Decodable { let client_id: String }
    private struct TokenResponse: Decodable {
        let access_token: String
        let refresh_token: String?
        let expires_in: Double?
    }
    private struct OAuthErrorBody: Decodable {
        let error: String
        let error_description: String?
    }

    /// Stateless dynamic registration (RFC 7591). The client_id is signed by the
    /// server, so it is cached and reused for the life of the install.
    static func clientID(deviceName: String) async throws -> String {
        if let cached = await TokenStore.shared.clientID { return cached }
        var request = URLRequest(url: AppConfig.baseURL.appending(path: "api/oauth/register"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "client_name": "Manifest for \(deviceName)",
            "redirect_uris": [redirectURI],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        ])
        let data = try await send(request)
        let id = try JSONDecoder().decode(Registration.self, from: data).client_id
        await TokenStore.shared.storeClientID(id)
        return id
    }

    struct PKCE {
        let verifier: String
        let challenge: String
        let state: String

        init() {
            verifier = Self.random(48)
            let digest = SHA256.hash(data: Data(verifier.utf8))
            challenge = Data(digest).base64URL
            state = Self.random(16)
        }

        private static func random(_ count: Int) -> String {
            var bytes = [UInt8](repeating: 0, count: count)
            _ = SecRandomCopyBytes(kSecRandomDefault, count, &bytes)
            return Data(bytes).base64URL
        }
    }

    static func authorizeURL(clientID: String, pkce: PKCE) -> URL {
        var components = URLComponents(
            url: AppConfig.baseURL.appending(path: "api/oauth/authorize"),
            resolvingAgainstBaseURL: false
        )!
        components.queryItems = [
            .init(name: "client_id", value: clientID),
            .init(name: "redirect_uri", value: redirectURI),
            .init(name: "response_type", value: "code"),
            .init(name: "code_challenge", value: pkce.challenge),
            .init(name: "code_challenge_method", value: "S256"),
            .init(name: "scope", value: "manifest"),
            .init(name: "state", value: pkce.state),
        ]
        return components.url!
    }

    /// Reads the code from the callback, rejecting a mismatched state.
    static func code(from callback: URL, expectedState: String) throws -> String {
        let items = URLComponents(url: callback, resolvingAgainstBaseURL: false)?.queryItems ?? []
        func value(_ name: String) -> String? { items.first { $0.name == name }?.value }
        if let error = value("error") {
            if error == "access_denied" { throw APIError.cancelled }
            throw APIError.server(value("error_description") ?? "Sign-in failed (\(error)).")
        }
        guard value("state") == expectedState else {
            throw APIError.server("Sign-in response did not match this request. Try again.")
        }
        guard let code = value("code"), !code.isEmpty else {
            throw APIError.server("Sign-in did not return a code.")
        }
        return code
    }

    static func exchange(code: String, pkce: PKCE, clientID: String) async throws -> Credentials {
        try await token([
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": pkce.verifier,
            "redirect_uri": redirectURI,
            "client_id": clientID,
        ])
    }

    static func refresh(refreshToken: String, clientID: String) async throws -> Credentials {
        try await token([
            "grant_type": "refresh_token",
            "refresh_token": refreshToken,
            "client_id": clientID,
        ])
    }

    static func revoke(token: String, clientID: String?) async {
        var request = URLRequest(url: AppConfig.baseURL.appending(path: "api/oauth/revoke"))
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        request.httpBody = formBody(["token": token, "client_id": clientID ?? ""])
        _ = try? await URLSession.shared.data(for: request)
    }

    private static func token(_ form: [String: String]) async throws -> Credentials {
        var request = URLRequest(url: AppConfig.baseURL.appending(path: "api/oauth/token"))
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        request.httpBody = formBody(form)
        let data = try await send(request)
        let body = try JSONDecoder().decode(TokenResponse.self, from: data)
        return Credentials(
            accessToken: body.access_token,
            refreshToken: body.refresh_token,
            expiresAt: Date().addingTimeInterval(body.expires_in ?? 86_400)
        )
    }

    private static func send(_ request: URLRequest) async throws -> Data {
        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            throw APIError.offline
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            let body = try? JSONDecoder().decode(OAuthErrorBody.self, from: data)
            if body?.error == "invalid_grant" || body?.error == "invalid_client" || status == 401 {
                if body?.error == "invalid_client" { await TokenStore.shared.storeClientID(nil) }
                throw APIError.unauthorized
            }
            throw APIError.server(body?.error_description ?? "Sign-in failed (HTTP \(status)).")
        }
        return data
    }

    private static func formBody(_ form: [String: String]) -> Data {
        var allowed = CharacterSet.alphanumerics
        allowed.insert(charactersIn: "-._~")
        return form.map { key, value in
            "\(key)=\(value.addingPercentEncoding(withAllowedCharacters: allowed) ?? value)"
        }
        .joined(separator: "&")
        .data(using: .utf8)!
    }
}

nonisolated extension Data {
    var base64URL: String {
        base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}

/// Presents the system web sheet and returns the callback URL.
@MainActor
final class WebAuthenticator: NSObject, ASWebAuthenticationPresentationContextProviding {
    private var session: ASWebAuthenticationSession?

    func authenticate(url: URL) async throws -> URL {
        try await withCheckedThrowingContinuation { continuation in
            let session = ASWebAuthenticationSession(
                url: url,
                callback: .customScheme(OAuth.callbackScheme)
            ) { callbackURL, error in
                if let callbackURL {
                    continuation.resume(returning: callbackURL)
                } else if let error = error as? ASWebAuthenticationSessionError,
                    error.code == .canceledLogin
                {
                    continuation.resume(throwing: APIError.cancelled)
                } else {
                    continuation.resume(throwing: APIError.server(error?.localizedDescription ?? "Sign-in failed."))
                }
            }
            session.presentationContextProvider = self
            // Reuse the Safari session so people already signed in on the web skip the login step.
            session.prefersEphemeralWebBrowserSession = false
            self.session = session
            if !session.start() {
                continuation.resume(throwing: APIError.server("Could not open the sign-in sheet."))
            }
        }
    }

    nonisolated func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        MainActor.assumeIsolated {
            #if os(macOS)
            NSApplication.shared.keyWindow ?? NSApplication.shared.windows.first ?? ASPresentationAnchor()
            #else
            let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
            let scene = scenes.first { $0.activationState == .foregroundActive } ?? scenes.first
            return scene?.keyWindow ?? scene?.windows.first ?? ASPresentationAnchor(windowScene: scene!)
            #endif
        }
    }
}
