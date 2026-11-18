import SwiftUI

// MARK: Team

struct TeamView: View {
    let ideaID: String
    let isOwner: Bool

    @State private var people: [Collaborator] = []
    @State private var state: LoadState = .idle
    @State private var email = ""
    @State private var role = "editor"
    @State private var inviting = false
    @State private var toast: Toast?
    @State private var error: String?

    private let roles = ["viewer", "commenter", "editor"]

    var body: some View {
        List {
            if isOwner {
                Section {
                    TextField("name@company.com", text: $email)
                        .textContentType(.emailAddress)
                        #if os(iOS)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        #endif
                        .autocorrectionDisabled()
                    Picker("Role", selection: $role) {
                        ForEach(roles, id: \.self) { Text($0.capitalized) }
                    }
                    Button {
                        invite()
                    } label: {
                        HStack {
                            Text("Send invitation").fontWeight(.semibold)
                            if inviting { Spacer(); ProgressView() }
                        }
                    }
                    .disabled(!email.contains("@") || inviting)
                } header: {
                    Text("Invite")
                } footer: {
                    Text("Viewers read. Commenters can leave notes. Editors change the idea and its documents.")
                }
            }

            Section("People") {
                if state == .loading && people.isEmpty {
                    ProgressView().frame(maxWidth: .infinity)
                } else if people.isEmpty {
                    Text("Just you so far.").foregroundStyle(Theme.secondaryText)
                }
                ForEach(people) { person in
                    HStack(spacing: 12) {
                        Avatar(name: person.name, url: person.userAvatar, size: 36)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(person.name).font(.subheadline.weight(.semibold))
                            Text(person.status == "pending" ? "Invited · \(person.role)" : person.role.capitalized)
                                .font(.caption).foregroundStyle(Theme.secondaryText)
                        }
                        Spacer()
                        if isOwner && person.role != "owner" {
                            Menu {
                                ForEach(roles, id: \.self) { r in
                                    Button(r.capitalized) { change(person, to: r) }
                                }
                                Divider()
                                Button("Remove", role: .destructive) { remove(person) }
                            } label: {
                                Image(systemName: "ellipsis.circle").foregroundStyle(Theme.secondaryText)
                            }
                            .accessibilityLabel("Manage \(person.name)")
                        }
                    }
                }
            }
            if let error { Section { Text(error).foregroundStyle(Theme.danger) } }
        }
        .navigationTitle("Team")
        .toast($toast)
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        state = .loading
        do {
            people = try await API.collaborators(ideaId: ideaID)
            state = .loaded
        } catch {
            state = .failed(error.localizedDescription)
            self.error = error.localizedDescription
        }
    }

    private func invite() {
        inviting = true
        Task {
            do {
                let result = try await API.invite(ideaId: ideaID, email: email.trimmed, role: role)
                if result.success {
                    toast = Toast(message: "Invitation sent", symbol: "paperplane.fill")
                    email = ""
                    await load()
                } else {
                    error = result.message
                }
            } catch {
                self.error = error.localizedDescription
            }
            inviting = false
        }
    }

    private func change(_ person: Collaborator, to role: String) {
        Task {
            error = await attempt { try await API.updateCollaboratorRole(ideaId: ideaID, userId: person.userId, role: role) }
            await load()
        }
    }

    private func remove(_ person: Collaborator) {
        Task {
            error = await attempt { try await API.removeCollaborator(ideaId: ideaID, userId: person.userId) }
            await load()
        }
    }
}

// MARK: Versions

struct VersionsView: View {
    let ideaID: String
    let canRestore: Bool
    let onRestore: () async -> Void

    @State private var versions: [IdeaVersion] = []
    @State private var loading = true
    @State private var error: String?
    @State private var toast: Toast?
    @State private var restoring: IdeaVersion?

