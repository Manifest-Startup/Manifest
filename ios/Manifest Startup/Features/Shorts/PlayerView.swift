import AVFoundation
import SwiftUI

/// A bare AVPlayerLayer: no chrome, aspect-fill, cheap to compose.
struct PlayerLayerView: View {
    let player: AVPlayer

    var body: some View {
        PlatformPlayerView(player: player)
            .accessibilityHidden(true)
    }
}

#if os(macOS)
private struct PlatformPlayerView: NSViewRepresentable {
    let player: AVPlayer
    func makeNSView(context: Context) -> PlayerNSView { PlayerNSView(player: player) }
    func updateNSView(_ view: PlayerNSView, context: Context) { view.playerLayer.player = player }
}

final class PlayerNSView: NSView {
    let playerLayer = AVPlayerLayer()
    init(player: AVPlayer) {
        super.init(frame: .zero)
        wantsLayer = true
        playerLayer.player = player
        playerLayer.videoGravity = .resizeAspectFill
        layer = playerLayer
    }
    required init?(coder: NSCoder) { fatalError() }
}
#else
private struct PlatformPlayerView: UIViewRepresentable {
    let player: AVPlayer
    func makeUIView(context: Context) -> PlayerUIView {
        let view = PlayerUIView()
        view.playerLayer.player = player
        view.playerLayer.videoGravity = .resizeAspectFill
        return view
    }
    func updateUIView(_ view: PlayerUIView, context: Context) {
        if view.playerLayer.player !== player { view.playerLayer.player = player }
    }
}

final class PlayerUIView: UIView {
    override static var layerClass: AnyClass { AVPlayerLayer.self }
    var playerLayer: AVPlayerLayer { layer as! AVPlayerLayer }
}
#endif

/// Keeps at most three players alive (previous, current, next) so swiping is
/// instant without holding a decoder per reel. Loops the current reel.
@Observable
final class PlayerPool {
    private var players: [String: AVQueuePlayer] = [:]
    private var loopers: [String: AVPlayerLooper] = [:]
    private(set) var activeID: String?
    var isMuted = false {
        didSet { players.values.forEach { $0.isMuted = isMuted } }
    }

    func player(for reel: PitchReel) -> AVQueuePlayer? {
        if let existing = players[reel.id] { return existing }
        guard let url = reel.videoURL else { return nil }
        let item = AVPlayerItem(url: url)
        item.preferredForwardBufferDuration = 4
        let player = AVQueuePlayer()
        player.isMuted = isMuted
        #if !os(visionOS)
        player.preventsDisplaySleepDuringVideoPlayback = true
        #endif
        loopers[reel.id] = AVPlayerLooper(player: player, templateItem: item)
        players[reel.id] = player
        return player
    }

    /// Plays `id`, pauses the rest, and drops players far from it.
    func activate(_ id: String?, in reels: [PitchReel]) {
        activeID = id
        guard let id, let index = reels.firstIndex(where: { $0.id == id }) else {
            pauseAll()
            return
        }
        let keep = Set(reels[max(0, index - 1)...min(reels.count - 1, index + 1)].map(\.id))
        for key in players.keys where !keep.contains(key) {
            players[key]?.pause()
            players[key] = nil
            loopers[key] = nil
        }
        for neighbour in keep where neighbour != id {
            if let reel = reels.first(where: { $0.id == neighbour }) {
                // Pre-roll the neighbours so the first frame is ready.
                _ = player(for: reel)
                players[neighbour]?.pause()
            }
        }
        if let reel = reels.first(where: { $0.id == id }), let player = player(for: reel) {
            player.play()
        }
    }

    func pauseAll() { players.values.forEach { $0.pause() } }

    func togglePlayback() {
        guard let activeID, let player = players[activeID] else { return }
        if player.timeControlStatus == .playing { player.pause() } else { player.play() }
    }

    func isPlaying(_ id: String) -> Bool { players[id]?.timeControlStatus == .playing }
}
