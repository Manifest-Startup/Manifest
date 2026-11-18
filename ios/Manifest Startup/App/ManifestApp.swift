import AVFoundation
import SwiftUI

@main
struct ManifestApp: App {
    @State private var session = SessionModel()
    @AppStorage(Appearance.storageKey) private var appearance: Appearance = .system

    init() {
        #if os(iOS)
        // Shorts play sound like any video app; mixing politely with other audio.
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback, options: [.mixWithOthers])
        #endif
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(session)
                .preferredColorScheme(appearance.colorScheme)
                .tint(Theme.accent)
        }
        #if os(macOS)
        .defaultSize(width: 1100, height: 760)
        .windowToolbarStyle(.unified)
        #endif
    }
}

enum Appearance: String, CaseIterable, Identifiable {
    case system, light, dark
    static let storageKey = "appearance"
    var id: String { rawValue }
    var title: String { rawValue.capitalized }
    var colorScheme: ColorScheme? {
        switch self {
        case .system: nil
        case .light: .light
        case .dark: .dark
        }
    }
}

/// Launch → sign in → the app. Cross-fades between phases.
struct RootView: View {
    @Environment(SessionModel.self) private var session

    var body: some View {
        ZStack {
            switch session.phase {
            case .launching:
                LaunchView()
                    .transition(.opacity)
            case .signedOut:
                SignInView()
                    .transition(.opacity.combined(with: .scale(scale: 1.02)))
            case .signedIn:
                MainView()
                    .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.35), value: session.phase)
        .task { await session.restore() }
    }
}

private struct LaunchView: View {
    @State private var progress: CGFloat = 0

    var body: some View {
        ManifestMark(size: 84, progress: progress)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Theme.background.ignoresSafeArea())
            .onAppear {
                withAnimation(.easeInOut(duration: 0.7)) { progress = 1 }
            }
    }
}
