import Foundation

struct FeedItem: Identifiable, Codable {
    let id: String
    let ideaId: String
    let title: String
    let description: String?
    let authorId: String
    let authorName: String
    let authorAvatarUrl: String?
    let upvoteCount: Int
    let hasUpvoted: Bool
    let isPublished: Bool
    let createdAt: Date?
    
    enum CodingKeys: String, CodingKey {
        case id = "feedItemId"
        case ideaId
        case title
        case description
        case authorId
        case authorName
        case authorAvatarUrl
        case upvoteCount
        case hasUpvoted
        case isPublished
        case createdAt
    }
}

struct VoteResult: Codable {
    let ideaId: String
    let upvoteCount: Int
    let hasUpvoted: Bool
}
