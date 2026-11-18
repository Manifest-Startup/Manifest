import ImageIO
import SwiftUI

/// Downsamples remote images off the main thread to the size they are drawn
/// at, and keeps decoded bitmaps in memory. Far cheaper than AsyncImage in
/// scrolling lists: no full-size decode, no refetch when a row reappears.
actor ImagePipeline {
    static let shared = ImagePipeline()

    private let cache = NSCache<NSString, CGImageBox>()
    private var inFlight: [String: Task<CGImage?, Never>] = [:]
    private let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.urlCache = URLCache(memoryCapacity: 16 << 20, diskCapacity: 256 << 20)
        config.requestCachePolicy = .returnCacheDataElseLoad
        return URLSession(configuration: config)
    }()

    init() { cache.totalCostLimit = 96 << 20 }

    func image(for url: URL, maxPixel: CGFloat) async -> CGImage? {
        let key = "\(url.absoluteString)#\(Int(maxPixel))"
        if let hit = cache.object(forKey: key as NSString) { return hit.image }
        if let task = inFlight[key] { return await task.value }
        let session = session
        let task = Task<CGImage?, Never>.detached(priority: .userInitiated) {
            guard let (data, _) = try? await session.data(from: url),
                let source = CGImageSourceCreateWithData(data as CFData, nil)
            else { return nil }
            let options: [CFString: Any] = [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceShouldCacheImmediately: true,
                kCGImageSourceThumbnailMaxPixelSize: max(maxPixel, 64),
            ]
            return CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary)
        }
        inFlight[key] = task
        let image = await task.value
        inFlight[key] = nil
        if let image {
            cache.setObject(CGImageBox(image), forKey: key as NSString, cost: image.bytesPerRow * image.height)
        }
        return image
    }
}

nonisolated final class CGImageBox: @unchecked Sendable {
    let image: CGImage
    init(_ image: CGImage) { self.image = image }
}

struct RemoteImage<Placeholder: View>: View {
    let url: URL?
    var contentMode: ContentMode = .fill
    @ViewBuilder var placeholder: () -> Placeholder

    @State private var image: CGImage?
    @Environment(\.displayScale) private var scale

    var body: some View {
        GeometryReader { proxy in
            ZStack {
                if let image {
                    Image(decorative: image, scale: 1)
                        .resizable()
                        .aspectRatio(contentMode: contentMode)
                        .frame(width: proxy.size.width, height: proxy.size.height)
                        .clipped()
                        .transition(.opacity)
                } else {
                    placeholder()
                        .frame(width: proxy.size.width, height: proxy.size.height)
                }
            }
            .task(id: url) {
                guard let url else { return }
                let side = max(proxy.size.width, proxy.size.height) * scale
                let loaded = await ImagePipeline.shared.image(for: url, maxPixel: side)
                withAnimation(.easeOut(duration: 0.2)) { image = loaded }
            }
        }
    }
}

/// A person: photo when there is one, otherwise initials on a soft tint.
struct Avatar: View {
    let name: String
    var url: String?
    var size: CGFloat = 40
    var tint: Color?

    var body: some View {
        RemoteImage(url: url.flatMap(URL.init(string:))) {
            ZStack {
                Circle().fill((tint ?? Theme.accent).gradient.opacity(0.9))
                Text(name.initials)
                    .font(.system(size: size * 0.38, weight: .semibold, design: .rounded))
                    .foregroundStyle(.white)
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .accessibilityHidden(true)
    }
}
