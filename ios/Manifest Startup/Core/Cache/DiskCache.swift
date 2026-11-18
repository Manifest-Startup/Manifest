import Foundation

/// Last-known responses on disk, so every tab paints instantly on launch and
/// refreshes in the background (stale-while-revalidate). Cleared on sign-out.
nonisolated enum DiskCache {
    private static let directory: URL = {
        let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        let dir = base.appending(path: "ManifestCache", directoryHint: .isDirectory)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }()

    private static func url(_ key: String) -> URL { directory.appending(path: "\(key).json") }

    static func load<T: Decodable & Sendable>(_ type: T.Type, key: String) async -> T? {
        await Task.detached(priority: .userInitiated) {
            guard let data = try? Data(contentsOf: url(key)) else { return nil }
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .secondsSince1970
            return try? decoder.decode(T.self, from: data)
        }.value
    }

    static func save<T: Encodable & Sendable>(_ value: T, key: String) {
        Task.detached(priority: .utility) {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .secondsSince1970
            guard let data = try? encoder.encode(value) else { return }
            try? data.write(to: url(key), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        }
    }

    static func clear() {
        try? FileManager.default.removeItem(at: directory)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }
}
