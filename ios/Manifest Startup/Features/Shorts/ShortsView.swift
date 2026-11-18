import AVFoundation
import SwiftUI

/// Full-bleed, swipe-up pitch shorts. One video plays at a time; it pauses when
/// the tab, app or screen goes away.
struct ShortsView: View {
    let isActive: Bool

    @Environment(ShortsStore.self) private var store
    @State private var pool = PlayerPool()
    @State private var currentID: String?
    @State private var commentsFor: PitchReel?
    @State private var ideaRoute: IdeaRoute?

    var body: some View {
        NavigationStack {
            ZStack {
                Color.black.ignoresSafeArea()

                if store.reels.isEmpty {
                    placeholder
                } else {
                    ScrollView(.vertical) {
                        LazyVStack(spacing: 0) {
                            ForEach(store.reels) { reel in
                                ReelPage(
                                    reel: reel,
                                    player: pool.player(for: reel),
                                    isCurrent: reel.id == currentID,
                                    pool: pool,
                                    onComments: { commentsFor = reel },
                                    onOpenIdea: { reel.ideaId.map { ideaRoute = IdeaRoute(id: $0) } }
                                )
                                .containerRelativeFrame([.horizontal, .vertical])
                                .id(reel.id)
                            }
                        }
                        .scrollTargetLayout()
                    }
                    .scrollTargetBehavior(.paging)
                    .scrollIndicators(.hidden)
                    .scrollPosition(id: $currentID)
                    .ignoresSafeArea()
                    .refreshable { await store.refresh() }
                }
            }
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        pool.isMuted.toggle()
                        Haptics.select()
                    } label: {
                        Label(pool.isMuted ? "Unmute" : "Mute", systemImage: pool.isMuted ? "speaker.slash.fill" : "speaker.wave.2.fill")
                    }
                }
            }
            #if os(iOS)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
            #endif
            .navigationDestination(item: $ideaRoute) { IdeaDetailView(ideaID: $0.id) }
            .sheet(item: $commentsFor) { reel in
                CommentsSheet(reel: reel)
                    .presentationDetents([.medium, .large])
                    .presentationBackground(.regularMaterial)
            }
        }
        // Scoped to this tab: preferredColorScheme would darken the whole window.
        .environment(\.colorScheme, .dark)
        .task {
            if store.reels.isEmpty { await store.load() }
            if currentID == nil { currentID = store.reels.first?.id }
        }
        .onChange(of: currentID) { sync() }
        .onChange(of: isActive) { sync() }
        .onChange(of: ideaRoute) { sync() }
        .onChange(of: store.reels.map(\.id)) {
            if currentID == nil || !store.reels.contains(where: { $0.id == currentID }) {
                currentID = store.reels.first?.id
            }
            sync()
        }
        .onDisappear { pool.pauseAll() }
    }

    private func sync() {
        if isActive && ideaRoute == nil {
            pool.activate(currentID, in: store.reels)
        } else {
            pool.pauseAll()
        }
    }

    @ViewBuilder
    private var placeholder: some View {
        switch store.state {
        case .failed(let message):
            EmptyStateView(symbol: "wifi.exclamationmark", title: "Couldn't load shorts", message: message, actionTitle: "Try again") {
                Task { await store.refresh() }
            }
        case .loaded:
            EmptyStateView(symbol: "play.rectangle", title: "No shorts yet", message: "Pitch shorts from founders show up here.")
        default:
            ProgressView().tint(.white).controlSize(.large)
        }
    }
}

private struct ReelPage: View {
    let reel: PitchReel
    let player: AVQueuePlayer?
    let isCurrent: Bool
    let pool: PlayerPool
    let onComments: () -> Void
    let onOpenIdea: () -> Void

    @Environment(ShortsStore.self) private var store
    @State private var heartBurst = false
    @State private var showPausedIcon = false

