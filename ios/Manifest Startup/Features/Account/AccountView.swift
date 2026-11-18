import SwiftUI
import UniformTypeIdentifiers

/// Profile, AI key, connections, security, data and privacy in one sheet.
struct AccountView: View {
    @Environment(SessionModel.self) private var session
    @Environment(\.dismiss) private var dismiss
    @AppStorage(Appearance.storageKey) private var appearance: Appearance = .system

    @State private var aiKey: AIKeyStatus?
    @State private var stats: SocialStats?
    @State private var confirmSignOut = false

    var body: some View {
        NavigationStack {
            List {
                Section {
                    NavigationLink {
                        ProfileEditView()
                    } label: {
                        HStack(spacing: 14) {
                            Avatar(name: session.user?.displayName ?? "M", url: session.user?.profilePictureUrl, size: 58)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(session.user?.displayName ?? "").font(.title3.weight(.semibold))
                                Text(session.isGuest ? "Guest workspace" : session.user?.email ?? "")
                                    .font(.subheadline).foregroundStyle(Theme.secondaryText)
                                if let stats {
                                    Text("\(Format.count(stats.followerCount)) followers · \(Format.count(stats.followingCount)) following")
                                        .font(.caption).foregroundStyle(Theme.tertiaryText)
                                }
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }

                Section {
                    NavigationLink {
                        AIKeyView(status: $aiKey)
                    } label: {
                        LabeledContent {
                            Text(aiKey.map { $0.configured ? "•••• \($0.last4 ?? "")" : "Not set" } ?? "")
                                .foregroundStyle(aiKey?.configured == true ? Theme.secondaryText : Theme.warning)
                        } label: {
                            Label("OpenAI key", systemImage: "key")
                        }
                    }
                    NavigationLink { ConnectionsView() } label: { Label("Connections", systemImage: "link") }
                } header: {
                    Text("AI and connections")
                } footer: {
                    Text("Manifest generates documents with your own OpenAI key, so you only pay for what you use.")
                }

                Section("Appearance") {
                    Picker(selection: $appearance) {
                        ForEach(Appearance.allCases) { Text($0.title).tag($0) }
                    } label: {
                        Label("Theme", systemImage: "circle.lefthalf.filled")
                    }
                }

                Section("Security and data") {
                    NavigationLink { SessionsView() } label: { Label("Signed-in devices", systemImage: "iphone.and.arrow.forward") }
                    NavigationLink { DataView() } label: { Label("Import and export", systemImage: "arrow.up.arrow.down.square") }
                    NavigationLink { PrivacyView() } label: { Label("Privacy", systemImage: "hand.raised") }
                }

                Section("Help") {
                    NavigationLink { FeedbackView() } label: { Label("Send feedback", systemImage: "envelope") }
                    Link(destination: AppConfig.baseURL.appending(path: "docs/guide")) {
                        Label("User guide", systemImage: "book")
                    }
                    Link(destination: AppConfig.baseURL.appending(path: "legal/terms")) {
                        Label("Terms of Service", systemImage: "doc.text")
                    }
                    Link(destination: AppConfig.baseURL.appending(path: "legal/privacy")) {
                        Label("Privacy Policy", systemImage: "lock.doc")
                    }
                }

                Section {
                    Button(session.isGuest ? "Leave guest workspace" : "Sign out", role: .destructive) {
                        confirmSignOut = true
                    }
                    .accessibilityIdentifier("signOut")
                } footer: {
                    VStack(spacing: 8) {
                        ManifestMark(size: 26)
                        Text("Manifest \(AppConfig.appVersion)")
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.top, 16)
                }
            }
            .navigationTitle("Account")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
            .confirmationDialog(
                session.isGuest ? "Leave the guest workspace?" : "Sign out of Manifest?",
                isPresented: $confirmSignOut, titleVisibility: .visible
            ) {
                Button(session.isGuest ? "Leave" : "Sign out", role: .destructive) {
                    Task {
                        dismiss()
                        await session.signOut()
                    }
                }
            } message: {
                Text(session.isGuest ? "Guest ideas aren't saved to an account." : "Your ideas stay safe in your account.")
            }
            .task {
                let userID = session.user?.userId
                async let key = try? API.aiKeyStatus()
                if let userID { stats = try? await API.socialStats(userId: userID) }
                aiKey = await key
            }
        }
    }
}

// MARK: Profile

struct ProfileEditView: View {
    @Environment(SessionModel.self) private var session
    @Environment(\.dismiss) private var dismiss
    @State private var firstName = ""
    @State private var lastName = ""
    @State private var username = ""
    @State private var bio = ""
    @State private var country = ""
    @State private var skills = ""
    @State private var saving = false
    @State private var error: String?

    var body: some View {
        Form {
            Section("Name") {
                TextField("First name", text: $firstName).textContentType(.givenName)
                TextField("Last name", text: $lastName).textContentType(.familyName)
                TextField("Username", text: $username)
                    .textContentType(.username)
                    .autocorrectionDisabled()
                    #if os(iOS)
                    .textInputAutocapitalization(.never)
                    #endif
            }
            Section("About") {
                TextField("A line about what you build", text: $bio, axis: .vertical).lineLimit(3...)
                TextField("Country", text: $country).textContentType(.countryName)
            }
            Section {
                TextField("Design, Swift, sales…", text: $skills)
            } header: {
                Text("Skills")
            } footer: {
                Text("Separate with commas. Founders looking for help see these.")
            }
            Section {
                LabeledContent("Email", value: session.user?.email ?? "")
            } footer: {
                Text("Your email comes from Open Media and can be changed there.")
            }
            if let error { Section { Text(error).foregroundStyle(Theme.danger) } }
        }
        .navigationTitle("Profile")
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button {
                    save()
                } label: {
                    if saving { ProgressView() } else { Text("Save").fontWeight(.semibold) }
                }
                .disabled(saving)
            }
        }
        .onAppear {
            guard let user = session.user else { return }
            firstName = user.firstName ?? ""
            lastName = user.lastName ?? ""
            username = user.username ?? ""
            bio = user.bio ?? ""
            country = user.country ?? ""
            skills = user.skills.joined(separator: ", ")
        }
    }

