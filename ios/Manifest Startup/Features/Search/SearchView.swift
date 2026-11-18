import SwiftUI

/// Search your ideas and everything published on Manifest, with debounced
/// live results and an assistant summary when there is one.
struct SearchView: View {
    @State private var query = ""
    @State private var results: SearchResults?
    @State private var searching = false
    @State private var error: String?
    @AppStorage("recentSearches") private var recentRaw = ""

    private var recents: [String] { recentRaw.split(separator: "\n").map(String.init) }

    var body: some View {
        NavigationStack {
            List {
                if query.trimmed.isEmpty {
                    if !recents.isEmpty {
                        Section {
                            ForEach(recents, id: \.self) { recent in
                                Button {
                                    query = recent
                                } label: {
                                    Label(recent, systemImage: "clock.arrow.circlepath").foregroundStyle(Theme.ink)
                                }
                            }
                        } header: {
                            HStack {
                                Text("Recent")
                                Spacer()
                                Button("Clear") { recentRaw = "" }.font(.caption)
                            }
                        }
                    }
                } else if let results {
                    if let summary = results.assistantSummary?.nilIfEmpty {
                        Section {
                            Label {
                                Text(LocalizedStringKey(summary)).font(.subheadline)
                            } icon: {
                                Image(systemName: "sparkles").foregroundStyle(Theme.accent)
                            }
                        }
                    }
                    if !results.myIdeas.isEmpty {
                        Section("Your ideas") {
                            ForEach(results.myIdeas) { row($0) }
                        }
                    }
                    if !results.publishedIdeas.isEmpty {
                        Section("On Manifest") {
                            ForEach(results.publishedIdeas) { row($0) }
                        }
                    }
                }
                if let error { Section { Text(error).foregroundStyle(Theme.danger) } }
            }
            .overlay {
                if query.trimmed.isEmpty && recents.isEmpty {
                    ContentUnavailableView("Search Manifest", systemImage: "magnifyingglass",
                                           description: Text("Find your ideas and ones founders have published."))
                } else if let results, results.myIdeas.isEmpty, results.publishedIdeas.isEmpty, !searching {
                    ContentUnavailableView.search(text: query)
                }
            }
            .searchable(text: $query, prompt: "Ideas, markets, people")
            .onSubmit(of: .search) { remember(query) }
            .task(id: query) { await search() }
            .navigationTitle("Search")
            .navigationDestination(for: IdeaRoute.self) { IdeaDetailView(ideaID: $0.id) }
        }
    }

    private func row(_ idea: SearchIdea) -> some View {
        NavigationLink(value: IdeaRoute(id: idea.ideaId)) {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(idea.title).font(.headline)
                    if idea.isPublished { PublishBadge(isPublished: true).imageScale(.small) }
                }
                Text(idea.snippet).font(.subheadline).foregroundStyle(Theme.secondaryText).lineLimit(2)
                if let creator = idea.creatorName {
                    Text(creator).font(.caption).foregroundStyle(Theme.tertiaryText)
                }
            }
            .padding(.vertical, 2)
        }
        .simultaneousGesture(TapGesture().onEnded { remember(query) })
    }

    private func search() async {
        let q = query.trimmed
        guard q.count >= 2 else {
            results = nil
            return
        }
        // Debounce: .task(id:) cancels this when the query changes again.
        try? await Task.sleep(for: .milliseconds(320))
        guard !Task.isCancelled else { return }
        searching = true
        do {
            let found = try await API.search(q)
            guard !Task.isCancelled else { return }
            withAnimation(Theme.snappy) { results = found }
            error = nil
        } catch {
            if (error as? APIError) != .cancelled { self.error = error.localizedDescription }
        }
        searching = false
    }

    private func remember(_ term: String) {
        let t = term.trimmed
        guard !t.isEmpty else { return }
        recentRaw = ([t] + recents.filter { $0 != t }).prefix(8).joined(separator: "\n")
    }
}
