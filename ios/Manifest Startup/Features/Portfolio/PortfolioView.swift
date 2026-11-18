import Charts
import SwiftUI

/// What you've put into other people's ideas: cash, time and the equity it bought.
struct PortfolioView: View {
    @Environment(PortfolioStore.self) private var store

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let error = store.state.error {
                        ErrorBanner(message: error) { Task { await store.refresh() } }
                    }

                    LazyVGrid(columns: [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)], spacing: 12) {
                        MetricTile(label: "Total value", value: Format.currency(store.totalValue), symbol: "sum")
                        MetricTile(label: "Positions", value: "\(store.items.count)", symbol: "square.stack.3d.up")
                        MetricTile(label: "Cash", value: Format.currency(store.cash), symbol: "dollarsign.circle", tint: Theme.success)
                        MetricTile(label: "Sweat equity", value: Format.currency(store.sweat), symbol: "hammer", tint: Color(hex: 0xFF9F0A))
                    }

                    if store.items.count > 1 {
                        allocation
                    }

                    if store.items.isEmpty {
                        if store.state == .loading {
                            ForEach(0..<3, id: \.self) { _ in SkeletonCard() }
                        } else if store.state == .loaded {
                            EmptyStateView(
                                symbol: "chart.pie",
                                title: "No positions yet",
                                message: "When you put cash or time into an idea, it's tracked here with the equity it earned."
                            )
                            .padding(.top, 20)
                        }
                    } else {
                        Text("Positions").eyebrowStyle().padding(.top, 6)
                        ForEach(store.items) { item in
                            NavigationLink(value: IdeaRoute(id: item.ideaId)) {
                                PositionRow(item: item)
                            }
                            .pressable()
                        }
                    }
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 100)
                .frame(maxWidth: 760)
                .frame(maxWidth: .infinity)
            }
            .screenBackground()
            .refreshable { await store.refresh() }
            .navigationTitle("Portfolio")
            .accountToolbar()
            .navigationDestination(for: IdeaRoute.self) { IdeaDetailView(ideaID: $0.id) }
            .task { await store.load() }
        }
    }

    private var allocation: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Allocation").eyebrowStyle()
            Chart(store.items) { item in
                SectorMark(
                    angle: .value("Value", item.totalValue),
                    innerRadius: .ratio(0.62),
                    angularInset: 1.5
                )
                .cornerRadius(4)
                .foregroundStyle(by: .value("Idea", item.ideaTitle))
            }
            .chartLegend(position: .trailing, alignment: .center)
            .frame(height: 170)
        }
        .card()
    }
}

private struct PositionRow: View {
    let item: PortfolioItem

    var body: some View {
        HStack(spacing: 14) {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Theme.gradient(for: item.ideaId))
                .frame(width: 44, height: 44)
                .overlay {
                    Text(String(item.ideaTitle.prefix(1)).uppercased())
                        .font(.system(.title3, design: .rounded, weight: .bold))
                        .foregroundStyle(.white)
                }
            VStack(alignment: .leading, spacing: 3) {
                Text(item.ideaTitle).font(.headline).foregroundStyle(Theme.ink).lineLimit(1)
                HStack(spacing: 6) {
                    StatusPill(text: item.status.capitalized, color: item.status == "cancelled" ? Theme.danger : item.status == "pending" ? Theme.warning : Theme.success)
                    Text(item.createdAt.formatted(.dateTime.month(.abbreviated).year()))
                        .font(.caption).foregroundStyle(Theme.tertiaryText)
                }
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text(Format.currency(item.totalValue)).font(.subheadline.weight(.semibold).monospacedDigit()).foregroundStyle(Theme.ink)
                Text(Format.percent(item.equityPercentage) + " equity").font(.caption).foregroundStyle(Theme.secondaryText)
            }
        }
        .card(padding: 14)
        .accessibilityElement(children: .combine)
    }
}