    var body: some View {
        ZStack(alignment: .bottom) {
            // Poster first (instant), video over it once it has a frame.
            LinearGradient(colors: [Color(hexString: reel.accentFrom), Color(hexString: reel.accentTo)],
                           startPoint: .topLeading, endPoint: .bottomTrailing)
            RemoteImage(url: reel.posterURL) { Color.clear }
            if let player {
                PlayerLayerView(player: player)
            }

            // Legibility scrim.
            LinearGradient(colors: [.clear, .black.opacity(0.65)], startPoint: .center, endPoint: .bottom)
                .allowsHitTesting(false)

            Color.clear
                .contentShape(.rect)
                .onTapGesture(count: 2) { like(fromDoubleTap: true) }
                .onTapGesture {
                    pool.togglePlayback()
                    showPausedIcon = !pool.isPlaying(reel.id)
                }

            if heartBurst {
                Image(systemName: "heart.fill")
                    .font(.system(size: 110))
                    .foregroundStyle(.white.opacity(0.92))
                    .shadow(radius: 20)
                    .transition(.scale(scale: 0.4).combined(with: .opacity))
                    .frame(maxHeight: .infinity)
                    .allowsHitTesting(false)
            }
            if showPausedIcon && isCurrent {
                Image(systemName: "play.fill")
                    .font(.system(size: 56))
                    .foregroundStyle(.white.opacity(0.85))
                    .frame(maxHeight: .infinity)
                    .allowsHitTesting(false)
            }

            HStack(alignment: .bottom, spacing: 16) {
                info
                actions
            }
            .padding(.horizontal, 18)
            .padding(.bottom, 110)
        }
        .clipped()
        .onChange(of: isCurrent) { showPausedIcon = false }
        .accessibilityElement(children: .contain)
        .accessibilityAction(named: "Like") { like(fromDoubleTap: false) }
        .accessibilityAction(named: "Comments") { onComments() }
    }

    private var info: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Avatar(name: reel.creator.name, url: reel.creator.avatar, size: 36)
                    .overlay(Circle().stroke(.white.opacity(0.8), lineWidth: 1.5))
                VStack(alignment: .leading, spacing: 1) {
                    Text(reel.creator.name).font(.subheadline.weight(.semibold))
                    if let handle = reel.creator.handle { Text("@\(handle)").font(.caption).opacity(0.75) }
                }
                Button(reel.creator.isFollowing ? "Following" : "Follow") {
                    Haptics.tap()
                    Task { await store.toggleFollow(creator: reel.creator.userId) }
                }
                .font(.caption.weight(.semibold))
                .glassButtonStyle()
                .controlSize(.small)
            }
            Text(reel.title)
                .font(.title3.weight(.bold))
                .lineLimit(2)
            if let subtitle = reel.subtitle ?? reel.thesis {
                Text(subtitle).font(.subheadline).lineLimit(3).opacity(0.9)
            }
            if !reel.tags.isEmpty {
                Text(reel.tags.prefix(4).map { "#\($0)" }.joined(separator: " "))
                    .font(.caption.weight(.semibold))
                    .opacity(0.8)
            }
            if reel.ideaId != nil {
                Button(action: onOpenIdea) {
                    Label("Open the idea", systemImage: "arrow.up.right")
                        .font(.caption.weight(.semibold))
                }
                .glassButtonStyle()
                .controlSize(.small)
            }
        }
        .foregroundStyle(.white)
        .shadow(color: .black.opacity(0.35), radius: 6, y: 2)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var actions: some View {
        VStack(spacing: 20) {
            ReelAction(symbol: reel.viewerState.liked ? "heart.fill" : "heart",
                       count: reel.stats.likeCount,
                       tint: reel.viewerState.liked ? Color(hex: 0xFF375F) : .white,
                       label: reel.viewerState.liked ? "Unlike" : "Like") {
                like(fromDoubleTap: false)
            }
            ReelAction(symbol: "bubble.right", count: reel.stats.commentCount, label: "Comments", action: onComments)
            ShareLink(item: reel.shareURL, subject: Text(reel.title), message: Text(reel.subtitle ?? "")) {
                ReelActionLabel(symbol: reel.viewerState.reshared ? "arrowshape.turn.up.right.fill" : "arrowshape.turn.up.right",
                                count: reel.stats.shareCount)
            }
            .simultaneousGesture(TapGesture().onEnded { Task { await store.markShared(reel.id) } })
            .accessibilityLabel("Share")
        }
        .foregroundStyle(.white)
    }

    private func like(fromDoubleTap: Bool) {
        Haptics.tap()
        if fromDoubleTap {
            withAnimation(.spring(response: 0.3, dampingFraction: 0.55)) { heartBurst = true }
            Task {
                try? await Task.sleep(for: .milliseconds(650))
                withAnimation(.easeOut(duration: 0.25)) { heartBurst = false }
            }
            if reel.viewerState.liked { return }
        }
        Task { await store.toggleLike(reel.id) }
    }
}