    private func save() {
        saving = true
        error = nil
        Task {
            do {
                let list = skills.split(separator: ",").map { String($0).trimmed }.filter { !$0.isEmpty }
                let user = try await API.updateAccount([
                    "firstName": .string(firstName.trimmed), "lastName": .string(lastName.trimmed),
                    "username": .optional(username.trimmed.nilIfEmpty), "bio": .string(bio.trimmed),
                    "country": .string(country.trimmed), "skills": .strings(list),
                ])
                session.update(user)
                Haptics.success()
                dismiss()
            } catch {
                self.error = error.localizedDescription
            }
            saving = false
        }
    }
}

// MARK: AI key

struct AIKeyView: View {
    @Binding var status: AIKeyStatus?
    @State private var key = ""
    @State private var saving = false
    @State private var error: String?
    @State private var toast: Toast?

    var body: some View {
        Form {
            Section {
                LabeledContent("Status") {
                    if let status, status.configured {
                        Label("Active · ends in \(status.last4 ?? "····")", systemImage: "checkmark.circle.fill")
                            .foregroundStyle(Theme.success)
                    } else {
                        Text("No key").foregroundStyle(Theme.warning)
                    }
                }
            }
            Section {
                SecureField("sk-…", text: $key)
                    .textContentType(.password)
                    .autocorrectionDisabled()
                    #if os(iOS)
                    .textInputAutocapitalization(.never)
                    #endif
                Button {
                    save()
                } label: {
                    HStack {
                        Text(status?.configured == true ? "Replace key" : "Save key").fontWeight(.semibold)
                        if saving { Spacer(); ProgressView() }
                    }
                }
                .disabled(!key.trimmed.hasPrefix("sk-") || saving)
            } header: {
                Text("Your OpenAI key")
            } footer: {
                Text("Stored encrypted on Manifest's servers and only used for your own generations. Create one at platform.openai.com → API keys.")
            }
            if status?.configured == true {
                Section {
                    Button("Remove key", role: .destructive) {
                        Task {
                            do { status = try await API.removeAIKey(); toast = Toast(message: "Key removed") } catch {
                                self.error = error.localizedDescription
                            }
                        }
                    }
                }
            }
            if let error { Section { Text(error).foregroundStyle(Theme.danger) } }
        }
        .navigationTitle("OpenAI key")
        .toast($toast)
    }

