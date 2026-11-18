import Foundation
import Observation
import SwiftUI

/// Load state shared by list screens.
enum LoadState: Equatable {
    case idle, loading, loaded
    case failed(String)

    var error: String? {
        if case .failed(let message) = self { return message }
        return nil
    }
}

/// Runs an async action, turning failures into a message (or nil when cancelled).
@discardableResult
func attempt(_ work: () async throws -> Void) async -> String? {
    do {
        try await work()
        return nil
    } catch APIError.cancelled {
        return nil
    } catch {
        return error.localizedDescription
    }
}

// MARK: Ideas

@Observable
final class IdeasStore {
    private(set) var ideas: [IdeaSummary] = []
    private(set) var shared: [SharedIdea] = []
    private(set) var invitations: [CollaborationInvitation] = []
    private(set) var state: LoadState = .idle
    /// Full ideas fetched by the detail screen, so reopening one is instant.
    private(set) var details: [String: Idea] = [:]

    func load() async {
        if ideas.isEmpty, let cached = await DiskCache.load([IdeaSummary].self, key: "ideas") {
            ideas = cached
        }
        await refresh()
    }

    func refresh() async {
        if ideas.isEmpty { state = .loading }
        do {
            async let mine = API.ideas()
            async let sharedWithMe = API.sharedIdeas()
            async let invites = API.invitations()
            let fetched = try await mine
            ideas = fetched.sorted { $0.createdAt > $1.createdAt }
            shared = (try? await sharedWithMe) ?? shared
            invitations = (try? await invites) ?? invitations
            state = .loaded
            DiskCache.save(ideas, key: "ideas")
        } catch APIError.cancelled {
        } catch {
            state = .failed(error.localizedDescription)
        }
    }

    func create(title: String, description: String?) async throws -> Idea {
        let idea = try await API.createIdea(title: title, description: description)
        upsert(idea)
        return idea
    }

    func upsert(_ idea: Idea) {
        details[idea.ideaId] = idea
        let summary = idea.summary
        if let index = ideas.firstIndex(where: { $0.ideaId == idea.ideaId }) {
            ideas[index] = summary
        } else if idea.userId == ideas.first?.userId || ideas.isEmpty {
            ideas.insert(summary, at: 0)
        }
        DiskCache.save(ideas, key: "ideas")
    }

    func delete(_ id: String) async throws {
        let previous = ideas
        withAnimation(Theme.spring) { ideas.removeAll { $0.ideaId == id } }
        do {
            try await API.deleteIdea(id)
            details[id] = nil
            DiskCache.save(ideas, key: "ideas")
        } catch {
            withAnimation(Theme.spring) { ideas = previous }
            throw error
        }
    }

    /// Optimistic: flips immediately, reconciles with the server's answer.
    func togglePublish(_ id: String) async throws {
        setPublished(id, !(isPublished(id) ?? false))
        do {
            let result = try await API.togglePublish(id)
            setPublished(id, result.isPublished)
        } catch {
            setPublished(id, !(isPublished(id) ?? false))
            throw error
        }
    }

    func respond(to invitation: CollaborationInvitation, accept: Bool) async throws {
        try await API.respond(ideaId: invitation.ideaId, accept: accept)
        withAnimation(Theme.spring) { invitations.removeAll { $0.id == invitation.id } }
        if accept { await refresh() }
    }

    func isPublished(_ id: String) -> Bool? {
        details[id]?.isPublished ?? ideas.first { $0.ideaId == id }?.isPublished
    }

    private func setPublished(_ id: String, _ value: Bool) {
        if let i = ideas.firstIndex(where: { $0.ideaId == id }) { ideas[i].isPublished = value }
        details[id]?.isPublished = value
    }
}

// MARK: Shorts

@Observable
final class ShortsStore {
    private(set) var reels: [PitchReel] = []
    private(set) var state: LoadState = .idle

    func load() async {
        if reels.isEmpty, let cached = await DiskCache.load([PitchReel].self, key: "reels") { reels = cached }
        await refresh()
    }

    func refresh() async {
        if reels.isEmpty { state = .loading }
        do {
            reels = try await API.reels().filter { $0.videoURL != nil }
            state = .loaded
            DiskCache.save(reels, key: "reels")
        } catch APIError.cancelled {
        } catch {
            state = .failed(error.localizedDescription)
        }
    }

