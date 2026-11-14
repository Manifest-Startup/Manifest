import Foundation
import SwiftUI
import Combine

@MainActor
class DiscoverViewModel: ObservableObject {
    
    @Published var feedItems: [FeedItem] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var currentIndex = 0
    
    private let apiService = APIService.shared
    
    func loadFeed() async {
        isLoading = true
        errorMessage = nil
        
        do {
            feedItems = try await apiService.getPublicFeed()
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }
    
    func upvote(item: FeedItem) async {
        do {
            let result = try await apiService.upvoteIdea(id: item.ideaId)
            if let index = feedItems.firstIndex(where: { $0.id == item.id }) {
                let updatedItem = FeedItem(
                    id: item.id,
                    ideaId: item.ideaId,
                    title: item.title,
                    description: item.description,
                    authorId: item.authorId,
                    authorName: item.authorName,
                    authorAvatarUrl: item.authorAvatarUrl,
                    upvoteCount: result.upvoteCount,
                    hasUpvoted: result.hasUpvoted,
                    isPublished: item.isPublished,
                    createdAt: item.createdAt
                )
                feedItems[index] = updatedItem
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
    
    func nextItem() {
        if currentIndex < feedItems.count - 1 {
            currentIndex += 1
        }
    }
    
    func previousItem() {
        if currentIndex > 0 {
            currentIndex -= 1
        }
    }
}

