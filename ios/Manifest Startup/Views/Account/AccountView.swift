import SwiftUI

struct AccountView: View {
    @StateObject private var viewModel = AccountViewModel()
    @State private var selectedTab = 0
    @AppStorage("isDarkMode") private var isDarkMode = false
    @AppStorage("useSystemTheme") private var useSystemTheme = true
    
    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading {
                    ProgressView()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ScrollView {
                        VStack(spacing: 16) {
                            ProfileHeaderView(user: viewModel.user)
                            
                            Picker("Section", selection: $selectedTab) {
                                Text("Portfolio").tag(0)
                                Text("Settings").tag(1)
                            }
                            .pickerStyle(.segmented)
                            .padding(.horizontal)
                            
                            if selectedTab == 0 {
                                PortfolioSection(
                                    stats: viewModel.portfolioStats,
                                    investments: viewModel.investments
                                )
                            } else {
                                SettingsSection(
                                    viewModel: viewModel,
                                    isDarkMode: $isDarkMode,
                                    useSystemTheme: $useSystemTheme
                                )
                            }
                        }
                        .padding(.vertical)
                    }
                }
            }
            .navigationTitle("Account")
            .task {
                await viewModel.loadAccount()
            }
            .refreshable {
                await viewModel.loadAccount()
            }
        }
        .preferredColorScheme(useSystemTheme ? nil : (isDarkMode ? .dark : .light))
    }
}

struct ProfileHeaderView: View {
    let user: User?
    
    var body: some View {
        HStack(spacing: 16) {
            AsyncImage(url: user?.avatarURL) { image in
                image.resizable()
            } placeholder: {
                Circle()
                    .fill(Color(.systemGray4))
            }
            .frame(width: 80, height: 80)
            .clipShape(Circle())
            
            VStack(alignment: .leading, spacing: 4) {
                Text(user?.displayName ?? "User")
                    .font(.title2)
                    .fontWeight(.bold)
                
                Text("Account Settings")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            
            Spacer()
        }
        .padding()
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .shadow(color: .black.opacity(0.05), radius: 4)
        .padding(.horizontal)
    }
}

struct PortfolioSection: View {
    let stats: PortfolioStats
    let investments: [Investment]
    
    var body: some View {
        VStack(spacing: 16) {
            HStack(spacing: 12) {
                StatCard(title: "Investments", value: "\(stats.totalInvestments)", color: .blue)
                StatCard(title: "Total Value", value: "$\(Int(stats.totalValue).formatted())", color: .green)
                StatCard(title: "Equity", value: String(format: "%.1f%%", stats.totalEquity), color: .purple)
            }
            .padding(.horizontal)
            
            if investments.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "building.2")
                        .font(.system(size: 36))
                        .foregroundStyle(.tertiary)
                    
                    Text("No investments yet")
                        .font(.headline)
                    
                    Text("Discover ideas to invest in")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    
                    NavigationLink("Explore Ideas") {
                        DiscoverView()
                    }
                    .buttonStyle(.borderedProminent)
                }
                .padding(32)
                .frame(maxWidth: .infinity)
                .background(Color(.systemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 16))
                .padding(.horizontal)
            } else {
                VStack(spacing: 12) {
                    ForEach(investments) { investment in
                        InvestmentRow(investment: investment)
                    }
                }
                .padding(.horizontal)
            }
        }
    }
}

struct StatCard: View {
    let title: String
    let value: String
    let color: Color
    
    var body: some View {
        VStack(spacing: 4) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title2)
                .fontWeight(.bold)
                .foregroundStyle(color)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.05), radius: 2)
    }
}

struct InvestmentRow: View {
    let investment: Investment
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(investment.ideaTitle)
                    .font(.headline)
                
                Text("$\(Int(investment.totalValue).formatted())")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            
            Spacer()
            
            VStack(alignment: .trailing, spacing: 4) {
                Text(String(format: "%.2f%%", investment.equityPercentage))
                    .font(.headline)
                    .foregroundStyle(.purple)
                
                Text(investment.status.rawValue.capitalized)
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(investment.status == .confirmed ? Color.green.opacity(0.2) : Color.yellow.opacity(0.2))
                    .foregroundStyle(investment.status == .confirmed ? .green : .yellow)
                    .clipShape(Capsule())
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.05), radius: 2)
    }
}

struct SettingsSection: View {
    @ObservedObject var viewModel: AccountViewModel
    @Binding var isDarkMode: Bool
    @Binding var useSystemTheme: Bool
    
    var body: some View {
        VStack(spacing: 16) {
            SettingsCard(title: "Appearance") {
                VStack(spacing: 12) {
                    Toggle("Use System Theme", isOn: $useSystemTheme)
                    
                    if !useSystemTheme {
                        Toggle("Dark Mode", isOn: $isDarkMode)
                    }
                }
            }
            
            SettingsCard(title: "Profile") {
                VStack(spacing: 12) {
                    TextField("First Name", text: $viewModel.firstName)
                        .textFieldStyle(.roundedBorder)
                    
                    TextField("Last Name", text: $viewModel.lastName)
                        .textFieldStyle(.roundedBorder)
                    
                    TextField("Email", text: $viewModel.email)
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.emailAddress)
                        .textContentType(.emailAddress)
                    
                    Button {
                        Task { await viewModel.saveChanges() }
                    } label: {
                        if viewModel.isSaving {
                            ProgressView()
                                .frame(maxWidth: .infinity)
                        } else {
                            Text("Save Changes")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.isSaving)
                }
            }
            
            SettingsCard(title: "Data Management") {
                VStack(spacing: 12) {
                    Button {
                    } label: {
                        HStack {
                            Image(systemName: "square.and.arrow.down")
                            Text("Import Ideas")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    
                    Button {
                    } label: {
                        HStack {
                            Image(systemName: "square.and.arrow.up")
                            Text("Export Ideas")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                }
            }
            
            SettingsCard(title: "Integrations") {
                VStack(spacing: 12) {
                    IntegrationRow(name: "Google", icon: "g.circle.fill", connected: false)
                    IntegrationRow(name: "GitHub", icon: "chevron.left.forwardslash.chevron.right", connected: false)
                    IntegrationRow(name: "Slack", icon: "number", connected: false)
                }
            }
            
            SettingsCard(title: "API Access") {
                VStack(spacing: 12) {
                    Text("Manage your API keys for programmatic access")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    
                    Button("Manage API Keys") {
                    }
                    .buttonStyle(.bordered)
                }
            }
        }
        .padding(.horizontal)
    }
}

struct SettingsCard<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .font(.headline)
            
            content
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .shadow(color: .black.opacity(0.05), radius: 4)
    }
}

struct IntegrationRow: View {
    let name: String
    let icon: String
    let connected: Bool
    
    var body: some View {
        HStack {
            Image(systemName: icon)
                .frame(width: 24)
            
            Text(name)
            
            Spacer()
            
            if connected {
                Text("Connected")
                    .font(.caption)
                    .foregroundStyle(.green)
            } else {
                Button("Connect") {
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
    }
}

#Preview {
    AccountView()
}
