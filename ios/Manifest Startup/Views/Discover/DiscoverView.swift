import SwiftUI

struct DiscoverView: View {
    @StateObject private var viewModel = DiscoverViewModel()
    
    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading {
                    ProgressView()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if viewModel.feedItems.isEmpty {
                    EmptyDiscoverView()
                } else {
                    GeometryReader { geometry in
                        TabView(selection: $viewModel.currentIndex) {
                            ForEach(Array(viewModel.feedItems.enumerated()), id: \.element.id) { index, item in
                                FeedCardView(
                                    item: item,
                                    onUpvote: { Task { await viewModel.upvote(item: item) } }
                                )
                                .tag(index)
                            }
                        }
#if os(iOS)
                        .tabViewStyle(.page(indexDisplayMode: .never))
#else
                        .tabViewStyle(DefaultTabViewStyle())
#endif
                        .ignoresSafeArea()
                    }
                }
            }
            .navigationTitle("Discover")
#if os(iOS) || os(tvOS) || os(visionOS)
            .navigationBarTitleDisplayMode(.inline)
#endif
            .task {
                await viewModel.loadFeed()
            }
            .refreshable {
                await viewModel.loadFeed()
            }
        }
    }
}

struct FeedCardView: View {
    let item: FeedItem
    let onUpvote: () -> Void
    
    var body: some View {
        VStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 16) {
                HStack(spacing: 12) {
                    AsyncImage(url: URL(string: item.authorAvatarUrl ?? "")) { image in
                        image.resizable()
                    } placeholder: {
                        Circle()
                        #if os(iOS) || os(tvOS) || os(visionOS)
                        .fill(Color(uiColor: .systemGray4))
                        #elseif os(macOS)
                        .fill(Color(nsColor: .systemGray))
                        #else
                        .fill(Color.gray.opacity(0.3))
                        #endif
                    }
                    .frame(width: 40, height: 40)
                    .clipShape(Circle())
                    
                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.authorName)
                            .font(.headline)
                        Text("Startup Idea")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    
                    Spacer()
                    
                    if item.isPublished {
                        Image(systemName: "checkmark.seal.fill")
                            .foregroundStyle(.blue)
                    }
                }
                
                VStack(alignment: .leading, spacing: 8) {
                    Text(item.title)
                        .font(.title2)
                        .fontWeight(.bold)
                    
                    if let description = item.description, !description.isEmpty {
                        Text(description.replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression))
                            .foregroundStyle(.secondary)
                            .lineLimit(6)
                    }
                }
                
                Spacer()
                
                HStack(spacing: 24) {
                    Button(action: onUpvote) {
                        HStack(spacing: 6) {
                            Image(systemName: item.hasUpvoted ? "heart.fill" : "heart")
                                .foregroundStyle(item.hasUpvoted ? .red : .primary)
                            Text("\(item.upvoteCount)")
                        }
                    }
                    .buttonStyle(.plain)
                    
                    Button {
                    } label: {
                        Image(systemName: "bubble.right")
                    }
                    .buttonStyle(.plain)
                    
                    Button {
                    } label: {
                        Image(systemName: "square.and.arrow.up")
                    }
                    .buttonStyle(.plain)
                    
                    Spacer()
                    
                    Button("Invest") {
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .padding(24)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
#if os(iOS) || os(tvOS) || os(visionOS)
            .background(Color(uiColor: .systemBackground))
#elseif os(macOS)
            .background(Color(nsColor: .windowBackgroundColor))
#else
            .background(Color.white)
#endif
        }
    }
}

struct EmptyDiscoverView: View {
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "globe")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            
            Text("No ideas to discover")
                .font(.title2)
                .fontWeight(.semibold)
            
            Text("Check back later for new ideas from the community")
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding()
    }
}

#Preview {
    DiscoverView()
}
