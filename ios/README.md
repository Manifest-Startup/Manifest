# Manifest for iPhone, iPad and Mac

The native Manifest app: one SwiftUI codebase and one Xcode target that runs on iPhone, iPad, Mac and Apple Vision Pro. It talks to the same GraphQL API as the web app at `https://manifeststartup.com/graphql`.

## What's in it

| Tab | What it does |
|---|---|
| **Ideas** | Your ideas, invitations and ideas shared with you. Create, edit, publish, delete. Each idea opens to its pitch, a live Business Model Canvas, four AI documents (pitch deck, PRD, provisional patent, landscape), a "pressure test" interview with a score, team and roles, cap table and investments, and version history. |
| **Shorts** | Full-screen pitch shorts. Swipe up, double-tap to like, comment, share, follow founders, jump to the idea. |
| **Inbox** | Founder messages through Open Media, with live updates, optimistic sending and unread badges. |
| **Portfolio** | Your cash and sweat-equity positions, totals and allocation chart. |
| **Search** | Your ideas and published ones, with an assistant summary and recent searches. |
| **Account** (avatar button) | Profile, your OpenAI key (bring your own key), Open Media connection, signed-in devices, import and export, privacy and account deletion, feedback, appearance. |

## Architecture

```
Manifest Startup/
├── App/            entry point, session state, tab shell, observable stores
├── Core/
│   ├── Auth/       OAuth 2.1 + PKCE sign-in, Keychain, token refresh
│   ├── Networking/ GraphQL client (actor), typed operations (API.swift), demo fixtures
│   ├── Models/     Codable mirrors of the GraphQL types
│   └── Cache/      last-known responses on disk for instant launch
├── DesignSystem/   theme tokens, rising-M mark, components, image pipeline, Markdown
└── Features/       Onboarding, Ideas, Shorts, Inbox, Portfolio, Search, Account
```

- **SwiftUI + Observation, no third-party dependencies.** `@Observable` stores per feature, injected through the environment. Swift 6 language mode with `MainActor` default isolation; networking, decoding, image decoding and Markdown parsing run off the main actor.
- **Sign-in** uses Manifest's own OAuth server (`/api/oauth/*`, ADR 0004) as an RFC 8252 native app: dynamic client registration, PKCE S256, the `com.manifeststartup.ios:` callback scheme and `ASWebAuthenticationSession`. The web sheet handles "Continue with Open Media", so the app never sees a password. Tokens live in the Keychain. Refresh tokens rotate, and concurrent refreshes are coalesced. The session appears under Account → Signed-in devices as "Manifest for iPhone/iPad/Mac". Guests get a server-backed guest workspace.
- **Performance.** Stale-while-revalidate disk cache, so tabs paint before the network returns. Lean GraphQL selections. Lazy stacks. Downsampled images cached in memory. At most three video players alive in Shorts. Debounced search. Polling only while the scene is active.
- **Design.** Ink, paper and one blue, taken from the web theme (`frontend/src/index.css`). Liquid Glass for floating controls. Adaptive layouts: a tab bar on iPhone, a sidebar on iPad and Mac, and a full canvas grid on wide screens. Dynamic Type, VoiceOver labels and Reduce Motion are respected.

## Run it

1. Open `Manifest Startup.xcodeproj` in Xcode 26 or later (deployment target iOS / macOS / visionOS 26.2).
2. Choose the **Manifest Startup** scheme and an iPhone simulator, then Run.

To work against a local backend, set `MANIFEST_API_URL` (for example `http://localhost:8000`) in the scheme's environment variables. Debug builds only; release builds always use production.

**Demo mode.** Launch with the `-demo` argument (Debug builds) to use synthetic fixtures with no network and no account. UI tests and design review use it.

## Test

```bash
# Unit tests (Swift Testing) on macOS, fast and no simulator needed
xcodebuild test -project "ios/Manifest Startup.xcodeproj" -scheme "Manifest Startup" \
  -destination platform=macOS -only-testing:"Manifest StartupTests"

# UI journeys + screen tour on a simulator (demo fixtures)
xcodebuild test -project "ios/Manifest Startup.xcodeproj" -scheme "Manifest Startup" \
  -destination "platform=iOS Simulator,name=iPhone 17 Pro" -only-testing:"Manifest StartupUITests"

# Every GraphQL operation in the app validates against the backend schema
python3 scripts/check_ios_graphql.py
```

`python3 scripts/check.py` runs the schema check and the unit tests whenever `ios/` or the GraphQL schema changes (area `ios`).

## Release

Bundle ID `com.manifeststartup.Manifest-Startup`, team `RWUG6FUV62`, automatic signing. Ship through Xcode Cloud or Archive → TestFlight. Before you submit, bump `MARKETING_VERSION` and `CURRENT_PROJECT_VERSION`. The app declares no non-exempt encryption.
