import SwiftUI

/// Manifest's visual language on Apple platforms: ink and paper, one confident
/// blue, generous whitespace, and Liquid Glass for anything that floats.
enum Theme {
    // Brand
    static let ink = Color(light: 0x1D1D1F, dark: 0xF5F5F7)
    static let accent = Color(light: 0x0071E3, dark: 0x2997FF)
    static let accentSoft = Color(light: 0xEEF5FF, dark: 0x0A2540)
    static let success = Color(light: 0x1D8A3A, dark: 0x30D158)
    static let warning = Color(light: 0xC25E00, dark: 0xFF9F0A)
    static let danger = Color(light: 0xE30000, dark: 0xFF453A)

    // Surfaces
    static let background = Color(light: 0xF5F5F7, dark: 0x000000)
    static let surface = Color(light: 0xFFFFFF, dark: 0x1C1C1E)
    static let surfaceRaised = Color(light: 0xFFFFFF, dark: 0x2C2C2E)
    static let hairline = Color.primary.opacity(0.08)

    // Text
    static let secondaryText = Color(light: 0x6E6E73, dark: 0xA1A1A6)
    static let tertiaryText = Color(light: 0x86868B, dark: 0x86868B)

    // Geometry
    static let radius: CGFloat = 22
    static let smallRadius: CGFloat = 14
    static let gutter: CGFloat = 20
    static let spacing: CGFloat = 12

    static let spring = Animation.spring(response: 0.42, dampingFraction: 0.86)
    static let snappy = Animation.snappy(duration: 0.28)

    /// Deterministic two-stop gradient for an idea, so each one keeps its own colour.
    static func gradient(for seed: String) -> LinearGradient {
        let palettes: [(UInt32, UInt32)] = [
            (0x0A84FF, 0x5E5CE6), (0x30B0C7, 0x0A84FF), (0xFF9F0A, 0xFF375F), (0x34C759, 0x30B0C7),
            (0xBF5AF2, 0x5E5CE6), (0xFF375F, 0xBF5AF2), (0x64D2FF, 0x34C759), (0xFFD60A, 0xFF9F0A),
        ]
        var hash: UInt64 = 1469598103934665603
        for byte in seed.utf8 { hash = (hash ^ UInt64(byte)) &* 1099511628211 }
        let pair = palettes[Int(hash % UInt64(palettes.count))]
        return LinearGradient(
            colors: [Color(hex: pair.0), Color(hex: pair.1)],
            startPoint: .topLeading, endPoint: .bottomTrailing
        )
    }
}

extension Color {
    init(hex: UInt32, opacity: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: opacity
        )
    }

    /// Parses "#RRGGBB" from the API; falls back to the accent.
    init(hexString: String?) {
        let cleaned = (hexString ?? "").trimmingCharacters(in: CharacterSet(charactersIn: "# "))
        if cleaned.count == 6, let value = UInt32(cleaned, radix: 16) {
            self.init(hex: value)
        } else {
            self = Theme.accent
        }
    }

    init(light: UInt32, dark: UInt32) {
        #if os(macOS)
        self.init(nsColor: NSColor(name: nil) { appearance in
            appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
                ? NSColor(Color(hex: dark)) : NSColor(Color(hex: light))
        })
        #else
        self.init(uiColor: UIColor { traits in
            traits.userInterfaceStyle == .dark ? UIColor(Color(hex: dark)) : UIColor(Color(hex: light))
        })
        #endif
    }
}

// MARK: Typography

extension Font {
    static let display = Font.system(size: 34, weight: .bold, design: .default)
    static let cardTitle = Font.system(.title3, design: .default, weight: .semibold)
    static let eyebrow = Font.system(.caption, design: .default, weight: .semibold)
    static let metric = Font.system(.title, design: .rounded, weight: .semibold).monospacedDigit()
}

extension View {
    /// Small caps-style section label.
    func eyebrowStyle(_ color: Color = Theme.secondaryText) -> some View {
        font(.eyebrow).textCase(.uppercase).tracking(0.6).foregroundStyle(color)
    }
}
