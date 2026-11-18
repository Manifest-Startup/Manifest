import SwiftUI

/// One idea, from sentence to plan: the pitch, the canvas, the documents, the
/// team and the money. Opens instantly from the list summary and fills in.
struct IdeaDetailView: View {
    let ideaID: String

    @Environment(IdeasStore.self) private var store
    @Environment(SessionModel.self) private var session
    @Environment(\.dismiss) private var dismiss

    @State private var idea: Idea?
    @State private var canvas: [BmcSection] = []
    @State private var error: String?
    @State private var toast: Toast?
    @State private var editing = false
    @State private var confirmDelete = false
    @State private var showInterview = false
    @State private var showInvest = false
    @State private var demoPush: DemoPush?

    private enum DemoPush: Hashable { case document, canvas, captable }

    private var summary: IdeaSummary? { store.ideas.first { $0.ideaId == ideaID } }
    private var isOwner: Bool { (idea?.userId ?? summary?.userId) == session.user?.userId }
    private var title: String { idea?.title ?? summary?.title ?? "" }
    private var isPublished: Bool { store.isPublished(ideaID) ?? idea?.isPublished ?? false }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                hero

                if let error {
                    ErrorBanner(message: error) { Task { await load() } }
                }

                if isOwner {
                    SharpenCard { showInterview = true }
                }

                section("Business model") {
                    NavigationLink {
                        CanvasView(ideaID: ideaID, description: idea?.description ?? title, sections: $canvas)
                    } label: {
                        CanvasPreview(sections: canvas)
                    }
                    .pressable()
                }

