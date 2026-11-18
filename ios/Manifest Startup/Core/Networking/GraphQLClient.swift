import Foundation

nonisolated enum APIError: Error, Equatable, LocalizedError {
    case unauthorized
    case offline
    case cancelled
    case needsAIKey
    case server(String)

    var errorDescription: String? {
        switch self {
        case .unauthorized: "Your session ended. Sign in again."
        case .offline: "You're offline. Check your connection and try again."
        case .cancelled: nil
        case .needsAIKey: "Add your OpenAI key in Account → AI to generate documents."
        case .server(let message): message
        }
    }

    /// Turns a GraphQL error message into something a person can act on.
    static func from(message: String) -> APIError {
        let lower = message.lowercased()
        if lower.contains("authentication required") || lower.contains("not authenticated")
            || lower.contains("session expired")
        {
            return .unauthorized
        }
        if lower.contains("openai") && (lower.contains("key") || lower.contains("api_key")) {
            return .needsAIKey
        }
        return .server(message)
    }
}

/// Typed GraphQL over URLSession. An actor, so JSON encode/decode never runs on
/// the main thread, and the shared URLSession keeps HTTP/2 connections warm.
actor GraphQLClient {
    static let shared = GraphQLClient()

    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder = JSONEncoder()

    init() {
        let configuration = URLSessionConfiguration.default
        configuration.waitsForConnectivity = false
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 240
        configuration.httpAdditionalHeaders = [
            "Accept": "application/json",
            "User-Agent": "Manifest-iOS/\(AppConfig.appVersion)",
            // The edge Worker and backend treat this as an API client, not a browser form.
            "X-Requested-With": "ManifestApp",
        ]
        session = URLSession(configuration: configuration)
        decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            if let date = DateParser.parse(raw) { return date }
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Bad date \(raw)")
        }
    }

    private struct Body: Encodable {
        let query: String
        let variables: [String: JSONValue]
    }

    private struct Envelope<T: Decodable>: Decodable {
        let data: T?
        let errors: [Message]?
        struct Message: Decodable { let message: String }
    }

    /// Runs an operation and decodes `data`. `timeout` is raised for AI generation.
    func run<T: Decodable & Sendable>(
        _ query: String,
        _ variables: [String: JSONValue] = [:],
        as type: T.Type = T.self,
        timeout: TimeInterval = 30
    ) async throws -> T {
        do {
            return try await perform(query, variables, timeout: timeout, allowRetry: true)
        } catch is CancellationError {
            throw APIError.cancelled
        } catch let error as URLError where error.code == .cancelled {
            throw APIError.cancelled
        }
    }

    private func perform<T: Decodable>(
        _ query: String,
        _ variables: [String: JSONValue],
        timeout: TimeInterval,
        allowRetry: Bool
    ) async throws -> T {
        #if DEBUG
        if Fixtures.isEnabled {
            try await Task.sleep(for: .milliseconds(250))
            let data = try JSONSerialization.data(withJSONObject: ["data": Fixtures.data(for: query)])
            guard let value = try decoder.decode(Envelope<T>.self, from: data).data else { throw APIError.server("No fixture") }
            return value
        }
        #endif
        var request = URLRequest(url: AppConfig.graphQLURL, timeoutInterval: timeout)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = try await TokenStore.shared.validAccessToken() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = try encoder.encode(Body(query: query, variables: variables))

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: request)
        } catch let error as URLError {
            switch error.code {
            case .cancelled: throw APIError.cancelled
            case .timedOut: throw APIError.server("That took too long. Try again in a moment.")
            default: throw APIError.offline
            }
        }
        try Task.checkCancellation()

        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        if status == 401 {
            return try await retryAfterRefresh(query, variables, timeout: timeout, allowRetry: allowRetry)
        }
        if status == 429 {
            throw APIError.server("You're going a little fast. Wait a few seconds and try again.")
        }
        guard (200..<300).contains(status) || status == 400 else {
            throw APIError.server("Manifest is having trouble right now (HTTP \(status)).")
        }

        let envelope: Envelope<T>
        do {
            envelope = try decoder.decode(Envelope<T>.self, from: data)
        } catch {
            #if DEBUG
            print("[GraphQL] decode failed:", error, String(data: data.prefix(600), encoding: .utf8) ?? "")
            #endif
            throw APIError.server("Manifest sent something this version can't read. Update the app.")
        }
        if let message = envelope.errors?.first?.message {
            let error = APIError.from(message: message)
            if error == .unauthorized {
                return try await retryAfterRefresh(query, variables, timeout: timeout, allowRetry: allowRetry)
            }
            // A nullable field can fail while the rest succeeds; keep the useful part.
            if let data = envelope.data { return data }
            throw error
        }
        guard let data = envelope.data else { throw APIError.server("Empty response.") }
        return data
    }

    private func retryAfterRefresh<T: Decodable>(
        _ query: String,
        _ variables: [String: JSONValue],
        timeout: TimeInterval,
        allowRetry: Bool
    ) async throws -> T {
        guard allowRetry, await TokenStore.shared.current?.refreshToken != nil else {
            await SessionEvents.shared.signedOut()
            throw APIError.unauthorized
        }
        do {
            try await TokenStore.shared.refresh()
        } catch {
            await SessionEvents.shared.signedOut()
            throw APIError.unauthorized
        }
        return try await perform(query, variables, timeout: timeout, allowRetry: false)
    }
}


