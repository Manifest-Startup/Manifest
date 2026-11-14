import Foundation
import Combine

class APIService: ObservableObject {
    let objectWillChange = ObservableObjectPublisher()
    
    static let shared = APIService()
    
    private let baseURL: String
    private var authToken: String?
    
    init() {
        self.baseURL = ProcessInfo.processInfo.environment["API_BASE_URL"] ?? "https://manifeststartup.com"
    }
    
    func setAuthToken(_ token: String?) {
        self.authToken = token
    }
    
    private func createRequest(endpoint: String, method: String = "GET", body: Data? = nil) -> URLRequest? {
        guard let url = URL(string: "\(baseURL)\(endpoint)") else { return nil }
        
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        if let token = authToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        request.httpBody = body
        return request
    }
    
    func getIdeas() async throws -> [Idea] {
        guard let request = createRequest(endpoint: "/api/v1/ideas") else {
            throw APIError.invalidURL
        }
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw APIError.requestFailed
        }
        
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode([Idea].self, from: data)
    }
    
    func getIdea(id: String) async throws -> Idea {
        guard let request = createRequest(endpoint: "/api/v1/ideas/\(id)") else {
            throw APIError.invalidURL
        }
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw APIError.requestFailed
        }
        
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(Idea.self, from: data)
    }
    
    func createIdea(title: String) async throws -> Idea {
        let input = CreateIdeaInput(title: title)
        let body = try JSONEncoder().encode(input)
        
        guard var request = createRequest(endpoint: "/api/v1/ideas", method: "POST", body: body) else {
            throw APIError.invalidURL
        }
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 201 else {
            throw APIError.requestFailed
        }
        
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(Idea.self, from: data)
    }
    
    func togglePublishIdea(id: String) async throws -> TogglePublishResult {
        guard let request = createRequest(endpoint: "/api/v1/ideas/\(id)/publish", method: "POST") else {
            throw APIError.invalidURL
        }
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw APIError.requestFailed
        }
        
        return try JSONDecoder().decode(TogglePublishResult.self, from: data)
    }
    
    func getAccount() async throws -> User {
        guard let request = createRequest(endpoint: "/api/v1/account") else {
            throw APIError.invalidURL
        }
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw APIError.requestFailed
        }
        
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(User.self, from: data)
    }
    
    func updateAccount(input: UpdateAccountInput) async throws -> User {
        let body = try JSONEncoder().encode(input)
        
        guard let request = createRequest(endpoint: "/api/v1/account", method: "PUT", body: body) else {
            throw APIError.invalidURL
        }
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw APIError.requestFailed
        }
        
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(User.self, from: data)
    }
    
    func getPortfolio() async throws -> [Investment] {
        guard let request = createRequest(endpoint: "/api/v1/portfolio") else {
            throw APIError.invalidURL
        }
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw APIError.requestFailed
        }
        
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode([Investment].self, from: data)
    }
    
    func getPublicFeed() async throws -> [FeedItem] {
        guard let request = createRequest(endpoint: "/api/v1/feed") else {
            throw APIError.invalidURL
        }
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw APIError.requestFailed
        }
        
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode([FeedItem].self, from: data)
    }
    
    func upvoteIdea(id: String) async throws -> VoteResult {
        guard let request = createRequest(endpoint: "/api/v1/ideas/\(id)/upvote", method: "POST") else {
            throw APIError.invalidURL
        }
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw APIError.requestFailed
        }
        
        return try JSONDecoder().decode(VoteResult.self, from: data)
    }
}

enum APIError: Error, LocalizedError {
    case invalidURL
    case requestFailed
    case decodingFailed
    case unauthorized
    
    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL"
        case .requestFailed: return "Request failed"
        case .decodingFailed: return "Failed to decode response"
        case .unauthorized: return "Unauthorized"
        }
    }
}
