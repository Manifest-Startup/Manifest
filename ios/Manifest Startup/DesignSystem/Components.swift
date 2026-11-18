import SwiftUI

// MARK: Cards

struct CardModifier: ViewModifier {
    var padding: CGFloat = 18
    func body(content: Content) -> some View {
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.surface, in: .rect(cornerRadius: Theme.radius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: Theme.radius, style: .continuous)
                    .strokeBorder(Theme.hairline, lineWidth: 0.5)
            }
    }
}

extension View {
    func card(padding: CGFloat = 18) -> some View { modifier(CardModifier(padding: padding)) }

    /// Springy press feedback for custom tappable surfaces.
    func pressable() -> some View { buttonStyle(PressableStyle()) }

    /// A shared background for every scrolling screen.
    func screenBackground() -> some View {
        background(Theme.background.ignoresSafeArea())
    }
}

struct PressableStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.975 : 1)
            .opacity(configuration.isPressed ? 0.92 : 1)
            .animation(.spring(response: 0.25, dampingFraction: 0.7), value: configuration.isPressed)
    }
}

// MARK: Buttons

/// The one prominent action on a screen.
struct PrimaryButton: View {
    let title: String
    var symbol: String?
    var isLoading = false
    var role: ButtonRole?
    let action: () -> Void

    var body: some View {
        Button(role: role, action: action) {
            HStack(spacing: 8) {
                if isLoading {
                    ProgressView().tint(.white)
                } else if let symbol {
                    Image(systemName: symbol)
                }
                Text(title).fontWeight(.semibold)
            }
            .frame(maxWidth: .infinity, minHeight: 30)
        }
        .glassButtonStyle(prominent: true)
        .controlSize(.large)
        .disabled(isLoading)
    }
}

// MARK: Status

struct StatusPill: View {
    let text: String
    var color: Color = Theme.accent
    var symbol: String?

    var body: some View {
        HStack(spacing: 4) {
            if let symbol { Image(systemName: symbol).imageScale(.small) }
            Text(text)
        }
        .font(.caption.weight(.semibold))
        .padding(.horizontal, 9)
        .padding(.vertical, 4)
        .foregroundStyle(color)
        .background(color.opacity(0.12), in: .capsule)
    }
}

struct PublishBadge: View {
    let isPublished: Bool
    var body: some View {
        Image(systemName: isPublished ? "checkmark.seal.fill" : "checkmark.seal")
            .foregroundStyle(isPublished ? Theme.accent : Theme.tertiaryText)
            .accessibilityLabel(isPublished ? "Published" : "Private")
    }
}

// MARK: States

struct EmptyStateView: View {
    let symbol: String
    let title: String
    let message: String
    var actionTitle: String?
    var action: (() -> Void)?

    var body: some View {
        ContentUnavailableView {
            Label(title, systemImage: symbol)
        } description: {
            Text(message)
        } actions: {
            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .glassButtonStyle(prominent: true)
            }
        }
    }
}

struct ErrorBanner: View {
    let message: String
    var retry: (() -> Void)?

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(Theme.warning)
            Text(message)
                .font(.subheadline)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let retry {
                Button("Retry", action: retry)
                    .font(.subheadline.weight(.semibold))
            }
        }
        .padding(14)
        .glassSurface(.rect(cornerRadius: Theme.smallRadius))
        .transition(.move(edge: .top).combined(with: .opacity))
    }
}

/// Shimmering placeholder rows while the first load is in flight.
struct SkeletonCard: View {
    @State private var phase: CGFloat = -1

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            RoundedRectangle(cornerRadius: 6).frame(width: 180, height: 16)
            RoundedRectangle(cornerRadius: 6).frame(height: 12)
            RoundedRectangle(cornerRadius: 6).frame(width: 240, height: 12)
        }
        .foregroundStyle(Theme.hairline)
        .card()
        .overlay {
            GeometryReader { proxy in
                LinearGradient(colors: [.clear, .white.opacity(0.25), .clear], startPoint: .leading, endPoint: .trailing)
                    .frame(width: proxy.size.width * 0.5)
                    .offset(x: phase * proxy.size.width * 1.5)
            }
            .clipShape(.rect(cornerRadius: Theme.radius))
            .allowsHitTesting(false)
        }
        .onAppear {
            withAnimation(.linear(duration: 1.3).repeatForever(autoreverses: false)) { phase = 1 }
        }
        .accessibilityHidden(true)
    }
}

/// A toast that confirms an action without blocking the screen.
struct Toast: Equatable {
    let message: String
    var symbol = "checkmark.circle.fill"
}

struct ToastModifier: ViewModifier {
    @Binding var toast: Toast?

    func body(content: Content) -> some View {
        content.overlay(alignment: .top) {
            if let toast {
                Label(toast.message, systemImage: toast.symbol)
                    .font(.subheadline.weight(.semibold))
                    .padding(.horizontal, 16)
                    .padding(.vertical, 11)
                    .glassSurface(.capsule)
                    .padding(.top, 8)
                    .transition(.move(edge: .top).combined(with: .opacity))
                    .task(id: toast) {
                        try? await Task.sleep(for: .seconds(2.2))
                        withAnimation(Theme.spring) { self.toast = nil }
                    }
                    .accessibilityAddTraits(.isStaticText)
            }
        }
        .animation(Theme.spring, value: toast)
    }
}

extension View {
    func toast(_ toast: Binding<Toast?>) -> some View { modifier(ToastModifier(toast: toast)) }
}

// MARK: Metrics

struct MetricTile: View {
    let label: String
    let value: String
    var symbol: String?
    var tint: Color = Theme.accent

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                if let symbol { Image(systemName: symbol).foregroundStyle(tint) }
                Text(label).eyebrowStyle()
            }
            Text(value)
                .font(.metric)
                .contentTransition(.numericText())
                .minimumScaleFactor(0.6)
                .lineLimit(1)
        }
        .card(padding: 16)
        .accessibilityElement(children: .combine)
    }
}

// MARK: Formatting

enum Format {
    static func currency(_ value: Double) -> String {
        value.formatted(.currency(code: "USD").precision(.fractionLength(value >= 1000 || value == 0 ? 0 : 2)).notation(value >= 100_000 ? .compactName : .automatic))
    }

    static func percent(_ value: Double) -> String {
        (value / 100).formatted(.percent.precision(.fractionLength(0...2)))
    }

    static func relative(_ date: Date) -> String {
        if abs(date.timeIntervalSinceNow) < 60 { return "Just now" }
        return date.formatted(.relative(presentation: .named, unitsStyle: .abbreviated))
    }

    static func count(_ value: Int) -> String {
        value.formatted(.number.notation(.compactName))
    }
}

// MARK: Platform adapters
// Liquid Glass on iOS, iPadOS and macOS; materials on visionOS, which has its own glass.

extension View {
    @ViewBuilder
    func glassButtonStyle(prominent: Bool = false) -> some View {
        #if os(visionOS)
        if prominent { buttonStyle(.borderedProminent) } else { buttonStyle(.bordered) }
        #else
        if prominent { buttonStyle(.glassProminent) } else { buttonStyle(.glass) }
        #endif
    }

    @ViewBuilder
    func glassSurface<S: Shape>(_ shape: S, clear: Bool = false) -> some View {
        #if os(visionOS)
        background(.regularMaterial, in: shape)
        #else
        glassEffect(clear ? .clear.interactive() : .regular, in: shape)
        #endif
    }

    @ViewBuilder
    func keyboardDismissOnScroll() -> some View {
        #if os(visionOS)
        self
        #else
        scrollDismissesKeyboard(.interactively)
        #endif
    }
}
