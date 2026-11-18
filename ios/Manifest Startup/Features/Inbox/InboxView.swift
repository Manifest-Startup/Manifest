import SwiftUI

/// One inbox for founder messages (delivered through Open Media).
struct InboxView: View {
    @Environment(InboxStore.self) private var store
    @State private var selection: InboxConversation?
    @State private var link: OpenMediaLink?

    var body: some View {
        NavigationSplitView {
            List(selection: $selection) {
                if let link, link.enabled, !link.linked || link.needsReconnect {
                    ConnectOpenMediaRow(link: link)
                        .listRowSeparator(.hidden)
                }
                if let error = store.state.error, store.conversations.isEmpty {
                    ErrorBanner(message: error) { Task { await store.refresh() } }
                        .listRowSeparator(.hidden)
                }
                ForEach(store.conversations) { conversation in
                    NavigationLink(value: conversation) {
                        ConversationRow(conversation: conversation)
                    }
                    .swipeActions(edge: .leading) {
                        if conversation.unreadCount > 0 {
                            Button {
                                store.markRead(conversation.id)
                            } label: {
                                Label("Read", systemImage: "envelope.open")
                            }
                            .tint(Theme.accent)
                        }
                    }
                }
            }
            .listStyle(.plain)
            .overlay {
                if store.conversations.isEmpty {
                    switch store.state {
                    case .loading, .idle: ProgressView()
                    case .loaded:
                        EmptyStateView(
                            symbol: "bubble.left.and.text.bubble.right",
                            title: "No messages yet",
                            message: "Message a founder from their idea or pitch short. Replies land here."
                        )
                    case .failed: EmptyView()
                    }
                }
            }
            .refreshable { await store.refresh() }
            .navigationTitle("Inbox")
            .accountToolbar()
        } detail: {
            if let selection {
                ThreadView(conversation: selection)
                    .id(selection.id)
            } else {
                ContentUnavailableView("Select a conversation", systemImage: "bubble.left.and.bubble.right")
            }
        }
        .task {
            await store.load()
            #if DEBUG
            if DemoScreen.is(.thread) { selection = store.conversations.first }
            #endif
            link = try? await API.openMediaLink()
        }
    }
}

private struct ConversationRow: View {
    let conversation: InboxConversation

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            ZStack(alignment: .topTrailing) {
                Avatar(name: conversation.title, url: conversation.avatarUrl, size: 48,
                       tint: Color(hexString: conversation.avatarColor))
                if conversation.unreadCount > 0 {
                    Circle().fill(Theme.accent).frame(width: 12, height: 12)
                        .overlay(Circle().stroke(Theme.surface, lineWidth: 2))
                }
            }
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline) {
                    Text(conversation.title)
                        .font(.body.weight(conversation.unreadCount > 0 ? .semibold : .regular))
                        .lineLimit(1)
                    Spacer()
                    Text(Format.relative(conversation.lastMessageAt))
                        .font(.caption)
                        .foregroundStyle(conversation.unreadCount > 0 ? Theme.accent : Theme.tertiaryText)
                }
                if let ideaTitle = conversation.ideaTitle {
                    Label(ideaTitle, systemImage: "lightbulb")
                        .font(.caption.weight(.medium))
                        .foregroundStyle(Theme.accent)
                        .lineLimit(1)
                }
                Text(conversation.preview ?? " ")
                    .font(.subheadline)
                    .foregroundStyle(Theme.secondaryText)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
        .accessibilityValue(conversation.unreadCount > 0 ? "\(conversation.unreadCount) unread" : "")
    }
}

private struct ConnectOpenMediaRow: View {
    let link: OpenMediaLink
    @Environment(\.openURL) private var openURL

    var body: some View {
        HStack(spacing: 12) {
            Image("OpenMediaMark").resizable().frame(width: 32, height: 32).clipShape(.rect(cornerRadius: 8))
            VStack(alignment: .leading, spacing: 2) {
                Text(link.needsReconnect ? "Reconnect Open Media" : "Connect Open Media").font(.subheadline.weight(.semibold))
                Text("Messages to and from founders travel through Open Media.")
                    .font(.caption).foregroundStyle(Theme.secondaryText)
            }
            Spacer()
            Button("Connect") {
                if let url = URL(string: link.connectUrl, relativeTo: AppConfig.baseURL) { openURL(url) }
            }
            .glassButtonStyle(prominent: true)
            .controlSize(.small)
        }
        .card(padding: 12)
    }
}

// MARK: Thread

struct ThreadView: View {
    let conversation: InboxConversation