                section("Documents") {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 160), spacing: 12)], spacing: 12) {
                        ForEach(DocumentKind.allCases) { kind in
                            NavigationLink {
                                DocumentView(ideaID: ideaID, kind: kind, idea: $idea, canEdit: isOwner)
                            } label: {
                                DocumentTile(kind: kind, ready: idea?.content(for: kind) != nil, loading: idea == nil)
                            }
                            .pressable()
                        }
                    }
                }

                section("People and money") {
                    VStack(spacing: 10) {
                        NavigationLink {
                            TeamView(ideaID: ideaID, isOwner: isOwner)
                        } label: {
                            LinkRow(symbol: "person.2", title: "Team", subtitle: "Invite collaborators and set roles")
                        }
                        NavigationLink {
                            CapTableView(ideaID: ideaID, ideaTitle: title, isOwner: isOwner)
                        } label: {
                            LinkRow(symbol: "chart.pie", title: "Cap table & investments", subtitle: "Who owns what, and every contribution")
                        }
                        NavigationLink {
                            VersionsView(ideaID: ideaID, canRestore: isOwner) { await load() }
                        } label: {
                            LinkRow(symbol: "clock.arrow.circlepath", title: "History", subtitle: "Snapshots you can return to")
                        }
                        if !isOwner {
                            FounderRow(ideaID: ideaID, ideaTitle: title)
                        }
                    }
                    .pressable()
                }
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 60)
            .frame(maxWidth: 760)
            .frame(maxWidth: .infinity)
        }
        .screenBackground()
        .navigationTitle(title)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar { toolbar }
        .refreshable { await load() }
        .toast($toast)
        .task(id: ideaID) {
            if idea == nil { idea = store.details[ideaID] }
            await load()
            #if DEBUG
            switch DemoScreen.current {
            case .document: demoPush = .document
            case .canvas: demoPush = .canvas
            case .captable: demoPush = .captable
            case .interview: showInterview = true
            default: break
            }
            #endif
        }
        .navigationDestination(item: $demoPush) { push in
            switch push {
            case .document: DocumentView(ideaID: ideaID, kind: .pitchDeck, idea: $idea, canEdit: isOwner)
            case .canvas: CanvasView(ideaID: ideaID, description: title, sections: $canvas)
            case .captable: CapTableView(ideaID: ideaID, ideaTitle: title, isOwner: isOwner)
            }
        }
        .sheet(isPresented: $editing) {
            if let idea {
                EditIdeaSheet(idea: idea) { updated in
                    self.idea = updated
                    store.upsert(updated)
                    toast = Toast(message: "Saved")
                }
            }
        }
        .sheet(isPresented: $showInterview) {
            QualificationView(ideaText: [title, idea?.description].compactMap { $0 }.joined(separator: "\n\n"))
        }
        .sheet(isPresented: $showInvest) {
            InvestSheet(ideaID: ideaID, ideaTitle: title) { toast = Toast(message: "Investment recorded") }
        }
        .confirmationDialog("Delete “\(title)”?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Delete idea", role: .destructive) {
                Task {
                    if let message = await attempt({ try await store.delete(ideaID) }) {
                        error = message
                    } else {
                        dismiss()
                    }
                }
            }
        } message: {
            Text("Its documents, canvas and history go with it. This can't be undone.")
        }
    }

    // MARK: Pieces

    private var hero: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 8) {
                StatusPill(
                    text: isPublished ? "Published" : "Private",
                    color: isPublished ? Theme.accent : Theme.secondaryText,
                    symbol: isPublished ? "globe" : "lock"
                )
                if let created = idea?.createdAt ?? summary?.createdAt {
                    Text("Started \(created.formatted(.dateTime.month(.abbreviated).day().year()))")
                        .font(.caption)
                        .foregroundStyle(Theme.tertiaryText)
                }
            }
            Text(title)
                .font(.system(.largeTitle, weight: .bold))
                .tracking(-0.5)
                .foregroundStyle(Theme.ink)
                .fixedSize(horizontal: false, vertical: true)

            if let description = (idea?.description ?? summary?.description)?.nilIfEmpty {
                Text(description)
                    .font(.body)
                    .lineSpacing(4)
                    .foregroundStyle(.primary.opacity(0.85))
                    .textSelection(.enabled)
            } else if isOwner {
                Button("Add a description") { editing = true }
                    .font(.subheadline.weight(.medium))
            }

            if let skills = idea?.requiredSkills, !skills.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(skills, id: \.self) { StatusPill(text: $0, color: Theme.secondaryText) }
                    }
                }
            }

            HStack(spacing: 10) {
                if isOwner {
                    Button {
                        Task {
                            if let message = await attempt({ try await store.togglePublish(ideaID) }) {
                                error = message
                            } else {
                                Haptics.success()
                                toast = Toast(message: isPublished ? "Published to Manifest" : "Now private",
                                              symbol: isPublished ? "globe" : "lock.fill")
                            }
                        }
                    } label: {
                        Label(isPublished ? "Make private" : "Publish", systemImage: isPublished ? "lock" : "paperplane")
                            .fontWeight(.semibold)
                    }
                    .glassButtonStyle(prominent: true)
                    .accessibilityIdentifier("publish")
                } else {
                    Button {
                        showInvest = true
                    } label: {
                        Label("Invest or contribute", systemImage: "plus.circle").fontWeight(.semibold)
                    }
                    .glassButtonStyle(prominent: true)
                }
                ShareLink(item: AppConfig.baseURL.appending(path: "ideas/\(ideaID)")) {
                    Label("Share", systemImage: "square.and.arrow.up")
                }
                .glassButtonStyle()
            }
            .controlSize(.large)
            .padding(.top, 4)
        }
        .padding(.top, 8)
    }

    @ToolbarContentBuilder
    private var toolbar: some ToolbarContent {
        if isOwner {
            ToolbarItem(placement: .primaryAction) {
                Menu {
                    Button { editing = true } label: { Label("Edit", systemImage: "pencil") }
                    Button { showInvest = true } label: { Label("Record investment", systemImage: "dollarsign.circle") }
                    Divider()
                    Button(role: .destructive) { confirmDelete = true } label: { Label("Delete", systemImage: "trash") }
                } label: {
                    Label("More", systemImage: "ellipsis")
                }
                .disabled(idea == nil)
            }
        }
    }

    private func section<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).eyebrowStyle()
            content()
        }
    }

    private func load() async {
        error = nil
        do {
            async let fullIdea = API.idea(ideaID)
            async let sections = API.canvas(ideaId: ideaID)
            let loaded = try await fullIdea
            withAnimation(Theme.snappy) { idea = loaded }
            store.upsert(loaded)
            canvas = (try? await sections) ?? canvas
        } catch APIError.cancelled {
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: Components

private struct SharpenCard: View {
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 14) {
                Image(systemName: "waveform.and.person.filled")
                    .font(.title2)
                    .foregroundStyle(.white)
                    .frame(width: 48, height: 48)
                    .background(LinearGradient(colors: [Color(hex: 0x5E5CE6), Color(hex: 0x0A84FF)], startPoint: .topLeading, endPoint: .bottomTrailing), in: .rect(cornerRadius: 14))
                VStack(alignment: .leading, spacing: 3) {
                    Text("Pressure-test it").font(.headline).foregroundStyle(Theme.ink)
                    Text("Answer the questions an investor would ask. Get a score.")
                        .font(.subheadline)
                        .foregroundStyle(Theme.secondaryText)
                        .multilineTextAlignment(.leading)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right").font(.caption.weight(.bold)).foregroundStyle(Theme.tertiaryText)
            }
            .card(padding: 14)
        }
        .pressable()
    }
}