private struct ReelAction: View {
    let symbol: String
    let count: Int
    var tint: Color = .white
    let label: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            ReelActionLabel(symbol: symbol, count: count, tint: tint)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityValue("\(count)")
    }
}

private struct ReelActionLabel: View {
    let symbol: String
    let count: Int
    var tint: Color = .white

    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: symbol)
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(tint)
                .frame(width: 50, height: 50)
                .glassSurface(.circle, clear: true)
                .contentTransition(.symbolEffect(.replace))
            Text(Format.count(count))
                .font(.caption2.weight(.semibold))
                .monospacedDigit()
                .contentTransition(.numericText())
        }
        .shadow(color: .black.opacity(0.3), radius: 4)
    }
}

// MARK: Comments

struct CommentsSheet: View {
    let reel: PitchReel
    @Environment(ShortsStore.self) private var store
    @State private var comments: [PitchReelComment] = []
    @State private var loading = true
    @State private var text = ""
    @State private var sending = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Group {
                if loading && comments.isEmpty {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if comments.isEmpty {
                    ContentUnavailableView("No comments yet", systemImage: "bubble.left.and.bubble.right",
                                           description: Text("Say something kind and specific."))
                } else {
                    List(comments) { comment in
                        HStack(alignment: .top, spacing: 10) {
                            Avatar(name: comment.authorName, url: comment.authorAvatar, size: 32)
                            VStack(alignment: .leading, spacing: 3) {
                                HStack(spacing: 6) {
                                    Text(comment.authorName).font(.subheadline.weight(.semibold))
                                    Text(Format.relative(comment.createdAt)).font(.caption).foregroundStyle(.secondary)
                                }
                                Text(comment.body).font(.subheadline)
                            }
                        }
                        .listRowBackground(Color.clear)
                    }
                    .listStyle(.plain)
                    .scrollContentBackground(.hidden)
                }
            }
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 6) {
                    if let error { Text(error).font(.caption).foregroundStyle(Theme.danger) }
                    HStack(spacing: 10) {
                        TextField("Add a comment", text: $text, axis: .vertical)
                            .lineLimit(1...4)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 10)
                            .glassSurface(.rect(cornerRadius: 20))
                            .onSubmit(send)
                        Button(action: send) {
                            Image(systemName: "arrow.up").font(.body.weight(.bold)).frame(width: 22, height: 22)
                        }
                        .glassButtonStyle(prominent: true)
                        .buttonBorderShape(.circle)
                        .disabled(text.trimmed.isEmpty || sending)
                        .accessibilityLabel("Post comment")
                    }
                }
                .padding()
            }
            .navigationTitle("\(Format.count(reel.stats.commentCount)) comments")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
        }
        .task {
            comments = (try? await API.comments(reelId: reel.id)) ?? []
            loading = false
        }
    }

    private func send() {
        let body = text.trimmed
        guard !body.isEmpty, !sending else { return }
        sending = true
        error = nil
        Task {
            do {
                let comment = try await API.addComment(reelId: reel.id, body: body)
                withAnimation(Theme.spring) { comments.insert(comment, at: 0) }
                store.commentAdded(to: reel.id)
                text = ""
                Haptics.success()
            } catch {
                self.error = error.localizedDescription
            }
            sending = false
        }
    }
}
