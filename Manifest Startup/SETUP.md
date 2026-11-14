# Manifest iOS App - Setup Guide

This guide will help you set up and run the Manifest iOS app on your development machine.

## Prerequisites

1. **macOS**: You need a Mac to develop iOS apps
2. **Xcode 15+**: Download from the Mac App Store
3. **Apple Developer Account**: Free account works for simulator testing

## Quick Start

### 1. Open the Project

```bash
cd "Manifest Startup"
open "Manifest Startup.xcodeproj"
```

### 2. Configure the API Endpoint

Edit `Manifest Startup/Services/APIService.swift` and update the base URL:

```swift
// Replace with your actual Manifest backend URL
self.baseURL = "https://manifeststartup.com"
```

### 3. Run the App

1. Select an iPhone simulator from the device dropdown (e.g., iPhone 15)
2. Press `Cmd + R` to build and run
3. The app will launch in the simulator

## Connecting to Your Backend

The iOS app connects to the same backend as the web application. Ensure your backend is running and accessible.

### API Endpoints Used

The app expects these REST API endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/ideas` | GET | List all ideas |
| `/api/v1/ideas` | POST | Create new idea |
| `/api/v1/ideas/{id}` | GET | Get idea details |
| `/api/v1/ideas/{id}/publish` | POST | Toggle publish status |
| `/api/v1/account` | GET | Get user account |
| `/api/v1/account` | PUT | Update account |
| `/api/v1/portfolio` | GET | Get investments |
| `/api/v1/feed` | GET | Get public feed |
| `/api/v1/ideas/{id}/upvote` | POST | Upvote idea |

### Authentication

The app sends the auth token in the `Authorization` header:

```
Authorization: Bearer <token>
```

## Testing on a Real Device

1. Connect your iPhone via USB
2. In Xcode, select your device from the device dropdown
3. You may need to trust the developer certificate on your device:
   - Go to Settings > General > VPN & Device Management
   - Trust your developer certificate

## Troubleshooting

### "Could not launch app"
- Make sure the simulator is fully booted
- Try restarting Xcode

### Network errors
- Verify the API base URL is correct
- Check that your backend is running
- Ensure the backend allows requests from the app (CORS if needed)

### Build errors
- Clean build folder: `Cmd + Shift + K`
- Restart Xcode
- Ensure you have the latest iOS SDK

## Project Files Overview

```
Manifest Startup/
├── Manifest_StartupApp.swift    # App entry point
├── ContentView.swift            # Auth routing
├── Models/                      # Data models
├── Services/                    # API & Auth services
├── ViewModels/                  # State management
└── Views/                       # SwiftUI screens
```

## Making Changes

### Adding a New Feature

1. Create model in `Models/` if needed
2. Add API method in `Services/APIService.swift`
3. Create ViewModel in `ViewModels/`
4. Create View in `Views/`

### Updating API Endpoints

All API calls are centralized in `Services/APIService.swift`. To add or modify endpoints:

```swift
func myNewEndpoint() async throws -> MyResponse {
    guard let request = createRequest(endpoint: "/api/v1/my-endpoint") else {
        throw APIError.invalidURL
    }
    let (data, _) = try await URLSession.shared.data(for: request)
    return try JSONDecoder().decode(MyResponse.self, from: data)
}
```

## Support

For issues with the iOS app, check:
1. This README and SETUP guide
2. The main project documentation in `README.md` and `docs/CLOUDFLARE_MIGRATION.md`
3. Contact the Manifest team for support
