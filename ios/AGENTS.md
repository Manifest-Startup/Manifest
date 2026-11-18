# ios/ — native app (child guide)

SwiftUI app for iPhone, iPad, Mac and Vision Pro: one target, `Manifest Startup`. Read `README.md` for the architecture.

## Commands

- Build: `xcodebuild -project "ios/Manifest Startup.xcodeproj" -scheme "Manifest Startup" -destination "platform=iOS Simulator,name=iPhone 17 Pro" build`
- Unit tests (fast, macOS): add `test -destination platform=macOS -only-testing:"Manifest StartupTests"`
- Schema contract: `python3 scripts/check_ios_graphql.py` (also runs via `scripts/check.py`, area `ios`)
- Run with fake data: launch argument `-demo` (Debug only; `Core/Networking/Fixtures.swift`)

## Rules

- **GraphQL lives in `Core/Networking/API.swift` only**, as string literals with `static let` fragments. Select just the fields a screen renders. After any backend schema change, run the contract check.
- Models in `Core/Models/Models.swift` are `nonisolated` Codable structs whose field names match the schema's camelCase.
- Swift 6 with `MainActor` default isolation. Anything used from the `GraphQLClient`/`TokenStore` actors or detached tasks must be `nonisolated` and `Sendable`.
- Never name a type `Environment` (it shadows SwiftUI's property wrapper); app config is `AppConfig`.
- Tokens only in the Keychain (`Core/Auth`). Never log tokens or GraphQL variables.
- AI generation uses the person's own OpenAI key; surface `APIError.needsAIKey` and point them to Account → OpenAI key.
- Gate iOS-only modifiers with `#if os(iOS)`. The same target builds for macOS, so build both when you touch UI.
- The project uses file-system-synchronized groups: new files under `Manifest Startup/` are picked up without editing `project.pbxproj`.