struct CanvasPreview: View {
    let sections: [BmcSection]

    private var filled: Int { sections.filter(\.hasContent).count }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Business Model Canvas").font(.headline).foregroundStyle(Theme.ink)
                    Text(filled == 0 ? "Nine boxes. Generate a first draft in one tap." : "\(filled) of 9 sections drafted")
                        .font(.subheadline).foregroundStyle(Theme.secondaryText)
                }
                Spacer()
                Image(systemName: "chevron.right").font(.caption.weight(.bold)).foregroundStyle(Theme.tertiaryText)
            }
            // A miniature of the real canvas layout.
            let byName = Dictionary(uniqueKeysWithValues: sections.map { ($0.sectionName, $0.hasContent) })
            Grid(horizontalSpacing: 4, verticalSpacing: 4) {
                GridRow {
                    cell(.keyPartners, byName, rows: 2)
                    VStack(spacing: 4) { cell(.keyActivities, byName); cell(.keyResources, byName) }
                    cell(.valuePropositions, byName, rows: 2)
                    VStack(spacing: 4) { cell(.customerRelationships, byName); cell(.channels, byName) }
                    cell(.customerSegments, byName, rows: 2)
                }
                GridRow {
                    HStack(spacing: 4) { cell(.costStructure, byName); cell(.revenueStreams, byName) }
                        .gridCellColumns(5)
                }
            }
            .frame(height: 104)
        }
        .card(padding: 16)
    }

    private func cell(_ section: CanvasSection, _ map: [String: Bool], rows: Int = 1) -> some View {
        RoundedRectangle(cornerRadius: 5, style: .continuous)
            .fill(map[section.rawValue] == true ? AnyShapeStyle(Theme.accent.gradient.opacity(0.85)) : AnyShapeStyle(Theme.hairline))
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private struct DocumentTile: View {
    let kind: DocumentKind
    let ready: Bool
    let loading: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: kind.symbol)
                .font(.title3.weight(.medium))
                .foregroundStyle(.white)
                .frame(width: 40, height: 40)
                .background(
                    LinearGradient(colors: [Color(hexString: kind.gradient.0), Color(hexString: kind.gradient.1)],
                                   startPoint: .topLeading, endPoint: .bottomTrailing),
                    in: .rect(cornerRadius: 11)
                )
            Spacer(minLength: 0)
            Text(kind.title).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink).lineLimit(1)
            HStack(spacing: 4) {
                if loading {
                    Text(" ").redacted(reason: .placeholder)
                } else {
                    Image(systemName: ready ? "checkmark.circle.fill" : "sparkles")
                        .foregroundStyle(ready ? Theme.success : Theme.accent)
                    Text(ready ? "Ready" : "Generate")
                }
            }
            .font(.caption.weight(.medium))
            .foregroundStyle(Theme.secondaryText)
        }
        .frame(height: 128, alignment: .topLeading)
        .card(padding: 14)
        .accessibilityElement(children: .combine)
    }
}