    @Environment(InboxStore.self) private var store
    @State private var items: [InboxItem] = []
    @State private var loading = true
    @State private var text = ""
    @State private var sending = false
    @State private var error: String?
    @FocusState private var focused: Bool

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 2) {
                    if loading && items.isEmpty {
                        ProgressView().padding(.top, 40)
                    }
                    ForEach(items) { item in
                        ThreadItemView(item: item, isGroup: conversation.group)
                            .id(item.id)
                    }
                    Color.clear.frame(height: 1).id("end")
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
            }
            .defaultScrollAnchor(.bottom)
            .keyboardDismissOnScroll()
            .onChange(of: items.count) {
                withAnimation(Theme.spring) { proxy.scrollTo("end", anchor: .bottom) }
            }
        }
        .screenBackground()
        .safeAreaInset(edge: .bottom) { composer }
        .navigationTitle(conversation.title)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task(id: conversation.id) {
            await load()
            store.markRead(conversation.id)
            // Gentle live updates while the thread is open.
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(12))
                guard !Task.isCancelled else { return }
                await load()
            }
        }
    }

    @ViewBuilder
    private var composer: some View {
        if conversation.canReply {
            VStack(spacing: 6) {
                if let error { Text(error).font(.caption).foregroundStyle(Theme.danger) }
                HStack(alignment: .bottom, spacing: 10) {
                    TextField("Message", text: $text, axis: .vertical)
                        .lineLimit(1...6)
                        .focused($focused)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                        .glassSurface(.rect(cornerRadius: 20))
                    Button(action: send) {
                        Image(systemName: "arrow.up").font(.body.weight(.bold)).frame(width: 22, height: 22)
                    }
                    .glassButtonStyle(prominent: true)
                    .buttonBorderShape(.circle)
                    .disabled(text.trimmed.isEmpty || sending)
                    .accessibilityLabel("Send")
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
        } else {
            Text("Replies to this conversation aren't available here.")
                .font(.caption)
                .foregroundStyle(Theme.secondaryText)
                .padding()
        }
    }

    private func load() async {
        do {
            let thread = try await API.thread(conversation.id)
            if thread.items != items {
                withAnimation(items.isEmpty ? nil : Theme.spring) { items = thread.items }
            }
            error = nil
        } catch {
            if (error as? APIError) != .cancelled && items.isEmpty { self.error = error.localizedDescription }
        }
        loading = false
    }

    private func send() {
        let body = text.trimmed
        guard !body.isEmpty, !sending else { return }
        sending = true
        error = nil
        let clientID = UUID().uuidString
        // Optimistic bubble; replaced by the server copy on reload.
        let pending = InboxItem(
            kind: "message", key: "pending-\(clientID)", at: .now, messageId: nil, isMine: true,
            senderName: nil, sentAt: .now, subject: nil, body: [.init(text: body, url: nil)],
            attachmentCount: 0, quotedHistoryHidden: false, groupStart: true, groupEnd: true
        )
        withAnimation(Theme.spring) { items.append(pending) }
        text = ""
        Task {
            do {
                try await API.reply(conversationId: conversation.id, text: body, clientId: clientID)
                store.didSend(body, in: conversation.id)
                Haptics.tap()
                await load()
            } catch {
                items.removeAll { $0.key == pending.key }
                text = body
                self.error = error.localizedDescription
            }
            sending = false
        }
    }
}

private struct ThreadItemView: View {
    let item: InboxItem
    let isGroup: Bool

    var body: some View {
        if item.isMessage {
            VStack(alignment: item.isMine ? .trailing : .leading, spacing: 3) {
                if item.groupStart && isGroup && !item.isMine, let sender = item.senderName {
                    Text(sender).font(.caption.weight(.semibold)).foregroundStyle(Theme.secondaryText).padding(.horizontal, 12)
                }
                HStack {
                    if item.isMine { Spacer(minLength: 56) }
                    VStack(alignment: .leading, spacing: 4) {
                        if let subject = item.subject?.nilIfEmpty {
                            Text(subject).font(.subheadline.weight(.semibold))
                        }
                        Text(attributed)
                            .font(.body)
                            .textSelection(.enabled)
                        if item.attachmentCount > 0 {
                            Label("\(item.attachmentCount) attachment\(item.attachmentCount == 1 ? "" : "s")", systemImage: "paperclip")
                                .font(.caption)
                                .opacity(0.8)
                        }
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 9)
                    .foregroundStyle(item.isMine ? .white : Theme.ink)
                    .background(
                        item.isMine ? AnyShapeStyle(Theme.accent.gradient) : AnyShapeStyle(Theme.surface),
                        in: .rect(cornerRadius: 19, style: .continuous)
                    )
                    .opacity(item.key.hasPrefix("pending-") ? 0.7 : 1)
                    if !item.isMine { Spacer(minLength: 56) }
                }
                if item.groupEnd, let date = item.sentAt ?? item.at {
                    Text(date.formatted(date: .omitted, time: .shortened))
                        .font(.caption2)
                        .foregroundStyle(Theme.tertiaryText)
                        .padding(.horizontal, 12)
                        .padding(.bottom, 6)
                }
            }
        } else {
            // Day dividers and system notes.
            Text(item.text.nilIfEmpty ?? (item.at?.formatted(date: .abbreviated, time: .omitted) ?? ""))
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.tertiaryText)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 10)
        }
    }

    private var attributed: AttributedString {
        var result = AttributedString()
        for segment in item.body {
            var part = AttributedString(segment.text)
            if let raw = segment.url, let url = URL(string: raw) {
                part.link = url
                part.underlineStyle = .single
            }
            result += part
        }
        return result
    }
}
