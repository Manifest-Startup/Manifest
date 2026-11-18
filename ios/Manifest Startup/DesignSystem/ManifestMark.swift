import SwiftUI

/// The rising M: path `M25 78V35L50 60L75 26V78` in a 100 × 100 box, stroke 11,
/// mitred joins. The right stroke climbs higher, an idea rising into a plan.
nonisolated struct RisingM: Shape {
    func path(in rect: CGRect) -> Path {
        let s = min(rect.width, rect.height) / 100
        let ox = rect.midX - 50 * s
        let oy = rect.midY - 50 * s
        func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: ox + x * s, y: oy + y * s) }
        var path = Path()
        path.move(to: p(25, 78))
        path.addLine(to: p(25, 35))
        path.addLine(to: p(50, 60))
        path.addLine(to: p(75, 26))
        path.addLine(to: p(75, 78))
        return path
    }
}

/// The app-icon tile, or the bare glyph.
struct ManifestMark: View {
    var size: CGFloat = 44
    var tile = true
    /// Draws the strokes in, for the launch moment.
    var progress: CGFloat = 1

    var body: some View {
        ZStack {
            if tile {
                RoundedRectangle(cornerRadius: size * 0.23, style: .continuous)
                    .fill(Theme.ink)
            }
            RisingM()
                .trim(from: 0, to: progress)
                .stroke(
                    tile ? AnyShapeStyle(Color(light: 0xFFFFFF, dark: 0x1D1D1F)) : AnyShapeStyle(Theme.ink),
                    style: StrokeStyle(lineWidth: size * 0.11, lineCap: .butt, lineJoin: .miter, miterLimit: 10)
                )
        }
        .frame(width: size, height: size)
        .accessibilityElement()
        .accessibilityLabel("Manifest")
    }
}

#Preview {
    HStack(spacing: 24) {
        ManifestMark(size: 96)
        ManifestMark(size: 96, tile: false)
    }
    .padding()
}