struct LinkRow: View {
    let symbol: String
    let title: String
    let subtitle: String

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: symbol)
                .font(.body.weight(.medium))
                .foregroundStyle(Theme.accent)
                .frame(width: 36, height: 36)
                .background(Theme.accentSoft, in: .rect(cornerRadius: 10))
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Text(subtitle).font(.caption).foregroundStyle(Theme.secondaryText)
            }
            Spacer()
            Image(systemName: "chevron.right").font(.caption.weight(.bold)).foregroundStyle(Theme.tertiaryText)
        }
        .card(padding: 12)
    }
}

/// For someone else's idea: who made it, and a way to reach them.
private struct FounderRow: View {
    let ideaID: String
    let ideaTitle: String
    @State private var owner: IdeaOwner?
    @State private var conversation: InboxConversation?
    @State private var error: String?

    var body: some View {
        Group {
            if let owner {
                HStack(spacing: 12) {
                    Avatar(name: owner.name, url: owner.profilePictureUrl, size: 40)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(owner.name).font(.subheadline.weight(.semibold))
                        Text(owner.openMediaHandle.map { "@\($0)" } ?? "Founder")
                            .font(.caption).foregroundStyle(Theme.secondaryText)
                    }
                    Spacer()
                    if owner.canMessage {
                        Button("Message") { message(owner) }.glassButtonStyle()
                    }
                }
                .card(padding: 12)
            }
            if let error { Text(error).font(.caption).foregroundStyle(Theme.danger) }
        }
        .task { owner = try? await API.ideaOwner(ideaID) }
        .navigationDestination(item: $conversation) { ThreadView(conversation: $0) }
    }

    private func message(_ owner: IdeaOwner) {
        Task {
            do {
                let started = try await API.startConversation(with: owner.userId, ideaId: ideaID)
                conversation = try await API.thread(started.conversationId).conversation
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}

// MARK: Edit

struct EditIdeaSheet: View {
    let idea: Idea
    let onSave: (Idea) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var title: String
    @State private var details: String
    @State private var skills: String
    @State private var saving = false
    @State private var error: String?

    init(idea: Idea, onSave: @escaping (Idea) -> Void) {
        self.idea = idea
        self.onSave = onSave
        _title = State(initialValue: idea.title)
        _details = State(initialValue: idea.description ?? "")
        _skills = State(initialValue: idea.requiredSkills.joined(separator: ", "))
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Title") { TextField("Title", text: $title) }
                Section("Description") {
                    TextField("Description", text: $details, axis: .vertical).lineLimit(5...)
                }
                Section {
                    TextField("e.g. iOS, sales, hardware", text: $skills)
                } header: {
                    Text("Skills it needs")
                } footer: {
                    Text("Separate with commas. Shown to people looking for ideas to join.")
                }
                if let error { Section { Text(error).foregroundStyle(Theme.danger) } }
            }
            .navigationTitle("Edit idea")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel", role: .cancel) { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }
                        .fontWeight(.semibold)
                        .disabled(title.trimmed.isEmpty || saving)
                }
            }
        }
    }

    private func save() {
        saving = true
        Task {
            do {
                let list = skills.split(separator: ",").map { String($0).trimmed }.filter { !$0.isEmpty }
                let updated = try await API.updateIdea(id: idea.ideaId, title: title.trimmed, description: details.trimmed, skills: list)
                // Snapshot so the change can be undone from History.
                try? await API.createVersion(ideaId: idea.ideaId, summary: "Edited on \(AppConfig.deviceName)")
                onSave(updated)
                dismiss()
            } catch {
                self.error = error.localizedDescription
                saving = false
            }
        }
    }
}
