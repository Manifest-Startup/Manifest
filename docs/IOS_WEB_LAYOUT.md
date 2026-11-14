# iOS App Launch Guide

This guide explains how to launch and use the iOS-styled version of Manifest in your browser.

## Quick Start

1. **Start the application**:
   ```bash
   python3 scripts/start_app.py
   ```
   Or manually:
   ```bash
   # Terminal 1 - Backend
   cd backend
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   uvicorn app.main:app --reload

   # Terminal 2 - Frontend
   cd frontend
   npm start
   ```

2. **Open in browser**:
   - Desktop: http://localhost:3000
   - The app will automatically detect iOS devices and show iOS view
   - Use the toggle button (bottom right) to switch between Desktop and iOS views

## View Modes

### Desktop View
- Traditional desktop layout with sidebar navigation
- Optimized for larger screens
- Full feature set with multi-column layout

### iOS View
- Native iOS-styled interface
- Bottom tab bar navigation
- Touch-optimized interactions
- Mobile-first design patterns

## Switching Views

### Automatic Detection
- The app automatically shows iOS view on iOS devices when view mode is set to "auto"
- Desktop view is shown on desktop browsers by default

### Manual Toggle
- Look for the toggle button in the bottom-right corner
- Click to switch between Desktop and iOS views
- Your preference is saved in localStorage

## Features in iOS View

### Navigation
- **Top Bar**: Logo and profile menu
- **Bottom Tab Bar**: Quick navigation to Ideas, Pitch Shorts, and Account
- **Swipe Gestures**: Native iOS-style interactions

### Pages
- **Ideas List**: Card-based list with create button
- **Idea Detail**: Full-screen editor with collapsible similar ideas
- **Auth**: iOS-styled login/signup form
- **Account**: Profile settings with iOS design

### Interactions
- **Touch Feedback**: All buttons have active states
- **Smooth Animations**: Native iOS-style transitions
- **Safe Areas**: Proper handling of notched devices

## Browser Testing

### Desktop Browser
1. Open http://localhost:3000 in Chrome/Firefox/Safari
2. Click the toggle button to switch to iOS view
3. Resize browser window to see responsive behavior

### Mobile Browser
1. Open http://localhost:3000 on your phone
2. iOS view should activate automatically
3. Test touch interactions and navigation

### Device Emulation
1. Open Chrome DevTools (F12)
2. Click device toolbar icon (Ctrl+Shift+M)
3. Select iPhone or iPad device
4. iOS view should activate automatically

## Troubleshooting

### iOS View Not Showing
- Check localStorage: `localStorage.getItem('manifest_view_mode')`
- Try clicking the toggle button
- Clear browser cache and reload

### Styling Issues
- Ensure Tailwind CSS is compiled
- Check browser console for CSS errors
- Verify `index.css` includes iOS styles

### Navigation Issues
- Check that routes are properly configured
- Verify React Router is working
- Check browser console for errors

## Development

### Adding New iOS Pages
1. Create component in `frontend/src/features/ios/pages/`
2. Add route in `AppIOS.tsx`
3. Add navigation item in `IOSTabBar.tsx` if needed
4. Style with iOS design patterns

### Customizing iOS Styles
- Edit `frontend/src/index.css` (look for `.ios-` classes)
- Update Tailwind config for iOS-specific colors/spacing
- Use iOS design system guidelines

## Architecture

```
frontend/src/features/ios/
├── components/          # iOS UI components
│   ├── IOSNavigationBar.tsx
│   ├── IOSTabBar.tsx
│   ├── IOSPageWrapper.tsx
│   └── IOSViewToggle.tsx
├── pages/              # iOS-styled pages
│   ├── IOSIdeasPage.tsx
│   ├── IOSAuthForm.tsx
│   ├── IOSAccountPage.tsx
├── utils/              # Utilities
│   ├── deviceDetection.ts
│   └── viewMode.ts
└── AppIOS.tsx          # iOS app root
```

## Best Practices

1. **Reuse Logic**: iOS pages reuse business logic from desktop components
2. **No Code Duplication**: Share hooks, queries, and utilities
3. **Consistent Design**: Follow iOS Human Interface Guidelines
4. **Performance**: Optimize for mobile performance
5. **Accessibility**: Ensure touch targets are at least 44x44 points

## Next Steps

- Test on real iOS devices
- Add more iOS-specific animations
- Implement swipe gestures
- Add haptic feedback (if using Capacitor)
- Optimize for iPad layouts

