import SwiftUI

/// The nine-box Business Model Canvas. A readable stack on iPhone, the classic
/// canvas grid on iPad and Mac. Each box can be edited or regenerated alone.
struct CanvasView: View {
    let ideaID: String
    let description: String
    @Binding var sections: [BmcSection]

    @Environment(\.horizontalSizeClass) private var sizeClass
    @State private var editing: BmcSection?
    @State private var regenerating: Set<String> = []
    @State private var regeneratingAll = false
    @State private var error: String?
    @State private var startedAt = Date.now

    private func section(_ meta: CanvasSection) -> BmcSection {
        sections.first { $0.sectionName == meta.rawValue }
            ?? BmcSection(sectionName: meta.rawValue, content: nil, contentFormat: "markdown", needsUserReview: false)
    }

    private var isEmpty: Bool { !sections.contains(where: \.hasContent) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let error { ErrorBanner(message: error) }

                if regeneratingAll {
                    GeneratingCanvas(startedAt: startedAt)
                } else if isEmpty {
                    VStack(spacing: 14) {
                        Image(systemName: "square.grid.3x3.fill")
                            .font(.system(size: 36))
                            .foregroundStyle(Theme.accent.gradient)
                        Text("Draft the whole canvas").font(.headline)
                        Text("Nine sections, each written from your idea. Edit any of them after.")
                            .font(.subheadline).foregroundStyle(Theme.secondaryText).multilineTextAlignment(.center)
                        PrimaryButton(title: "Generate canvas", symbol: "sparkles") { regenerateAll() }
                            .frame(maxWidth: 300)
                    }
                    .frame(maxWidth: .infinity)
                    .card(padding: 28)
                }

                if sizeClass == .regular {
                    wideCanvas
                } else {
                    ForEach(CanvasSection.readingOrder, id: \.self) { meta in
                        box(meta, lines: nil)
                    }
                }
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 60)
        }
        .screenBackground()
        .navigationTitle("Business Model")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar {
            if !isEmpty {
                ToolbarItem(placement: .primaryAction) {
                    Menu {
                        Button { regenerateAll() } label: { Label("Regenerate all", systemImage: "sparkles") }
                        ShareLink(item: markdownExport) { Label("Share as text", systemImage: "square.and.arrow.up") }
                    } label: {
                        Label("More", systemImage: "ellipsis")
                    }
                    .disabled(regeneratingAll)
                }
            }
        }
        .sheet(item: $editing) { section in
            CanvasSectionEditor(ideaID: ideaID, section: section) { saved in replace(saved) }
        }
        .task {
            if sections.isEmpty, let loaded = try? await API.canvas(ideaId: ideaID) { sections = loaded }
        }
    }

    private var wideCanvas: some View {
        Grid(horizontalSpacing: 10, verticalSpacing: 10) {
            GridRow {
                box(.keyPartners, lines: 14)
                VStack(spacing: 10) { box(.keyActivities, lines: 5); box(.keyResources, lines: 5) }
                box(.valuePropositions, lines: 14)
                VStack(spacing: 10) { box(.customerRelationships, lines: 5); box(.channels, lines: 5) }
                box(.customerSegments, lines: 14)
            }
            GridRow {
                HStack(spacing: 10) { box(.costStructure, lines: 6); box(.revenueStreams, lines: 6) }
                    .gridCellColumns(5)
            }
        }
    }

    private func box(_ meta: CanvasSection, lines: Int?) -> some View {
        let item = section(meta)
        let busy = regenerating.contains(meta.rawValue) || regeneratingAll
        return Button {
            editing = item
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Label(meta.title, systemImage: meta.symbol)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    if busy {
                        ProgressView().controlSize(.small)
                    } else if item.needsUserReview {
                        StatusPill(text: "Review", color: Theme.warning)
                    }
                }
                if let content = item.content?.nilIfEmpty {
                    Text(LocalizedStringKey(content))
                        .font(.subheadline)
                        .foregroundStyle(.primary.opacity(0.85))
                        .lineLimit(lines)
                        .multilineTextAlignment(.leading)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    Text(meta.prompt)
                        .font(.subheadline)
                        .foregroundStyle(Theme.tertiaryText)
                }
                if lines != nil { Spacer(minLength: 0) }
            }
            .frame(maxWidth: .infinity, maxHeight: lines == nil ? nil : .infinity, alignment: .topLeading)
            .card(padding: 14)
            .redacted(reason: busy ? .placeholder : [])
        }
        .pressable()
        .contextMenu {
            Button { editing = item } label: { Label("Edit", systemImage: "pencil") }
            Button { regenerate(meta) } label: { Label("Regenerate", systemImage: "sparkles") }
        }
    }

    private var markdownExport: String {
        CanvasSection.readingOrder.map { meta in
            "## \(meta.title)\n\n\(section(meta).content ?? "—")"
        }
        .joined(separator: "\n\n")
    }

    private func replace(_ saved: BmcSection) {
        if let i = sections.firstIndex(where: { $0.sectionName == saved.sectionName }) {
            sections[i] = saved
        } else {
            sections.append(saved)
        }
    }

    private func regenerate(_ meta: CanvasSection) {
        regenerating.insert(meta.rawValue)
        Task {
            do {
                replace(try await API.regenerateCanvasSection(ideaId: ideaID, section: meta.rawValue))
                Haptics.success()
            } catch {
                self.error = error.localizedDescription
            }
            regenerating.remove(meta.rawValue)
        }
    }

    private func regenerateAll() {
        error = nil
        startedAt = .now
        withAnimation(Theme.spring) { regeneratingAll = true }
        Task {
            do {
                let fresh = try await API.regenerateCanvas(ideaId: ideaID)
                withAnimation(Theme.spring) { sections = fresh }
                Haptics.success()
            } catch {
                self.error = error.localizedDescription
            }
            withAnimation(Theme.spring) { regeneratingAll = false }
        }
    }
}

