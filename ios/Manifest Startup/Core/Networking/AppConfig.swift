import Foundation
#if os(macOS)
import AppKit
#else
import UIKit
#endif

/// Build-time and device facts. `MANIFEST_API_URL` (scheme env var) points the
/// app at a local backend; release builds always use production.
nonisolated enum AppConfig {
    static let baseURL: URL = {
        #if DEBUG
        if let raw = ProcessInfo.processInfo.environment["MANIFEST_API_URL"], let url = URL(string: raw) {
            return url
        }
        #endif
        return URL(string: "https://manifeststartup.com")!
    }()

    static var graphQLURL: URL { baseURL.appending(path: "graphql") }

    /// Shown on the consent page and under Account → Sessions.
    @MainActor static var deviceName: String {
        #if os(macOS)
        return "Mac"
        #elseif os(visionOS)
        return "Vision Pro"
        #else
        return UIDevice.current.userInterfaceIdiom == .pad ? "iPad" : "iPhone"
        #endif
    }

    static let appVersion: String = {
        let info = Bundle.main.infoDictionary
        let version = info?["CFBundleShortVersionString"] as? String ?? "1.0"
        let build = info?["CFBundleVersion"] as? String ?? "1"
        return "\(version) (\(build))"
    }()

    static let isUITesting = ProcessInfo.processInfo.arguments.contains("-ui-testing")
}
