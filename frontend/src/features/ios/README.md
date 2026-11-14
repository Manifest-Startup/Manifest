# iOS App for Manifest

This directory contains the iOS-styled version of the Manifest app that runs in the browser with native iOS design patterns. The iOS app maintains full feature parity with the web application.

**Current Status**: Full feature parity with web application (verified December 2025)

## Feature Parity with Web App

The iOS app includes all features available in the web version:

### Core Features
- **Ideas Management**: Create, view, edit ideas with full document generation
- **Publish Tick Indicators**: Grey/blue tick to toggle publish status (visible in ideas list)
- **Voice Agent**: Floating voice button for AI-powered ideation
- **Shorts**: Full-screen startup discovery with comments, follows, and sharing
- **Portfolio**: Investment tracking and management

### Account Features
- **Portfolio Tab**: View investments with statistics (total investments, value, equity)
- **Settings Tab**: Full settings management including:
  - Appearance (Light/Dark/System theme toggle)
  - Profile editing (name, email, photo)
  - API Access management
  - Integrations connections
  - Data Management (Import/Export ideas)

### Dark Mode Support
Full dark mode support across all iOS components with system preference synchronization.

## Components

### Core Components
- `IOSNavigationBar`: Top navigation bar with iOS styling and dark mode support
- `IOSTabBar`: Bottom tab bar with 4 tabs (Ideas, Portfolio, Shorts, Account)
- `IOSPageWrapper`: Page container with safe area support and dark mode
- `IOSViewToggle`: Button to switch between desktop/iOS views

### Pages
- `IOSIdeasPage`: iOS-styled ideas list with publish tick indicators and idea detail view
- `IOSAuthForm`: iOS-styled authentication form
- `IOSAccountPage`: Full-featured account page with portfolio/settings tabs
- `IOSPitchShortsPage`: iOS-styled pitch shorts page

### Utilities
- `deviceDetection.ts`: Device type detection and responsive utilities
- `viewMode.ts`: View mode management (desktop/iOS/auto)

## Testing

Component tests are located in `__tests__/`:
- `IOSFeatureParity.test.tsx`: Tests for iOS components, dark mode, and navigation (17 tests)
- `IOSComponents.test.tsx`: Tests for IOSPageWrapper and IOSViewToggle (10 tests)

Run tests with:
```bash
cd frontend && npm test -- --testPathPattern=ios
```

**Note**: Tests cover component rendering and dark mode styling. Integration tests for portfolio, settings mutations, and idea workflows are planned for future enhancement.

## Usage

The iOS app automatically activates when:
1. View mode is set to "ios" in localStorage
2. View mode is set to "auto" and the device is detected as iOS
3. User manually toggles to iOS view using the toggle button

## View Modes

- **Desktop**: Traditional desktop layout
- **iOS**: Native iOS-styled layout
- **Auto**: Automatically switches based on device detection

## Styling

All iOS-specific styles are defined in `index.css` with the `.ios-` prefix. The app uses:
- SF Pro Display/Text font stack (iOS system fonts)
- Native iOS colors and spacing
- iOS-style animations and transitions
- Safe area insets for notched devices
- Full dark mode support with `dark:` Tailwind classes

## Design Principles

Following the core product principles:
1. **Extremely Easy to Use**: Minimal buttons, intuitive navigation via bottom tab bar
2. **Extremely Robust**: Consistent behavior with web app, comprehensive error handling
3. **Inexpensive**: Lightweight components, efficient renders

## Browser Support

The iOS app works in all modern browsers and can be viewed on:
- Desktop browsers (with view toggle)
- Mobile browsers (iOS and Android)
- Tablet browsers
