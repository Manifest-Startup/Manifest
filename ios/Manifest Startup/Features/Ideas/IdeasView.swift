import SwiftUI

struct IdeasView: View {
    @Environment(IdeasStore.self) private var store
    @Environment(SessionModel.self) private var session
    @State private var path = NavigationPath()
    @State private var showComposer = false
    @State private var query = ""
    @State private var error: String?
    @State private var pendingDelete: IdeaSummary?

    private var filtered: [IdeaSummary] {
        let q = query.trimmed
        guard !q.isEmpty else { return store.ideas }
        return store.ideas.filter {
            $0.title.localizedCaseInsensitiveContains(q) || ($0.description ?? "").localizedCaseInsensitiveContains(q)
        }
    }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    header

                    if let message = error ?? store.state.error {
                        ErrorBanner(message: message) { Task { await store.refresh() } }
                    }

                    if session.isGuest { GuestBanner() }

                    ForEach(store.invitations) { invite in
                        InvitationCard(invitation: invite)
                    }

                    if store.state == .loading && store.ideas.isEmpty {
                        ForEach(0..<4, id: \.self) { _ in SkeletonCard() }
                    } else if store.ideas.isEmpty && store.state == .loaded {
                        EmptyIdeas { showComposer = true }
                            .padding(.top, 30)
                    } else {
                        ForEach(filtered) { idea in
                            NavigationLink(value: IdeaRoute(id: idea.ideaId)) {
                                IdeaCard(idea: idea)
                            }
                            .pressable()
                            .contextMenu { contextMenu(for: idea) }
                        }
                        if !query.isEmpty && filtered.isEmpty {
                            Text("No ideas match “\(query)”.")
                                .foregroundStyle(Theme.secondaryText)
                                .frame(maxWidth: .infinity)
                                .padding(.top, 40)
                        }
                    }

                    if !store.shared.isEmpty {
                        Text("Shared with you").eyebrowStyle().padding(.top, 18)
                        ForEach(store.shared) { shared in
                            NavigationLink(value: IdeaRoute(id: shared.ideaId)) {
                                SharedIdeaRow(idea: shared)
                            }
                            .pressable()
                        }
                    }
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 100)
                .frame(maxWidth: 760)
                .frame(maxWidth: .infinity)
            }
            .screenBackground()
            .refreshable { await store.refresh() }
            .searchable(text: $query, placement: .toolbar, prompt: "Filter your ideas")
            .navigationTitle("Ideas")
            .accountToolbar()
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        showComposer = true
                    } label: {
                        Label("New idea", systemImage: "plus")
                    }
                    .accessibilityIdentifier("newIdea")
                }
            }
            #if DEBUG
            .task {
                switch DemoScreen.current {
                case .idea, .document, .canvas, .interview, .captable: path.append(IdeaRoute(id: "idea-1"))
                case .newIdea: showComposer = true
                default: break
                }
            }
            #endif
            .navigationDestination(for: IdeaRoute.self) { route in
                IdeaDetailView(ideaID: route.id)
            }
            .sheet(isPresented: $showComposer) {
                NewIdeaSheet { idea in
                    path.append(IdeaRoute(id: idea.ideaId))
                }
            }
            .confirmationDialog(
                "Delete “\(pendingDelete?.title ?? "")”?",
                isPresented: Binding(get: { pendingDelete != nil }, set: { if !$0 { pendingDelete = nil } }),
                titleVisibility: .visible
            ) {
                Button("Delete idea", role: .destructive) {
                    guard let idea = pendingDelete else { return }
                    Task { error = await attempt { try await store.delete(idea.ideaId) } }
                }
            } message: {
                Text("Its documents, canvas and history go with it. This can't be undone.")
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(Date.now.formatted(.dateTime.weekday(.wide).month().day()))
                .eyebrowStyle()
            Text(greeting)
                .font(.title2.weight(.semibold))
                .foregroundStyle(Theme.ink)
            if !store.ideas.isEmpty {
                Text(summaryLine)
                    .font(.subheadline)
                    .foregroundStyle(Theme.secondaryText)
            }
        }
        .padding(.top, 4)
        .padding(.bottom, 6)
    }

    private var greeting: String {
        let hour = Calendar.current.component(.hour, from: .now)
        let part = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening"
        if let first = session.user?.firstName?.nilIfEmpty, !session.isGuest { return "\(part), \(first)." }
        return "\(part)."
    }

    private var summaryLine: String {
        let published = store.ideas.filter(\.isPublished).count
        let count = store.ideas.count
        return "\(count) \(count == 1 ? "idea" : "ideas") · \(published) published"
    }

    @ViewBuilder
    private func contextMenu(for idea: IdeaSummary) -> some View {
        Button {
            Task { error = await attempt { try await store.togglePublish(idea.ideaId) } }
        } label: {
            Label(idea.isPublished ? "Make private" : "Publish", systemImage: idea.isPublished ? "lock" : "globe")
        }
        Button(role: .destructive) {
            pendingDelete = idea
        } label: {
            Label("Delete", systemImage: "trash")
        }
    }
}

