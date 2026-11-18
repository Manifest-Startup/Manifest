import SwiftUI

/// First impression: the mark drawing itself, a single line of promise, one
/// way in (Open Media via the web sheet), and a guest path to look around.
struct SignInView: View {
    @Environment(SessionModel.self) private var session
    @State private var drawn: CGFloat = 0
    @State private var revealed = false
    @State private var page = 0

    private let pages: [(symbol: String, title: String, body: String)] = [
        ("lightbulb.max", "Start with a rough idea", "Write it the way you'd say it out loud. Manifest asks the questions an investor would."),
        ("square.grid.3x3", "Watch it become a plan", "A business model canvas, pitch deck, PRD and patent draft, generated from your words."),
        ("person.2.wave.2", "Build it with people", "Share pitch shorts, find collaborators and track every stake on a clean cap table."),
    ]

    var body: some View {
        ZStack {
            AmbientBackground()

            VStack(spacing: 0) {
                Spacer(minLength: 40)

                ManifestMark(size: 76, progress: drawn)
                    .shadow(color: .black.opacity(0.15), radius: 18, y: 10)

                Text("Manifest")
                    .font(.system(size: 40, weight: .bold))
                    .tracking(-0.8)
                    .padding(.top, 22)
                    .opacity(revealed ? 1 : 0)
                    .offset(y: revealed ? 0 : 8)

                Text("From a rough idea to an investable plan.")
                    .font(.title3)
                    .foregroundStyle(Theme.secondaryText)
                    .multilineTextAlignment(.center)
                    .padding(.top, 6)
                    .opacity(revealed ? 1 : 0)

                TabView(selection: $page) {
                    ForEach(pages.indices, id: \.self) { index in
                        FeatureCard(symbol: pages[index].symbol, title: pages[index].title, message: pages[index].body)
                            .padding(.horizontal, 28)
                            .tag(index)
                    }
                }
                #if os(iOS)
                .tabViewStyle(.page(indexDisplayMode: .always))
                .indexViewStyle(.page(backgroundDisplayMode: .interactive))
                #endif
                .frame(height: 230)
                .padding(.top, 28)
                .opacity(revealed ? 1 : 0)

                Spacer(minLength: 24)

                VStack(spacing: 12) {
                    if let error = session.error {
                        ErrorBanner(message: error)
                    }

                    Button {
                        Task { await session.signIn() }
                    } label: {
                        HStack(spacing: 10) {
                            if session.isWorking {
                                ProgressView().tint(.white)
                            } else {
                                Image("OpenMediaMark")
                                    .resizable()
                                    .frame(width: 20, height: 20)
                                    .clipShape(.rect(cornerRadius: 5))
                            }
                            Text("Continue with Open Media").fontWeight(.semibold)
                        }
                        .frame(maxWidth: .infinity, minHeight: 30)
                    }
                    .glassButtonStyle(prominent: true)
                    .controlSize(.large)
                    .disabled(session.isWorking)
                    .accessibilityIdentifier("signIn")

                    Button("Look around as a guest") {
                        Task { await session.continueAsGuest() }
                    }
                    .font(.subheadline.weight(.medium))
                    .glassButtonStyle()
                    .controlSize(.large)
                    .disabled(session.isWorking)
                    .accessibilityIdentifier("guest")

                    Text("By continuing you agree to the [Terms](https://manifeststartup.com/legal/terms) and [Privacy Policy](https://manifeststartup.com/legal/privacy).")
                        .font(.caption)
                        .foregroundStyle(Theme.tertiaryText)
                        .multilineTextAlignment(.center)
                        .padding(.top, 4)
                }
                .frame(maxWidth: 420)
                .padding(.horizontal, 24)
                .padding(.bottom, 20)
                .opacity(revealed ? 1 : 0)
                .offset(y: revealed ? 0 : 20)
            }
        }
        .onAppear {
            withAnimation(.easeInOut(duration: 0.9)) { drawn = 1 }
            withAnimation(Theme.spring.delay(0.35)) { revealed = true }
        }
        .task {
            // Gently advance the feature cards until the person takes over.
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(4.5))
                withAnimation(Theme.spring) { page = (page + 1) % pages.count }
            }
        }
    }
}

private struct FeatureCard: View {
    let symbol: String
    let title: String
    let message: String

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: symbol)
                .font(.system(size: 30, weight: .medium))
                .foregroundStyle(Theme.accent)
                .symbolRenderingMode(.hierarchical)
                .frame(width: 60, height: 60)
                .glassSurface(.circle)
            Text(title).font(.headline)
            Text(message)
                .font(.subheadline)
                .foregroundStyle(Theme.secondaryText)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.bottom, 36)
        .frame(maxWidth: 420)
    }
}

/// Slow-moving colour fields behind the glass. Cheap: three blurred circles
/// animated by TimelineView at a low frame rate.
struct AmbientBackground: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 20, paused: reduceMotion)) { context in
            let t = context.date.timeIntervalSinceReferenceDate / 9
            GeometryReader { proxy in
                let w = proxy.size.width, h = proxy.size.height
                ZStack {
                    Theme.background
                    Circle().fill(Color(hex: 0x0A84FF).opacity(0.28))
                        .frame(width: w * 0.9).blur(radius: 80)
                        .position(x: w * (0.2 + 0.1 * sin(t)), y: h * (0.18 + 0.05 * cos(t * 1.3)))
                    Circle().fill(Color(hex: 0x5E5CE6).opacity(0.22))
                        .frame(width: w * 0.8).blur(radius: 90)
                        .position(x: w * (0.85 + 0.08 * cos(t * 0.8)), y: h * (0.4 + 0.06 * sin(t)))
                    Circle().fill(Color(hex: 0x30B0C7).opacity(0.18))
                        .frame(width: w * 0.7).blur(radius: 90)
                        .position(x: w * (0.4 + 0.1 * sin(t * 0.7)), y: h * (0.85 + 0.04 * cos(t)))
                }
            }
        }
        .ignoresSafeArea()
        .drawingGroup()
        .accessibilityHidden(true)
    }
}

#Preview {
    SignInView().environment(SessionModel())
}
