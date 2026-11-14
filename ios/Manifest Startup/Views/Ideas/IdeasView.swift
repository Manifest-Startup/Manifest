import SwiftUI

struct IdeasView: View {
    @StateObject private var viewModel = IdeasViewModel()
    @State private var showCreateSheet = false
    @State private var newIdeaTitle = ""
    
    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading {
                    ProgressView()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if viewModel.ideas.isEmpty {
                    EmptyIdeasView(onCreateTapped: { showCreateSheet = true })
                } else {
                    List {
                        ForEach(viewModel.ideas) { idea in
                            NavigationLink(destination: IdeaDetailView(idea: idea)) {
                                IdeaRowView(idea: idea, onTogglePublish: {
                                    Task { await viewModel.togglePublish(idea: idea) }
                                })
                            }
                        }
                        .onDelete { indexSet in
                            for index in indexSet {
                                viewModel.deleteIdea(idea: viewModel.ideas[index])
                            }
                        }
                    }
                    .listStyle(.plain)
                    .refreshable {
                        await viewModel.loadIdeas()
                    }
                }
            }
            .navigationTitle("My Ideas")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        showCreateSheet = true
                    } label: {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $showCreateSheet) {
                CreateIdeaSheet(
                    title: $newIdeaTitle,
                    onCreate: {
                        Task {
                            await viewModel.createIdea(title: newIdeaTitle)
                            newIdeaTitle = ""
                            showCreateSheet = false
                        }
                    },
                    onCancel: {
                        newIdeaTitle = ""
                        showCreateSheet = false
                    }
                )
            }
            .task {
                await viewModel.loadIdeas()
            }
            .alert("Error", isPresented: .constant(viewModel.errorMessage != nil)) {
                Button("OK") { viewModel.errorMessage = nil }
            } message: {
                Text(viewModel.errorMessage ?? "")
            }
        }
    }
}

struct IdeaRowView: View {
    let idea: Idea
    let onTogglePublish: () -> Void
    
    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(idea.title)
                        .font(.headline)
                        .lineLimit(1)
                    
                    PublishBadge(isPublished: idea.isPublished, onTap: onTogglePublish)
                }
                
                if let description = idea.description, !description.isEmpty {
                    Text(description.replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            
            Spacer()
            
            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 4)
    }
}

struct PublishBadge: View {
    let isPublished: Bool
    let onTap: () -> Void
    
    var body: some View {
        Button(action: onTap) {
            Image(systemName: "checkmark.seal.fill")
                .font(.caption)
                .foregroundStyle(isPublished ? .blue : .gray)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(isPublished ? "Published" : "Not published")
    }
}

struct EmptyIdeasView: View {
    let onCreateTapped: () -> Void
    
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "lightbulb")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            
            Text("No ideas yet")
                .font(.title2)
                .fontWeight(.semibold)
            
            Text("Start by creating your first idea")
                .foregroundStyle(.secondary)
            
            Button("Create Your First Idea") {
                onCreateTapped()
            }
            .buttonStyle(.borderedProminent)
        }
        .padding()
    }
}

struct CreateIdeaSheet: View {
    @Binding var title: String
    let onCreate: () -> Void
    let onCancel: () -> Void
    
    var body: some View {
        NavigationStack {
            Form {
                Section("Idea Title") {
                    TextField("Enter a title for your idea", text: $title)
                }
            }
            .navigationTitle("New Idea")
#if !os(macOS)
            .navigationBarTitleDisplayMode(.inline)
#endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel", action: onCancel)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create", action: onCreate)
                        .disabled(title.isEmpty)
                }
            }
        }
        .presentationDetents([.medium])
    }
}

#Preview {
    IdeasView()
}