struct IdeaRoute: Hashable { let id: String }

// MARK: Rows

struct IdeaCard: View {
    let idea: IdeaSummary

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Theme.gradient(for: idea.ideaId))
                .frame(width: 44, height: 44)
                .overlay {
                    Text(String(idea.title.prefix(1)).uppercased())
                        .font(.system(.title3, design: .rounded, weight: .bold))
                        .foregroundStyle(.white)
                }

            VStack(alignment: .leading, spacing: 5) {
                HStack(alignment: .firstTextBaseline) {
                    Text(idea.title)
                        .font(.headline)
                        .foregroundStyle(Theme.ink)
                        .lineLimit(2)
                    Spacer(minLength: 8)
                    PublishBadge(isPublished: idea.isPublished)
                }
                if let description = idea.description?.nilIfEmpty {
                    Text(description)
                        .font(.subheadline)
                        .foregroundStyle(Theme.secondaryText)
                        .lineLimit(2)
                }
                HStack(spacing: 10) {
                    ProgressDots(filled: idea.generatedAssetCount, total: 4)
                    Text(idea.generatedAssetCount == 0 ? "Ready to plan" : "\(idea.generatedAssetCount) of 4 documents")
                    Spacer()
                    Text(Format.relative(idea.createdAt))
                }
                .font(.caption)
                .foregroundStyle(Theme.tertiaryText)
                .padding(.top, 2)
            }
        }
        .card(padding: 16)
        .accessibilityElement(children: .combine)
        .accessibilityHint("Opens the idea")
    }
}

struct ProgressDots: View {
    let filled: Int
    let total: Int
    var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<total, id: \.self) { i in
                Capsule()
                    .fill(i < filled ? Theme.accent : Theme.hairline)
                    .frame(width: 12, height: 4)
            }
        }
        .accessibilityHidden(true)
    }
}

private struct SharedIdeaRow: View {
    let idea: SharedIdea
    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "person.2.fill")
                .foregroundStyle(Theme.accent)
                .frame(width: 44, height: 44)
                .background(Theme.accentSoft, in: .rect(cornerRadius: 12))
            VStack(alignment: .leading, spacing: 3) {
                Text(idea.title).font(.headline).foregroundStyle(Theme.ink).lineLimit(1)
                Text("You're \(idea.userRole == "editor" ? "an editor" : "a \(idea.userRole)")")
                    .font(.caption).foregroundStyle(Theme.secondaryText)
            }
            Spacer()
            Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(Theme.tertiaryText)
        }
        .card(padding: 14)
    }
}

private struct InvitationCard: View {
    @Environment(IdeasStore.self) private var store
    let invitation: CollaborationInvitation
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Invitation", systemImage: "envelope.open").eyebrowStyle(Theme.accent)
            Text("\(invitation.inviterName ?? "Someone") invited you to “\(invitation.ideaTitle ?? "an idea")” as \(invitation.role).")
                .font(.subheadline)
            if let error { Text(error).font(.caption).foregroundStyle(Theme.danger) }
            HStack {
                Button("Decline") { respond(false) }.glassButtonStyle()
                Button("Accept") { respond(true) }.glassButtonStyle(prominent: true)
            }
            .disabled(busy)
        }
        .card()
    }

    private func respond(_ accept: Bool) {
        busy = true
        Task {
            error = await attempt { try await store.respond(to: invitation, accept: accept) }
            busy = false
        }
    }
}

private struct GuestBanner: View {
    @Environment(SessionModel.self) private var session
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "person.crop.circle.badge.questionmark").font(.title2).foregroundStyle(Theme.accent)
            VStack(alignment: .leading, spacing: 2) {
                Text("You're exploring as a guest").font(.subheadline.weight(.semibold))
                Text("Sign in to keep your ideas and publish them.").font(.caption).foregroundStyle(Theme.secondaryText)
            }
            Spacer()
            Button("Sign in") {
                Task {
                    await session.signOut()
                }
            }
            .glassButtonStyle()
        }
        .card(padding: 14)
    }
}

private struct EmptyIdeas: View {
    let create: () -> Void
    var body: some View {
        VStack(spacing: 18) {
            ManifestMark(size: 64)
            Text("Every company starts as a sentence.")
                .font(.title3.weight(.semibold))
                .multilineTextAlignment(.center)
            Text("Write yours down. Manifest turns it into a canvas, a deck and a plan.")
                .font(.subheadline)
                .foregroundStyle(Theme.secondaryText)
                .multilineTextAlignment(.center)
            Button(action: create) {
                Label("Write your first idea", systemImage: "square.and.pencil")
                    .fontWeight(.semibold)
                    .padding(.horizontal, 6)
            }
            .glassButtonStyle(prominent: true)
            .controlSize(.large)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 30)
    }
}
