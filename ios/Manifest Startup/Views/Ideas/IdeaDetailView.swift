import SwiftUI

struct IdeaDetailView: View {
    let idea: Idea
    @State private var selectedSection = 0
    
    private let sections = ["Description", "Pitch Deck", "Business Model", "Patent"]
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack {
                    Text(idea.title)
                        .font(.title)
                        .fontWeight(.bold)
                    
                    Spacer()
                    
                    Image(systemName: "checkmark.seal.fill")
                        .foregroundStyle(idea.isPublished ? .blue : .gray)
                }
                .padding(.horizontal)
                
                Picker("Section", selection: $selectedSection) {
                    ForEach(0..<sections.count, id: \.self) { index in
                        Text(sections[index]).tag(index)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)
                
                VStack(alignment: .leading, spacing: 16) {
                    switch selectedSection {
                    case 0:
                        DescriptionSection(description: idea.description)
                    case 1:
                        PitchDeckSection(pitchDeck: idea.pitchDeck)
                    case 2:
                        BusinessModelSection(canvas: idea.businessModelCanvas)
                    case 3:
                        PatentSection()
                    default:
                        EmptyView()
                    }
                }
                .padding(.horizontal)
            }
            .padding(.vertical)
        }
#if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
#endif
    }
}

struct DescriptionSection: View {
    let description: String?
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Description")
                .font(.headline)
            
            if let description = description, !description.isEmpty {
                Text(description.replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression))
                    .foregroundStyle(.secondary)
            } else {
                Text("No description yet")
                    .foregroundStyle(.tertiary)
                    .italic()
            }
        }
    }
}

struct PitchDeckSection: View {
    let pitchDeck: String?
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Pitch Deck")
                .font(.headline)
            
            if let pitchDeck = pitchDeck, !pitchDeck.isEmpty {
                Text(pitchDeck)
                    .foregroundStyle(.secondary)
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "doc.richtext")
                        .font(.largeTitle)
                        .foregroundStyle(.tertiary)
                    Text("No pitch deck generated")
                        .foregroundStyle(.tertiary)
                    Button("Generate Pitch Deck") {
                    }
                    .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 24)
            }
        }
    }
}

struct BusinessModelSection: View {
    let canvas: BusinessModelCanvas?
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Business Model Canvas")
                .font(.headline)
            
            if let canvas = canvas {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                    CanvasCard(title: "Key Partners", content: canvas.keyPartners)
                    CanvasCard(title: "Key Activities", content: canvas.keyActivities)
                    CanvasCard(title: "Key Resources", content: canvas.keyResources)
                    CanvasCard(title: "Value Propositions", content: canvas.valuePropositions)
                    CanvasCard(title: "Customer Relationships", content: canvas.customerRelationships)
                    CanvasCard(title: "Channels", content: canvas.channels)
                    CanvasCard(title: "Customer Segments", content: canvas.customerSegments)
                    CanvasCard(title: "Revenue Streams", content: canvas.revenueStreams)
                }
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "square.grid.3x3")
                        .font(.largeTitle)
                        .foregroundStyle(.tertiary)
                    Text("No business model canvas generated")
                        .foregroundStyle(.tertiary)
                    Button("Generate Business Model") {
                    }
                    .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 24)
            }
        }
    }
}

struct CanvasCard: View {
    let title: String
    let content: String?
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption)
                .fontWeight(.medium)
                .foregroundStyle(.secondary)
            
            Text(content ?? "Not set")
                .font(.subheadline)
                .foregroundStyle(content == nil ? .tertiary : .primary)
                .lineLimit(3)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(
            {
#if os(iOS)
                Color(.systemGray6)
#else
                Color.gray.opacity(0.12)
#endif
            }()
        )
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

struct PatentSection: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Provisional Patent")
                .font(.headline)
            
            VStack(spacing: 8) {
                Image(systemName: "doc.badge.gearshape")
                    .font(.largeTitle)
                    .foregroundStyle(.tertiary)
                Text("No patent generated")
                    .foregroundStyle(.tertiary)
                Button("Generate Patent") {
                }
                .buttonStyle(.bordered)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 24)
        }
    }
}

#Preview {
    NavigationStack {
        IdeaDetailView(idea: Idea(
            id: "1",
            title: "Sample Idea",
            description: "This is a sample description",
            isPublished: true,
            pitchDeck: nil,
            businessModelCanvas: nil,
            createdAt: nil,
            updatedAt: nil
        ))
    }
}