/// Broadcasts "the server says this session is over" to the UI layer.
@MainActor
final class SessionEvents {
    static let shared = SessionEvents()
    var onSignedOut: (() -> Void)?
    func signedOut() { onSignedOut?() }
}

/// GraphQL variables without `Any`.
nonisolated enum JSONValue: Encodable, Sendable, ExpressibleByStringLiteral, ExpressibleByIntegerLiteral,
    ExpressibleByBooleanLiteral, ExpressibleByFloatLiteral, ExpressibleByNilLiteral,
    ExpressibleByArrayLiteral, ExpressibleByDictionaryLiteral
{
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case array([JSONValue])
    case object([String: JSONValue])
    case null

    init(stringLiteral value: String) { self = .string(value) }
    init(integerLiteral value: Int) { self = .int(value) }
    init(booleanLiteral value: Bool) { self = .bool(value) }
    init(floatLiteral value: Double) { self = .double(value) }
    init(nilLiteral: ()) { self = .null }
    init(arrayLiteral elements: JSONValue...) { self = .array(elements) }
    init(dictionaryLiteral elements: (String, JSONValue)...) {
        self = .object(Dictionary(uniqueKeysWithValues: elements))
    }

    static func optional(_ value: String?) -> JSONValue { value.map(JSONValue.string) ?? .null }
    static func strings(_ values: [String]) -> JSONValue { .array(values.map(JSONValue.string)) }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let v): try container.encode(v)
        case .int(let v): try container.encode(v)
        case .double(let v): try container.encode(v)
        case .bool(let v): try container.encode(v)
        case .array(let v): try container.encode(v)
        case .object(let v): try container.encode(v)
        case .null: try container.encodeNil()
        }
    }
}

nonisolated enum DateParser {
    private static let withFraction = Date.ISO8601FormatStyle(includingFractionalSeconds: true)
    private static let plain = Date.ISO8601FormatStyle()

    /// Accepts ISO 8601 with or without fractional seconds or a zone (the backend sends both).
    static func parse(_ raw: String) -> Date? {
        if let d = try? withFraction.parse(raw) { return d }
        if let d = try? plain.parse(raw) { return d }
        // Naive timestamps ("2026-11-18T08:59:02.123456") are UTC.
        var trimmed = raw.replacingOccurrences(of: " ", with: "T")
        if let dot = trimmed.firstIndex(of: ".") { trimmed = String(trimmed[..<dot]) }
        if let plus = trimmed.range(of: "+", options: .backwards) { trimmed = String(trimmed[..<plus.lowerBound]) }
        return try? plain.parse(trimmed + "Z")
    }
}