    private func save() {
        saving = true
        error = nil
        Task {
            do {
                status = try await API.saveAIKey(key.trimmed)
                key = ""
                toast = Toast(message: "Key saved", symbol: "key.fill")
                Haptics.success()
            } catch {
                self.error = error.localizedDescription
            }
            saving = false
        }
    }
}

// MARK: Connections

struct ConnectionsView: View {
    @State private var link: OpenMediaLink?
    @State private var integrations: [Integration] = []
    @State private var error: String?
    @Environment(\.openURL) private var openURL

    var body: some View {
        List {
            Section {
                HStack(spacing: 12) {
                    Image("OpenMediaMark").resizable().frame(width: 34, height: 34).clipShape(.rect(cornerRadius: 8))
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Open Media").font(.subheadline.weight(.semibold))
                        Text(linkStatus).font(.caption).foregroundStyle(Theme.secondaryText)
                    }
                    Spacer()
                    if let link, !link.linked || link.needsReconnect {
                        Button(link.needsReconnect ? "Reconnect" : "Connect") {
                            if let url = URL(string: link.connectUrl, relativeTo: AppConfig.baseURL) { openURL(url) }
                        }
                        .glassButtonStyle(prominent: true)
                        .controlSize(.small)
                    }
                }
            } footer: {
                Text("Your sign-in, and the network your founder messages travel on.")
            }

            if !integrations.isEmpty {
                Section("Connected services") {
                    ForEach(integrations) { integration in
                        LabeledContent(integration.serviceName) {
                            Text("Since \(integration.connectedAt.formatted(.dateTime.month().year()))")
                        }
                        .swipeActions {
                            Button("Disconnect", role: .destructive) {
                                Task {
                                    error = await attempt { try await API.disconnectIntegration(integration.serviceId) }
                                    await load()
                                }
                            }
                        }
                    }
                }
            }
            if let error { Section { Text(error).foregroundStyle(Theme.danger) } }
        }
        .navigationTitle("Connections")
        .task { await load() }
        .refreshable { await load() }
    }

    private var linkStatus: String {
        guard let link else { return "Checking…" }
        if link.needsReconnect { return "Needs reconnecting" }
        if link.linked { return link.handle.map { "Connected as @\($0)" } ?? "Connected" }
        return "Not connected"
    }

    private func load() async {
        async let l = API.openMediaLink()
        async let i = API.integrations()
        link = try? await l
        integrations = ((try? await i) ?? []).filter { $0.serviceId != "openai" && $0.serviceId != "open_media" }
    }
}

// MARK: Sessions

struct SessionsView: View {
    @State private var sessions: [SessionInfo] = []
    @State private var loading = true
    @State private var error: String?
    @State private var toast: Toast?

    var body: some View {
        List {
            Section {
                if loading && sessions.isEmpty { ProgressView().frame(maxWidth: .infinity) }
                ForEach(sessions) { info in
                    HStack(spacing: 12) {
                        Image(systemName: symbol(for: info))
                            .font(.title3)
                            .foregroundStyle(info.current ? Theme.accent : Theme.secondaryText)
                            .frame(width: 30)
                        VStack(alignment: .leading, spacing: 2) {
                            HStack {
                                Text(title(for: info)).font(.subheadline.weight(.semibold)).lineLimit(1)
                                if info.current { StatusPill(text: "This device", color: Theme.success) }
                            }
                            Text(detail(for: info)).font(.caption).foregroundStyle(Theme.secondaryText)
                        }
                    }
                    .swipeActions {
                        if !info.current {
                            Button("Sign out", role: .destructive) { revoke(info) }
                        }
                    }
                }
            } footer: {
                Text("Swipe a device to sign it out.")
            }
            if sessions.filter({ !$0.current }).count > 0 {
                Section {
                    Button("Sign out all other devices", role: .destructive) {
                        Task {
                            do {
                                let count = try await API.revokeOtherSessions()
                                toast = Toast(message: "Signed out \(count) device\(count == 1 ? "" : "s")")
                                await load()
                            } catch { self.error = error.localizedDescription }
                        }
                    }
                }
            }
            if let error { Section { Text(error).foregroundStyle(Theme.danger) } }
        }
        .navigationTitle("Devices")
        .toast($toast)
        .task { await load() }
        .refreshable { await load() }
    }

