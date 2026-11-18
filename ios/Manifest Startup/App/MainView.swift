import SwiftUI

enum AppTab: Hashable {
    case ideas, shorts, inbox, portfolio, search
}

/// The signed-in app. A tab bar on iPhone, a sidebar on iPad and Mac, one codebase.
struct MainView: View {
    @Environment(SessionModel.self) private var session
    @Environment(\.scenePhase) private var scenePhase

    @State private var tab: AppTab = .ideas
    @State private var ideas = IdeasStore()
    @State private var shorts = ShortsStore()
    @State private var inbox = InboxStore()
    @State private var portfolio = PortfolioStore()
    @State private var showAccount = false

    init() {
        #if DEBUG
        switch DemoScreen.current {
        case .shorts: _tab = State(initialValue: .shorts)
        case .inbox, .thread: _tab = State(initialValue: .inbox)
        case .portfolio: _tab = State(initialValue: .portfolio)
        case .search: _tab = State(initialValue: .search)
        case .account: _showAccount = State(initialValue: true)
        default: break
        }
        #endif
    }

    var body: some View {
        TabView(selection: $tab) {
            Tab("Ideas", systemImage: "lightbulb", value: AppTab.ideas) {
                IdeasView()
            }
            Tab("Shorts", systemImage: "play.rectangle.on.rectangle", value: AppTab.shorts) {
                ShortsView(isActive: tab == .shorts && scenePhase == .active)
            }
            Tab("Inbox", systemImage: "bubble.left.and.text.bubble.right", value: AppTab.inbox) {
                InboxView()
            }
            .badge(inbox.unread)
            Tab("Portfolio", systemImage: "chart.pie", value: AppTab.portfolio) {
                PortfolioView()
            }
            Tab(value: AppTab.search, role: .search) {
                SearchView()
            }
        }
        .tabViewStyle(.sidebarAdaptable)
        #if os(iOS)
        .tabBarMinimizeBehavior(.onScrollDown)
        #endif
        .environment(ideas)
        .environment(shorts)
        .environment(inbox)
        .environment(portfolio)
        .environment(\.openAccount, OpenAccountAction { showAccount = true })
        .sheet(isPresented: $showAccount) {
            AccountView()
                .environment(ideas)
        }
        .task {
            // Warm the first tab and the badge in parallel.
            async let a: Void = ideas.load()
            async let b: Void = inbox.refreshUnread()
            _ = await (a, b)
        }
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            await inbox.pollUnread()
        }
    }
}

// MARK: Account entry point, shared by every tab's toolbar

struct OpenAccountAction {
    let action: () -> Void
    func callAsFunction() { action() }
}

extension EnvironmentValues {
    @Entry var openAccount = OpenAccountAction {}
}

struct AccountToolbarButton: View {
    @Environment(SessionModel.self) private var session
    @Environment(\.openAccount) private var openAccount

    var body: some View {
        Button {
            openAccount()
        } label: {
            Avatar(name: session.user?.displayName ?? "M", url: session.user?.profilePictureUrl, size: 30)
        }
        .accessibilityLabel("Account")
        .accessibilityIdentifier("account")
    }
}

extension View {
    /// The avatar in the top trailing corner that opens Account.
    func accountToolbar() -> some View {
        toolbar {
            ToolbarItem(placement: .primaryAction) { AccountToolbarButton() }
        }
    }
}
