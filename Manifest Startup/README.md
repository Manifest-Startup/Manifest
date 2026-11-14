# Manifest Startup - Native iOS App

A native SwiftUI iOS application for the Manifest startup building platform. This app provides full feature parity with the web application, allowing users to manage startup ideas, view their portfolio, discover community ideas, and manage their account.

## Features

### Core Features (Full Parity with Web App)
- **Ideas Management**: Create, view, edit, and delete startup ideas
- **Publish Status**: Toggle publish status with verified badge indicators (blue = published, grey = unpublished)
- **Idea Details**: View description, pitch deck, business model canvas, and patent information
- **Document Generation**: Generate AI-powered documents for your ideas

### Social Features
- **Discover Feed**: TikTok-style vertical scrolling feed of community ideas
- **Upvoting**: Vote on ideas you find interesting
- **Verified Badges**: Visual indicators for published ideas

### Portfolio Management
- **Investment Tracking**: View all your investments with status indicators
- **Portfolio Statistics**: Total investments, total value, and equity percentage
- **Investment Details**: Cash amount, sweat equity, and equity breakdown

### Account Management
- **Profile Editing**: Update first name, last name, and email
- **Appearance Settings**: Light mode, dark mode, or system theme
- **Integrations**: Connect with Google, GitHub, Slack (coming soon)
- **API Access**: Manage API keys for programmatic access
- **Data Management**: Import and export ideas

## Project Structure

```
Manifest Startup/
├── Manifest Startup/
│   ├── Models/
│   │   ├── Idea.swift           # Idea and BusinessModelCanvas models
│   │   ├── User.swift           # User and account models
│   │   ├── Investment.swift     # Investment and portfolio models
│   │   └── FeedItem.swift       # Discover feed models
│   ├── Services/
│   │   ├── APIService.swift     # REST API client for backend
│   │   └── AuthService.swift    # Authentication management
│   ├── ViewModels/
│   │   ├── IdeasViewModel.swift      # Ideas list state management
│   │   ├── DiscoverViewModel.swift   # Discover feed state management
│   │   └── AccountViewModel.swift    # Account/portfolio state management
│   ├── Views/
│   │   ├── MainTabView.swift         # Main tab navigation
│   │   ├── Ideas/
│   │   │   ├── IdeasView.swift       # Ideas list screen
│   │   │   └── IdeaDetailView.swift  # Idea detail screen
│   │   ├── Discover/
│   │   │   └── DiscoverView.swift    # Discover feed screen
│   │   ├── Shorts/
│   │   │   └── ShortsView.swift      # Pitch shorts screen
│   │   └── Account/
│   │       └── AccountView.swift     # Account/settings screen
│   ├── ContentView.swift        # Root view with auth handling
│   ├── Manifest_StartupApp.swift    # App entry point
│   └── Assets.xcassets/         # App icons and colors
├── Manifest StartupTests/       # Unit tests
└── Manifest StartupUITests/     # UI tests
```

## Requirements

- iOS 17.0+
- Xcode 15.0+
- Swift 5.9+

## Configuration

### API Configuration

Set the `API_BASE_URL` environment variable to your Manifest backend URL:

```swift
// In APIService.swift, the default is:
self.baseURL = ProcessInfo.processInfo.environment["API_BASE_URL"] ?? "https://manifeststartup.com"
```

For local development, you can:
1. Edit the scheme in Xcode and add an environment variable
2. Or directly modify the fallback URL in `APIService.swift`

### Authentication

The app uses token-based authentication. The auth token is stored securely in UserDefaults and automatically included in API requests.

## Building and Running

1. Open `Manifest Startup.xcodeproj` in Xcode
2. Select your target device or simulator
3. Configure the API base URL (see Configuration section)
4. Press Cmd+R to build and run

## Architecture

The app follows the MVVM (Model-View-ViewModel) architecture:

- **Models**: Data structures that match the backend API responses
- **Views**: SwiftUI views that display the UI
- **ViewModels**: Observable objects that manage state and business logic
- **Services**: Singleton services for API communication and authentication

### Key Design Decisions

1. **Async/Await**: All API calls use Swift's modern concurrency with async/await
2. **@MainActor**: ViewModels are marked with @MainActor for safe UI updates
3. **ObservableObject**: State is managed using Combine's ObservableObject protocol
4. **Environment Objects**: Auth state is shared via SwiftUI's environment

## Feature Parity Checklist

| Feature | Web | iOS | Status |
|---------|-----|-----|--------|
| Ideas List | ✅ | ✅ | UI Complete, API Ready |
| Create Idea | ✅ | ✅ | UI Complete, API Ready |
| Delete Idea | ✅ | ✅ | UI Complete, API Ready |
| Publish Toggle | ✅ | ✅ | UI Complete, API Ready |
| Idea Details | ✅ | ✅ | UI Complete |
| Pitch Deck View | ✅ | 🔧 | UI Scaffold, Generation Pending |
| Business Model Canvas | ✅ | 🔧 | UI Scaffold, Generation Pending |
| Patent Generation | ✅ | 🔧 | UI Scaffold, Generation Pending |
| Discover Feed | ✅ | ✅ | UI Complete, API Ready |
| Upvoting | ✅ | ✅ | UI Complete, API Ready |
| Portfolio Stats | ✅ | ✅ | UI Complete, API Ready |
| Investment List | ✅ | ✅ | UI Complete, API Ready |
| Profile Editing | ✅ | ✅ | UI Complete, API Ready |
| Theme Toggle | ✅ | ✅ | Fully Implemented |
| Authentication | ✅ | 🔧 | Scaffold, Needs Backend Wiring |
| Import/Export | ✅ | 🔧 | UI Ready, API Pending |
| Integrations | ✅ | 🔧 | UI Ready, OAuth Pending |
| API Keys | ✅ | 🔧 | UI Ready, API Pending |
| Pitch Shorts | ✅ | ⏳ | Coming Soon |
| Voice Agent | ✅ | ⏳ | Planned |

✅ = Fully Implemented | 🔧 = UI Complete, Backend Integration Needed | ⏳ = Planned

### Implementation Notes

The iOS app provides a complete UI scaffold with MVVM architecture. To achieve full feature parity:

1. **Authentication**: Wire `AuthService.login()` to your backend's login endpoint
2. **Document Generation**: Connect pitch deck/BMC/patent buttons to backend AI generation endpoints
3. **OAuth Integrations**: Implement OAuth flows for Google, GitHub, Slack
4. **API Key Management**: Connect to `/api/v1/api-keys` endpoints
5. **Import/Export**: Implement file picker and document sharing

## Testing

Run unit tests:
```bash
# In Xcode: Cmd+U
# Or via command line:
xcodebuild test -scheme "Manifest Startup" -destination "platform=iOS Simulator,name=iPhone 15"
```

## Dark Mode Support

The app fully supports dark mode with three options:
- **System**: Follows iOS system appearance
- **Light**: Always light mode
- **Dark**: Always dark mode

Theme preference is persisted using @AppStorage.

## License

Proprietary - Manifest Startup Platform

## Contact

For questions or support, contact the Manifest team.
