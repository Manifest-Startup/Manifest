import SwiftUI

struct ShortsView: View {
    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Image(systemName: "play.rectangle.fill")
                    .font(.system(size: 48))
                    .foregroundStyle(.secondary)
                
                Text("Pitch Shorts")
                    .font(.title2)
                    .fontWeight(.semibold)
                
                Text("Quick video pitches from founders")
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                
                Text("Coming Soon")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .padding(.top, 8)
            }
            .padding()
            .navigationTitle("Shorts")
        }
    }
}

#Preview {
    ShortsView()
}