    private func load() async {
        do {
            sessions = try await API.sessions()
                .filter { $0.kind != "revoked" }
                .sorted { ($0.current ? 1 : 0, $0.lastSeenAt ?? .distantPast) > ($1.current ? 1 : 0, $1.lastSeenAt ?? .distantPast) }
        } catch { self.error = error.localizedDescription }
        loading = false
    }

    private func revoke(_ info: SessionInfo) {
        Task {
            error = await attempt { try await API.revokeSession(info.sessionId) }
            await load()
        }
    }

    private func symbol(for info: SessionInfo) -> String {
        let agent = (info.userAgent ?? "").lowercased()
        if agent.contains("iphone") { return "iphone" }
        if agent.contains("ipad") { return "ipad" }
        if agent.contains("mac") { return "laptopcomputer" }
        if info.kind == "cli" { return "terminal" }
        if info.kind == "agent" { return "sparkles" }
        return "globe"
    }

    private func title(for info: SessionInfo) -> String {
        if info.kind != "browser", let label = info.userAgent?.nilIfEmpty { return label }
        let agent = info.userAgent ?? ""
        let browser = ["Edg": "Edge", "Chrome": "Chrome", "Firefox": "Firefox", "Safari": "Safari"]
            .first { agent.contains($0.key) }?.value ?? "Browser"
        return "\(browser) on the web"
    }

    private func detail(for info: SessionInfo) -> String {
        let seen = info.lastSeenAt.map { "Active \(Format.relative($0))" } ?? "Signed in \(info.createdAt.map(Format.relative) ?? "")"
        return [seen, info.requestIp].compactMap { $0 }.joined(separator: " · ")
    }
}

// MARK: Data

struct DataView: View {
    @Environment(IdeasStore.self) private var ideas
    @State private var exported: ExportFile?
    @State private var importing = false
    @State private var busy = false
    @State private var message: String?
    @State private var error: String?

    var body: some View {
        List {
            Section {
                Button { export("json") } label: { Label("Export as JSON", systemImage: "curlybraces") }
                Button { export("csv") } label: { Label("Export as CSV", systemImage: "tablecells") }
                Button { export("markdown") } label: { Label("Export as Markdown", systemImage: "text.document") }
            } header: {
                Text("Export")
            } footer: {
                Text("Every idea with its documents. Yours to keep.")
            }
            Section {
                Button { importing = true } label: { Label("Import ideas from a file", systemImage: "square.and.arrow.down") }
            } header: {
                Text("Import")
            } footer: {
                Text("JSON or CSV exported from Manifest, or a CSV with title and description columns.")
            }
            if busy { Section { ProgressView().frame(maxWidth: .infinity) } }
            if let message { Section { Label(message, systemImage: "checkmark.circle.fill").foregroundStyle(Theme.success) } }
            if let error { Section { Text(error).foregroundStyle(Theme.danger) } }
        }
        .navigationTitle("Import and export")
        .disabled(busy)
        .fileExporter(
            isPresented: Binding(get: { exported != nil }, set: { if !$0 { exported = nil } }),
            document: exported,
            contentType: exported?.type ?? .json,
            defaultFilename: exported?.filename
        ) { result in
            if case .success = result { message = "Exported" }
            exported = nil
        }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.json, .commaSeparatedText, .plainText]) { result in
            guard case .success(let url) = result else { return }
            importFile(url)
        }
    }

    private func export(_ format: String) {
        busy = true
        error = nil
        message = nil
        Task {
            do {
                let result = try await API.exportIdeas(format: format)
                let type: UTType = format == "csv" ? .commaSeparatedText : format == "json" ? .json : .plainText
                exported = ExportFile(text: result.content, type: type, filename: result.filename)
            } catch { self.error = error.localizedDescription }
            busy = false
        }
    }

    private func importFile(_ url: URL) {
        busy = true
        error = nil
        message = nil
        Task {
            let access = url.startAccessingSecurityScopedResource()
            defer { if access { url.stopAccessingSecurityScopedResource() } }
            do {
                let content = try String(contentsOf: url, encoding: .utf8)
                let format = url.pathExtension.lowercased() == "csv" ? "csv" : "json"
                let result = try await API.importIdeas(content: content, format: format, filename: url.lastPathComponent)
                message = "Imported \(result.importedCount), skipped \(result.skippedCount)"
                if let first = result.errors.first { error = first }
                await ideas.refresh()
            } catch { self.error = error.localizedDescription }
            busy = false
        }
    }
}