    func toggleLike(_ id: String) async {
        guard let i = reels.firstIndex(where: { $0.id == id }) else { return }
        let liked = !reels[i].viewerState.liked
        reels[i].viewerState.liked = liked
        reels[i].stats.likeCount += liked ? 1 : -1
        do {
            let result = try await API.setLike(reelId: id, liked: liked)
            if let j = reels.firstIndex(where: { $0.id == id }) {
                reels[j].viewerState.liked = result.liked
                if let count = result.likeCount { reels[j].stats.likeCount = count }
            }
        } catch {
            if let j = reels.firstIndex(where: { $0.id == id }) {
                reels[j].viewerState.liked = !liked
                reels[j].stats.likeCount += liked ? -1 : 1
            }
        }
    }

    func markShared(_ id: String) async {
        guard let i = reels.firstIndex(where: { $0.id == id }), !reels[i].viewerState.reshared else { return }
        reels[i].viewerState.reshared = true
        reels[i].stats.shareCount += 1
        if let result = try? await API.setReshare(reelId: id, reshared: true),
            let count = result.shareCount, let j = reels.firstIndex(where: { $0.id == id })
        {
            reels[j].stats.shareCount = count
        }
    }

    func toggleFollow(creator userId: String) async {
        let following = !(reels.first { $0.creator.userId == userId }?.creator.isFollowing ?? false)
        setFollowing(userId, following)
        do {
            let result = try await API.toggleFollow(userId: userId)
            setFollowing(userId, result.following)
        } catch {
            setFollowing(userId, !following)
        }
    }

    func commentAdded(to id: String) {
        if let i = reels.firstIndex(where: { $0.id == id }) { reels[i].stats.commentCount += 1 }
    }

    private func setFollowing(_ userId: String, _ value: Bool) {
        for i in reels.indices where reels[i].creator.userId == userId {
            if reels[i].creator.isFollowing != value {
                reels[i].creator.followerCount += value ? 1 : -1
            }
            reels[i].creator.isFollowing = value
        }
    }
}

// MARK: Inbox

@Observable
final class InboxStore {
    private(set) var conversations: [InboxConversation] = []
    private(set) var state: LoadState = .idle
    private(set) var unread = 0

    func load() async {
        if conversations.isEmpty, let cached = await DiskCache.load([InboxConversation].self, key: "inbox") {
            conversations = cached
        }
        await refresh()
    }

    func refresh() async {
        if conversations.isEmpty { state = .loading }
        do {
            conversations = try await API.inbox().sorted { $0.lastMessageAt > $1.lastMessageAt }
            unread = conversations.reduce(0) { $0 + $1.unreadCount }
            state = .loaded
            DiskCache.save(conversations, key: "inbox")
        } catch APIError.cancelled {
        } catch {
            state = .failed(error.localizedDescription)
        }
    }

    func refreshUnread() async {
        if let count = try? await API.unreadCount() { unread = count }
    }

    /// Light polling while the app is in the foreground; cancelled with the scene.
    func pollUnread() async {
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(45))
            guard !Task.isCancelled else { return }
            await refreshUnread()
        }
    }

    func markRead(_ id: String) {
        guard let i = conversations.firstIndex(where: { $0.id == id }), conversations[i].unreadCount > 0 else { return }
        unread = max(0, unread - conversations[i].unreadCount)
        conversations[i].unreadCount = 0
        Task { try? await API.markRead(id) }
    }

    func didSend(_ text: String, in id: String) {
        guard let i = conversations.firstIndex(where: { $0.id == id }) else { return }
        conversations[i].preview = text
        conversations[i].lastMessageAt = .now
        let item = conversations.remove(at: i)
        conversations.insert(item, at: 0)
    }
}

// MARK: Portfolio

@Observable
final class PortfolioStore {
    private(set) var items: [PortfolioItem] = []
    private(set) var state: LoadState = .idle

    var totalValue: Double { items.reduce(0) { $0 + $1.totalValue } }
    var cash: Double { items.reduce(0) { $0 + $1.cashAmount } }
    var sweat: Double { items.reduce(0) { $0 + $1.sweatEquityValue } }

    func load() async {
        if items.isEmpty, let cached = await DiskCache.load([PortfolioItem].self, key: "portfolio") { items = cached }
        await refresh()
    }

    func refresh() async {
        if items.isEmpty { state = .loading }
        do {
            items = try await API.portfolio().sorted { $0.createdAt > $1.createdAt }
            state = .loaded
            DiskCache.save(items, key: "portfolio")
        } catch APIError.cancelled {
        } catch {
            state = .failed(error.localizedDescription)
        }
    }
}
