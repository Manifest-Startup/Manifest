import SwiftUI

/// A generated document: read it beautifully, edit it, regenerate it, share it.
struct DocumentView: View {
    let ideaID: String
    let kind: DocumentKind
    @Binding var idea: Idea?
    let canEdit: Bool

    @Environment(IdeasStore.self) private var store
    @State private var generating = false
    @State private var editing = false
    @State private var draft = ""
    @State private var error: String?
    @State private var toast: Toast?
    @State private var confirmRegenerate = false
    @State private var startedAt: Date?

    private var content: String? { idea?.content(for: kind) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header

                if let error {
                    ErrorBanner(message: error, retry: error == APIError.needsAIKey.errorDescription ? nil : { generate() })
                }

                if generating {
                    GeneratingView(kind: kind, startedAt: startedAt ?? .now)
                } else if editing {
                    TextEditor(text: $draft)
                        .font(.system(.body, design: .monospaced))
                        .frame(minHeight: 480)
                        .scrollContentBackground(.hidden)
                        .padding(12)
                        .background(Theme.surface, in: .rect(cornerRadius: Theme.radius))
                } else if let content {
                    MarkdownView(markdown: content)
                        .card(padding: 22)
                } else {
                    emptyState
                }

                if kind == .patent, content != nil {
                    Label("A draft to discuss with a registered patent attorney. Not legal advice.", systemImage: "info.circle")
                        .font(.caption)
                        .foregroundStyle(Theme.secondaryText)
                }
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 60)
            .frame(maxWidth: 820)
            .frame(maxWidth: .infinity)
        }
        .screenBackground()
        .navigationTitle(kind.title)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toast($toast)
        .toolbar { toolbar }
        .confirmationDialog("Regenerate the \(kind.title.lowercased())?", isPresented: $confirmRegenerate, titleVisibility: .visible) {
            Button("Regenerate", role: .destructive) { generate() }
        } message: {
            Text("The new draft replaces the current one, including your edits. It uses your OpenAI key.")
        }
    }

    private var header: some View {
        HStack(spacing: 14) {
            Image(systemName: kind.symbol)
                .font(.title2.weight(.medium))
                .foregroundStyle(.white)
                .frame(width: 52, height: 52)
                .background(
                    LinearGradient(colors: [Color(hexString: kind.gradient.0), Color(hexString: kind.gradient.1)],
                                   startPoint: .topLeading, endPoint: .bottomTrailing),
                    in: .rect(cornerRadius: 14)
                )
            VStack(alignment: .leading, spacing: 2) {
                Text(kind.title).font(.title2.weight(.bold))
                Text(kind.subtitle).font(.subheadline).foregroundStyle(Theme.secondaryText)
            }
        }
        .padding(.top, 8)
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "sparkles")
                .font(.system(size: 34))
                .foregroundStyle(Theme.accent)
                .symbolEffect(.pulse, options: .repeating)
            Text("Not written yet").font(.headline)
            Text("Manifest drafts it from your idea in about a minute. You can edit every word afterwards.")
                .font(.subheadline)
                .foregroundStyle(Theme.secondaryText)
                .multilineTextAlignment(.center)
            if canEdit {
                PrimaryButton(title: "Generate \(kind.title)", symbol: "sparkles") { generate() }
                    .frame(maxWidth: 320)
                    .accessibilityIdentifier("generate")
            } else {
                Text("Only the owner can generate documents.").font(.caption).foregroundStyle(Theme.tertiaryText)
            }
        }
        .frame(maxWidth: .infinity)
        .card(padding: 28)
    }

    @ToolbarContentBuilder
    private var toolbar: some ToolbarContent {
        if editing {
            ToolbarItem(placement: .cancellationAction) {
                Button("Cancel", role: .cancel) { editing = false }
            }
            ToolbarItem(placement: .confirmationAction) {
                Button("Save") { save() }.fontWeight(.semibold)
            }
        } else if let content, !generating {
            ToolbarItem(placement: .primaryAction) {
                ShareLink(item: content, subject: Text("\(idea?.title ?? "Idea") — \(kind.title)")) {
                    Label("Share", systemImage: "square.and.arrow.up")
                }
            }
            if canEdit {
                ToolbarItem(placement: .primaryAction) {
                    Menu {
                        Button {
                            draft = content
                            editing = true
                        } label: { Label("Edit", systemImage: "pencil") }
                        Button { confirmRegenerate = true } label: { Label("Regenerate", systemImage: "arrow.clockwise") }
                        Button {
                            copyToPasteboard(content)
                            toast = Toast(message: "Copied", symbol: "doc.on.doc")
                        } label: { Label("Copy Markdown", systemImage: "doc.on.doc") }
                    } label: {
                        Label("More", systemImage: "ellipsis")
                    }
                }
            }
        }
    }

    private func generate() {
        guard !generating else { return }
        let description = [idea?.title, idea?.description].compactMap { $0?.nilIfEmpty }.joined(separator: "\n\n")
        guard !description.isEmpty else {
            error = "Add a description to the idea first."
            return
        }
        error = nil
        startedAt = .now
        withAnimation(Theme.spring) { generating = true }
        Task {
            do {
                let text = try await API.generate(kind, ideaId: ideaID, description: description)
                let refreshed = try? await API.idea(ideaID)
                withAnimation(Theme.spring) {
                    if let refreshed {
                        idea = refreshed
                    } else {
                        set(text)
                    }
                    generating = false
                }
                if let current = idea { store.upsert(current) }
                Haptics.success()
            } catch {
                withAnimation(Theme.spring) { generating = false }
                if let api = error as? APIError, api == .cancelled { return }
                self.error = error.localizedDescription
                Haptics.error()
            }
        }
    }

    private func save() {
        let text = draft
        Task {
            do {
                try await API.saveDocument(ideaId: ideaID, kind: kind, content: text)
                set(text)
                if let current = idea { store.upsert(current) }
                editing = false
                toast = Toast(message: "Saved")
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    private func set(_ text: String) {
        switch kind {
        case .pitchDeck: idea?.pitchDeck = text
        case .prd: idea?.productRequirementsDocument = text
        case .patent: idea?.provisionalPatent = text
        case .similar: idea?.similarIdeas = text
        }
    }
}

/// Honest progress for a long AI call: what is happening, and for how long.
struct GeneratingView: View {
    let kind: DocumentKind
    let startedAt: Date
    private let steps = ["Reading your idea", "Studying the market", "Structuring the argument", "Writing", "Polishing"]

    var body: some View {
        TimelineView(.periodic(from: startedAt, by: 1)) { context in
            let elapsed = Int(context.date.timeIntervalSince(startedAt))
            let step = min(elapsed / 12, steps.count - 1)
            VStack(spacing: 18) {
                ProgressView()
                    .controlSize(.large)
                Text(steps[step] + "…")
                    .font(.headline)
                    .contentTransition(.opacity)
                    .animation(.easeInOut, value: step)
                Text("Usually under a minute. You can leave this screen; it keeps going.")
                    .font(.subheadline)
                    .foregroundStyle(Theme.secondaryText)
                    .multilineTextAlignment(.center)
                Text(Duration.seconds(elapsed).formatted(.time(pattern: .minuteSecond)))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(Theme.tertiaryText)
            }
            .frame(maxWidth: .infinity)
            .card(padding: 32)
        }
        .accessibilityElement(children: .combine)
    }
}

func copyToPasteboard(_ text: String) {
    #if os(macOS)
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(text, forType: .string)
    #else
    UIPasteboard.general.string = text
    #endif
}