struct ExportFile: FileDocument {
    static let readableContentTypes: [UTType] = [.json, .commaSeparatedText, .plainText]
    let text: String
    var type: UTType = .json
    var filename = "manifest-ideas"

    init(text: String, type: UTType, filename: String) {
        self.text = text
        self.type = type
        self.filename = filename
    }

    init(configuration: ReadConfiguration) throws {
        text = String(decoding: configuration.file.regularFileContents ?? Data(), as: UTF8.self)
    }

    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        FileWrapper(regularFileWithContents: Data(text.utf8))
    }
}

// MARK: Privacy

struct PrivacyView: View {
    @Environment(SessionModel.self) private var session
    @State private var status: PrivacyStatus?
    @State private var confirmEmail = ""
    @State private var askDelete = false
    @State private var error: String?
    @State private var requested = false

    var body: some View {
        Form {
            Section {
                Text("Your ideas are private until you publish them. Manifest never sells your data or trains models on it.")
                    .font(.subheadline)
                Link("Read the Privacy Policy", destination: AppConfig.baseURL.appending(path: "legal/privacy"))
            }
            if let date = status?.deletionRequestedAt {
                Section {
                    Label("Deletion requested \(date.formatted(date: .abbreviated, time: .omitted))", systemImage: "clock")
                        .foregroundStyle(Theme.warning)
                }
            } else if !session.isGuest {
                Section {
                    Button("Delete my account", role: .destructive) { askDelete = true }
                } footer: {
                    Text("Removes your ideas, documents and profile. Export first if you want a copy.")
                }
            }
            if requested {
                Section { Label("Request received. We'll email you to confirm.", systemImage: "checkmark.circle.fill").foregroundStyle(Theme.success) }
            }
            if let error { Section { Text(error).foregroundStyle(Theme.danger) } }
        }
        .navigationTitle("Privacy")
        .task { status = try? await API.privacyStatus() }
        .alert("Delete your account?", isPresented: $askDelete) {
            TextField("Type your email", text: $confirmEmail)
                .textContentType(.emailAddress)
                #if os(iOS)
                .textInputAutocapitalization(.never)
                #endif
            Button("Delete", role: .destructive) {
                Task {
                    do {
                        try await API.requestAccountDeletion(email: confirmEmail.trimmed)
                        requested = true
                        status = try? await API.privacyStatus()
                    } catch { self.error = error.localizedDescription }
                    confirmEmail = ""
                }
            }
            Button("Cancel", role: .cancel) { confirmEmail = "" }
        } message: {
            Text("This can't be undone. Type \(session.user?.email ?? "your email") to confirm.")
        }
    }
}

// MARK: Feedback

struct FeedbackView: View {
    @Environment(SessionModel.self) private var session
    @Environment(\.dismiss) private var dismiss
    @State private var message = ""
    @State private var sending = false
    @State private var sent = false
    @State private var error: String?

    var body: some View {
        Form {
            Section {
                TextField("What's working, what isn't, what you wish it did", text: $message, axis: .vertical)
                    .lineLimit(6...)
            } footer: {
                Text("Goes straight to the people who build Manifest.")
            }
            if sent { Section { Label("Thank you. We read every one.", systemImage: "heart.fill").foregroundStyle(Theme.accent) } }
            if let error { Section { Text(error).foregroundStyle(Theme.danger) } }
        }
        .navigationTitle("Feedback")
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("Send") { send() }.fontWeight(.semibold).disabled(message.trimmed.count < 3 || sending || sent)
            }
        }
    }

    private func send() {
        sending = true
        Task {
            do {
                let user = session.user
                try await API.submitFeedback(
                    firstName: user?.firstName?.nilIfEmpty ?? user?.displayName ?? "Manifest",
                    lastName: user?.lastName?.nilIfEmpty ?? "User",
                    email: user?.email ?? "",
                    message: "[\(AppConfig.deviceName) app \(AppConfig.appVersion)] " + message.trimmed
                )
                sent = true
                Haptics.success()
            } catch { self.error = error.localizedDescription }
            sending = false
        }
    }
}
