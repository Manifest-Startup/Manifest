import SwiftUI

/// A short interview: the questions an investor would ask, one at a time,
/// ending with a score and the reasons behind it.
struct QualificationView: View {
    let ideaText: String

    @Environment(\.dismiss) private var dismiss
    @State private var session: QualificationSession?
    @State private var answer = ""
    @State private var sending = false
    @State private var error: String?
    @FocusState private var focused: Bool

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        intro
                        if let session {
                            ForEach(Array(session.transcript.enumerated()), id: \.offset) { _, message in
                                Bubble(text: message.content, mine: message.role == "user")
                            }
                            if sending { TypingBubble() }
                            if session.isComplete { ScoreCard(session: session) }
                        } else if error == nil {
                            TypingBubble()
                        }
                        if let error {
                            ErrorBanner(message: error) { Task { await start() } }
                        }
                        Color.clear.frame(height: 1).id("bottom")
                    }
                    .padding(Theme.gutter)
                    .frame(maxWidth: 720)
                    .frame(maxWidth: .infinity)
                }
                .keyboardDismissOnScroll()
                .onChange(of: session?.transcript.count) {
                    withAnimation(Theme.spring) { proxy.scrollTo("bottom", anchor: .bottom) }
                }
                .onChange(of: sending) {
                    withAnimation(Theme.spring) { proxy.scrollTo("bottom", anchor: .bottom) }
                }
            }
            .screenBackground()
            .safeAreaInset(edge: .bottom) {
                if let session, !session.isComplete {
                    composer
                }
            }
            .navigationTitle("Pressure test")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
            .task { await start() }
        }
    }

    private var intro: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("A few honest questions").font(.title3.weight(.semibold))
            Text("Answer in a sentence or two. There are no wrong answers, only clearer ones.")
                .font(.subheadline)
                .foregroundStyle(Theme.secondaryText)
        }
        .padding(.bottom, 8)
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("Your answer", text: $answer, axis: .vertical)
                .lineLimit(1...5)
                .focused($focused)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .glassSurface(.rect(cornerRadius: 20))
                .onSubmit(send)
            Button(action: send) {
                Image(systemName: "arrow.up")
                    .font(.body.weight(.bold))
                    .frame(width: 22, height: 22)
            }
            .glassButtonStyle(prominent: true)
            .buttonBorderShape(.circle)
            .disabled(answer.trimmed.isEmpty || sending)
            .accessibilityLabel("Send answer")
        }
        .padding(.horizontal, Theme.gutter)
        .padding(.vertical, 10)
    }

    private func start() async {
        guard session == nil else { return }
        error = nil
        do {
            session = try await API.startQualification(text: ideaText)
            focused = true
        } catch {
            if (error as? APIError) != .cancelled { self.error = error.localizedDescription }
        }
    }

    private func send() {
        guard let current = session, !answer.trimmed.isEmpty, !sending else { return }
        let text = answer.trimmed
        answer = ""
        sending = true
        session?.transcript.append(QualificationMessage(role: "user", content: text))
        Task {
            do {
                let next = try await API.continueQualification(sessionId: current.id, message: text)
                withAnimation(Theme.spring) { session = next }
                if next.isComplete { Haptics.success() }
            } catch {
                self.error = error.localizedDescription
                session?.transcript.removeLast()
                answer = text
            }
            sending = false
        }
    }
}

struct Bubble: View {
    let text: String
    let mine: Bool

    var body: some View {
        HStack {
            if mine { Spacer(minLength: 48) }
            Text(LocalizedStringKey(text))
                .font(.body)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .foregroundStyle(mine ? .white : Theme.ink)
                .background(
                    mine ? AnyShapeStyle(Theme.accent.gradient) : AnyShapeStyle(Theme.surface),
                    in: .rect(cornerRadius: 20, style: .continuous)
                )
                .textSelection(.enabled)
            if !mine { Spacer(minLength: 48) }
        }
        .transition(.move(edge: mine ? .trailing : .leading).combined(with: .opacity))
    }
}

struct TypingBubble: View {
    @State private var phase = 0.0
    var body: some View {
        HStack(spacing: 5) {
            ForEach(0..<3) { i in
                Circle()
                    .fill(Theme.tertiaryText)
                    .frame(width: 7, height: 7)
                    .opacity(0.35 + 0.65 * abs(sin(phase + Double(i) * 0.6)))
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(Theme.surface, in: .capsule)
        .onAppear {
            withAnimation(.linear(duration: 1.2).repeatForever(autoreverses: false)) { phase = .pi }
        }
        .accessibilityLabel("Thinking")
    }
}

private struct ScoreCard: View {
    let session: QualificationSession

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .center, spacing: 18) {
                ZStack {
                    Circle().stroke(Theme.hairline, lineWidth: 8)
                    Circle()
                        .trim(from: 0, to: CGFloat(session.qualificationScore ?? 0) / 100)
                        .stroke(Theme.accent.gradient, style: StrokeStyle(lineWidth: 8, lineCap: .round))
                        .rotationEffect(.degrees(-90))
                    Text("\(session.qualificationScore ?? 0)")
                        .font(.system(.title, design: .rounded, weight: .bold))
                }
                .frame(width: 84, height: 84)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Your idea scores").eyebrowStyle()
                    Text(verdict).font(.title3.weight(.semibold))
                }
            }
            if let explanation = session.qualificationExplanation?.nilIfEmpty {
                Text(explanation).font(.subheadline).foregroundStyle(.primary.opacity(0.85))
            }
            let factors: [(String, Int?)] = [
                ("Market need", session.ideaMarketNeed), ("Feasibility", session.ideaFeasibility),
                ("Defensibility", session.ideaDefensibility), ("Revenue", session.ideaRevenuePotential),
            ]
            ForEach(factors, id: \.0) { name, value in
                if let value {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(name).font(.caption.weight(.semibold))
                            Spacer()
                            Text("\(value)/10").font(.caption.monospacedDigit()).foregroundStyle(Theme.secondaryText)
                        }
                        ProgressView(value: Double(value), total: 10).tint(Theme.accent)
                    }
                }
            }
            if let risks = session.ideaRisks?.nilIfEmpty {
                Label {
                    Text(risks).font(.subheadline)
                } icon: {
                    Image(systemName: "exclamationmark.triangle").foregroundStyle(Theme.warning)
                }
            }
        }
        .card(padding: 20)
        .padding(.top, 8)
    }

    private var verdict: String {
        switch session.qualificationScore ?? 0 {
        case 80...: "Strong. Go build it."
        case 60..<80: "Promising, with work to do."
        case 40..<60: "Worth sharpening."
        default: "Early. Keep exploring."
        }
    }
}
