import SwiftUI

struct MainTabView: View {
    @State private var selectedTab = 0
    
    var body: some View {
        TabView(selection: $selectedTab) {
            IdeasView()
                .tabItem {
                    Label("Ideas", systemImage: "lightbulb.fill")
                }
                .tag(0)
            
            DiscoverView()
                .tabItem {
                    Label("Discover", systemImage: "globe")
                }
                .tag(1)
            
            ShortsView()
                .tabItem {
                    Label("Shorts", systemImage: "play.rectangle.fill")
                }
                .tag(2)
            
            AccountView()
                .tabItem {
                    Label("Account", systemImage: "person.fill")
                }
                .tag(3)
        }
        .tint(.blue)
    }
}

#Preview {
    MainTabView()
}