private struct GeneratingCanvas: View {
    let startedAt: Date
    var body: some View {
        HStack(spacing: 14) {
            ProgressView()
            VStack(alignment: .leading, spacing: 2) {
                Text("Drafting nine sections…").font(.headline)
                TimelineView(.periodic(from: startedAt, by: 1)) { context in
                    Text("Each one builds on the last. \(Int(context.date.timeIntervalSince(startedAt)))s")
                        .font(.caption.monospacedDigit()).foregroundStyle(Theme.secondaryText)
                }
            }
        }
        .card()
    }
}

private struct CanvasSectionEditor: View {
    let ideaID: String
    let section: BmcSection
    let onSave: (BmcSection) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var text: String
    @State private var saving = false
    @State private var error: String?

    init(ideaID: String, section: BmcSection, onSave: @escaping (BmcSection) -> Void) {
        self.ideaID = ideaID
        self.section = section
        self.onSave = onSave
        _text = State(initialValue: section.content ?? "")
    }

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 10) {
                Text(section.meta.prompt).font(.subheadline).foregroundStyle(Theme.secondaryText)
                TextEditor(text: $text)
                    .font(.body)
                    .scrollContentBackground(.hidden)
                    .padding(10)
                    .background(Theme.surface, in: .rect(cornerRadius: Theme.smallRadius))
                if let error { Text(error).font(.caption).foregroundStyle(Theme.danger) }
            }
            .padding(Theme.gutter)
            .screenBackground()
            .navigationTitle(section.meta.title)
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel", role: .cancel) { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        save()
                    } label: {
                        if saving { ProgressView() } else { Text("Save").fontWeight(.semibold) }
                    }
                    .disabled(saving)
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private func save() {
        saving = true
        Task {
            do {
                onSave(try await API.saveCanvasSection(ideaId: ideaID, section: section.sectionName, content: text))
                Haptics.success()
                dismiss()
            } catch {
                self.error = error.localizedDescription
                saving = false
            }
        }
    }
}
