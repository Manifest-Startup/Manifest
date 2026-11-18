import Foundation
import Security

/// Minimal generic-password Keychain wrapper. Tokens never touch UserDefaults.
nonisolated enum Keychain {
    private static let service = "com.manifeststartup.app"

    static func data(for key: String) -> Data? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: AnyObject?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess else { return nil }
        return result as? Data
    }

    static func set(_ data: Data?, for key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
        SecItemDelete(query as CFDictionary)
        guard let data else { return }
        var attributes = query
        attributes[kSecValueData as String] = data
        attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemAdd(attributes as CFDictionary, nil)
    }

    static func value<T: Decodable>(_ type: T.Type, for key: String) -> T? {
        data(for: key).flatMap { try? JSONDecoder().decode(T.self, from: $0) }
    }

    static func set<T: Encodable>(value: T?, for key: String) {
        set(value.flatMap { try? JSONEncoder().encode($0) }, for: key)
    }
}