    var body: some View {
        List {
            if canRestore {
                Section {
                    Button {
                        Task {
                            error = await attempt { try await API.createVersion(ideaId: ideaID, summary: "Snapshot") }
                            if error == nil { toast = Toast(message: "Snapshot saved") }
                            await load()
                        }
                    } label: {
                        Label("Save a snapshot now", systemImage: "camera.aperture")
                    }
                }
            }
            Section {
                if loading && versions.isEmpty { ProgressView().frame(maxWidth: .infinity) }
                if !loading && versions.isEmpty {
                    Text("No snapshots yet. Edits you make here save one automatically.")
                        .foregroundStyle(Theme.secondaryText)
                }
                ForEach(versions) { version in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Version \(version.versionNumber)").font(.subheadline.weight(.semibold))
                            Spacer()
                            Text(Format.relative(version.createdAt)).font(.caption).foregroundStyle(Theme.tertiaryText)
                        }
                        if let summary = version.changeSummary?.nilIfEmpty {
                            Text(summary).font(.caption).foregroundStyle(Theme.secondaryText)
                        }
                        if let title = version.title { Text(title).font(.caption).lineLimit(1) }
                    }
                    .swipeActions {
                        if canRestore {
                            Button("Restore") { restoring = version }.tint(Theme.accent)
                        }
                    }
                    .contextMenu {
                        if canRestore { Button("Restore this version") { restoring = version } }
                    }
                }
            } footer: {
                if canRestore && !versions.isEmpty { Text("Swipe a version to restore it.") }
            }
            if let error { Section { Text(error).foregroundStyle(Theme.danger) } }
        }
        .navigationTitle("History")
        .toast($toast)
        .task { await load() }
        .confirmationDialog(
            "Restore version \(restoring?.versionNumber ?? 0)?",
            isPresented: Binding(get: { restoring != nil }, set: { if !$0 { restoring = nil } }),
            titleVisibility: .visible
        ) {
            Button("Restore") {
                guard let version = restoring else { return }
                Task {
                    error = await attempt { try await API.restoreVersion(ideaId: ideaID, versionId: version.versionId) }
                    if error == nil {
                        toast = Toast(message: "Restored")
                        await onRestore()
                        await load()
                    }
                }
            }
        } message: {
            Text("The title and description go back to this version. The current state is kept as a new version.")
        }
    }

    private func load() async {
        loading = true
        do {
            versions = try await API.versions(ideaId: ideaID).sorted { $0.versionNumber > $1.versionNumber }
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }
}

// MARK: Cap table

struct CapTableView: View {
    let ideaID: String
    let ideaTitle: String
    let isOwner: Bool

    @State private var entries: [CapTableEntry] = []
    @State private var investments: [Investment] = []
    @State private var loading = true
    @State private var error: String?
    @State private var showInvest = false
    @State private var toast: Toast?

    private let palette: [Color] = [
        Color(hex: 0x0A84FF), Color(hex: 0x5E5CE6), Color(hex: 0x30B0C7), Color(hex: 0x34C759),
        Color(hex: 0xFF9F0A), Color(hex: 0xFF375F), Color(hex: 0xBF5AF2),
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if let error { ErrorBanner(message: error) }

                VStack(alignment: .leading, spacing: 14) {
                    Text("Ownership").eyebrowStyle()
                    if entries.isEmpty {
                        Text(loading ? "Loading…" : "No equity recorded yet. Investments and sweat equity appear here.")
                            .font(.subheadline).foregroundStyle(Theme.secondaryText)
                    } else {
                        OwnershipBar(entries: entries, palette: palette)
                        ForEach(Array(entries.enumerated()), id: \.element.id) { index, entry in
                            HStack {
                                Circle().fill(palette[index % palette.count]).frame(width: 10, height: 10)
                                Text(entry.stakeholderName ?? entry.stakeholderType.capitalized).font(.subheadline)
                                Spacer()
                                Text(Format.percent(entry.equityPercentage)).font(.subheadline.monospacedDigit().weight(.semibold))
                            }
                            .accessibilityElement(children: .combine)
                        }
                    }
                }
                .card()

                VStack(alignment: .leading, spacing: 10) {
                    Text("Contributions").eyebrowStyle()
                    if investments.isEmpty && !loading {
                        Text("Nothing yet.").font(.subheadline).foregroundStyle(Theme.secondaryText).card()
                    }
                    ForEach(investments) { investment in
                        InvestmentRow(investment: investment, canManage: isOwner) { status in
                            Task {
                                error = await attempt {
                                    try await API.updateInvestmentStatus(id: investment.investmentId, status: status)
                                }
                                await load()
                            }
                        }
                    }
                }
            }
            .padding(Theme.gutter)
            .frame(maxWidth: 760)
            .frame(maxWidth: .infinity)
        }
        .screenBackground()
        .navigationTitle("Cap table")
        .toast($toast)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { showInvest = true } label: { Label("Add", systemImage: "plus") }
            }
        }
        .sheet(isPresented: $showInvest) {
            InvestSheet(ideaID: ideaID, ideaTitle: ideaTitle) {
                toast = Toast(message: "Recorded")
                Task { await load() }
            }
        }
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        loading = true
        async let cap = API.capTable(ideaId: ideaID)
        async let inv = API.investments(ideaId: ideaID)
        do {
            entries = try await cap.sorted { $0.equityPercentage > $1.equityPercentage }
            investments = try await inv.sorted { $0.createdAt > $1.createdAt }
        } catch {
            if (error as? APIError) != .cancelled { self.error = error.localizedDescription }
        }
        loading = false
    }
}

