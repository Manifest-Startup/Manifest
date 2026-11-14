import Foundation

struct Idea: Identifiable, Codable {
    let id: String
    let title: String
    let description: String?
    let isPublished: Bool
    let pitchDeck: String?
    let businessModelCanvas: BusinessModelCanvas?
    let createdAt: Date?
    let updatedAt: Date?
    
    enum CodingKeys: String, CodingKey {
        case id = "ideaId"
        case title
        case description
        case isPublished
        case pitchDeck
        case businessModelCanvas
        case createdAt
        case updatedAt
    }
}

struct BusinessModelCanvas: Codable {
    let keyPartners: String?
    let keyActivities: String?
    let keyResources: String?
    let valuePropositions: String?
    let customerRelationships: String?
    let channels: String?
    let customerSegments: String?
    let costStructure: String?
    let revenueStreams: String?
}

struct CreateIdeaInput: Codable {
    let title: String
}

struct TogglePublishResult: Codable {
    let ideaId: String
    let isPublished: Bool
    let message: String
}
