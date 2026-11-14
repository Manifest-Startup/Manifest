import Foundation

struct User: Identifiable, Codable {
    let id: String
    let email: String
    let firstName: String?
    let lastName: String?
    let username: String?
    let bio: String?
    let country: String?
    let gravatarHash: String?
    let profilePictureUrl: String?
    
    enum CodingKeys: String, CodingKey {
        case id = "userId"
        case email
        case firstName
        case lastName
        case username
        case bio
        case country
        case gravatarHash
        case profilePictureUrl
    }
    
    var displayName: String {
        if let first = firstName, let last = lastName, !first.isEmpty, !last.isEmpty {
            return "\(first) \(last)"
        }
        return email
    }
    
    var avatarURL: URL? {
        if let profilePictureUrl = profilePictureUrl, !profilePictureUrl.isEmpty {
            return URL(string: profilePictureUrl)
        }
        if let hash = gravatarHash, !hash.isEmpty {
            return URL(string: "https://www.gravatar.com/avatar/\(hash)?s=200&d=mp")
        }
        return nil
    }
}

struct UpdateAccountInput: Codable {
    var firstName: String?
    var lastName: String?
    var email: String?
    var bio: String?
    var profilePictureUrl: String?
}