private struct OwnershipBar: View {
    let entries: [CapTableEntry]
    let palette: [Color]
    var body: some View {
        GeometryReader { proxy in
            let total = max(entries.reduce(0) { $0 + $1.equityPercentage }, 100)
            HStack(spacing: 2) {
                ForEach(Array(entries.enumerated()), id: \.element.id) { index, entry in
                    palette[index % palette.count]
                        .frame(width: max(2, proxy.size.width * entry.equityPercentage / total))
                }
                Theme.hairline
            }
            .clipShape(.capsule)
        }
        .frame(height: 14)
        .accessibilityHidden(true)
    }
}

private struct InvestmentRow: View {
    let investment: Investment
    let canManage: Bool
    let setStatus: (String) -> Void

    var body: some View {
        HStack(spacing: 12) {
            Avatar(name: investment.investorName ?? "Investor", url: investment.investorAvatar, size: 38)
            VStack(alignment: .leading, spacing: 3) {
                Text(investment.investorName ?? "Investor").font(.subheadline.weight(.semibold))
                Text(detail).font(.caption).foregroundStyle(Theme.secondaryText)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 4) {
                Text(Format.percent(investment.equityPercentage)).font(.subheadline.monospacedDigit().weight(.semibold))
                StatusPill(text: investment.status.capitalized, color: statusColor)
            }
        }
        .card(padding: 14)
        .contextMenu {
            if canManage {
                ForEach(["pending", "confirmed", "cancelled"], id: \.self) { status in
                    Button(status.capitalized) { setStatus(status) }
                }
            }
        }
    }

    private var detail: String {
        var parts: [String] = []
        if investment.cashAmount > 0 { parts.append(Format.currency(investment.cashAmount) + " cash") }
        if investment.sweatEquityHours > 0 {
            parts.append("\(investment.sweatEquityHours.formatted()) h · \(Format.currency(investment.sweatEquityValue))")
        }
        if let role = investment.role?.nilIfEmpty { parts.append(role) }
        return parts.isEmpty ? investment.investmentType.capitalized : parts.joined(separator: " · ")
    }

    private var statusColor: Color {
        switch investment.status {
        case "confirmed", "active", "completed": Theme.success
        case "cancelled": Theme.danger
        default: Theme.warning
        }
    }
}

// MARK: Invest

struct InvestSheet: View {
    let ideaID: String
    let ideaTitle: String
    let onDone: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var type = "cash"
    @State private var cash = 0.0
    @State private var hours = 0.0
    @State private var rate = 50.0
    @State private var equity = 0.0
    @State private var role = ""
    @State private var notes = ""
    @State private var saving = false
    @State private var error: String?

    private var sweatValue: Double { hours * rate }
    private var valid: Bool { (type == "cash" ? cash > 0 : hours > 0) && equity >= 0 && equity <= 100 }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker("Kind", selection: $type) {
                        Text("Cash").tag("cash")
                        Text("Sweat equity").tag("sweat_equity")
                    }
                    .pickerStyle(.segmented)
                }
                if type == "cash" {
                    Section("Amount") {
                        TextField("Amount", value: $cash, format: .currency(code: "USD"))
                            #if os(iOS)
                            .keyboardType(.decimalPad)
                            #endif
                    }
                } else {
                    Section {
                        LabeledContent("Hours") {
                            TextField("Hours", value: $hours, format: .number).multilineTextAlignment(.trailing)
                        }
                        LabeledContent("Hourly rate") {
                            TextField("Rate", value: $rate, format: .currency(code: "USD")).multilineTextAlignment(.trailing)
                        }
                        LabeledContent("Value", value: Format.currency(sweatValue))
                        TextField("Role (e.g. CTO)", text: $role)
                    } header: {
                        Text("Time")
                    }
                }
                Section {
                    LabeledContent("Equity") {
                        TextField("%", value: $equity, format: .number.precision(.fractionLength(0...2)))
                            .multilineTextAlignment(.trailing)
                    }
                    TextField("Notes", text: $notes, axis: .vertical)
                } footer: {
                    Text("Recorded on \(ideaTitle)'s cap table. This is a record, not a legal agreement or a payment.")
                }
                if let error { Section { Text(error).foregroundStyle(Theme.danger) } }
            }
            .navigationTitle("Contribute")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel", role: .cancel) { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Record") { save() }.fontWeight(.semibold).disabled(!valid || saving)
                }
            }
        }
    }

    private func save() {
        saving = true
        Task {
            do {
                try await API.createInvestment(
                    ideaId: ideaID, cash: type == "cash" ? cash : 0, hours: type == "cash" ? 0 : hours,
                    hourlyRate: rate, equity: equity, type: type, role: role.nilIfEmpty, notes: notes.nilIfEmpty)
                Haptics.success()
                onDone()
                dismiss()
            } catch {
                self.error = error.localizedDescription
                saving = false
            }
        }
    }
}
