import SwiftUI

/// Capture an idea in the person's own words. Title is optional: if they only
/// write the description, the first sentence becomes the title.
struct NewIdeaSheet: View {
    @Environment(IdeasStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    let onCreated: (Idea) -> Void

    @State private var title = ""
    @State private var details = ""
    @State private var saving = false
    @State private var error: String?
    @FocusState private var focus: Field?

    private enum Field { case title, details }

    private var derivedTitle: String {
        if let t = title.nilIfEmpty { return t.trimmed }
        let sentence = details.trimmed.split(whereSeparator: { ".!?\n".contains($0) }).first.map(String.init) ?? ""
        return String(sentence.prefix(80)).trimmed
    }

    private var canSave: Bool { !derivedTitle.isEmpty && !saving }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    TextField("Name it (optional)", text: $title, axis: .vertical)
                        .font(.title2.weight(.semibold))
                        .focused($focus, equals: .title)
                        .submitLabel(.next)
                        .onSubmit { focus = .details }
                        .accessibilityIdentifier("ideaTitle")

                    TextField(
                        "What's the idea? Who has the problem, and what would you build for them?",
                        text: $details, axis: .vertical
                    )
                    .font(.body)
                    .lineSpacing(4)
                    .lineLimit(6...)
                    .focused($focus, equals: .details)
                    .accessibilityIdentifier("ideaDetails")

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Prompts that help").eyebrowStyle()
                        ForEach(prompts, id: \.self) { prompt in
                            Button {
                                details += (details.isEmpty || details.hasSuffix("\n") ? "" : "\n") + prompt + " "
                                focus = .details
                                Haptics.select()
                            } label: {
                                Label(prompt, systemImage: "plus.circle")
                                    .font(.subheadline)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(Theme.accent)
                        }
                    }
                    .padding(.top, 8)

                    if let error { ErrorBanner(message: error) }
                }
                .padding(Theme.gutter)
            }
            .keyboardDismissOnScroll()
            .navigationTitle("New idea")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel", role: .cancel) { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        save()
                    } label: {
                        if saving { ProgressView() } else { Text("Create").fontWeight(.semibold) }
                    }
                    .disabled(!canSave)
                    .accessibilityIdentifier("createIdea")
                }
            }
            .onAppear { focus = .title }
        }
        .presentationDetents([.large])
        .interactiveDismissDisabled(!details.isEmpty || !title.isEmpty)
    }

    private let prompts = [
        "The people who feel this most are",
        "Today they get by with",
        "What I'd build first is",
        "It makes money by",
    ]

    private func save() {
        saving = true
        error = nil
        Task {
            do {
                let idea = try await store.create(title: derivedTitle, description: details.nilIfEmpty?.trimmed)
                Haptics.success()
                dismiss()
                onCreated(idea)
            } catch {
                self.error = error.localizedDescription
                saving = false
            }
        }
    }
}
