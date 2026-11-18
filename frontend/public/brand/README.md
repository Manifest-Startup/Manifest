# Brand marks

Manifest's own mark and the third-party marks shown in its UI, served as static files.

## Manifest

- `manifest-mark.svg`: the app-icon tile (ink `#1d1d1f`, rounded 23/100) with the white rising M.
- `manifest-glyph.svg`: the M alone, for places that supply their own background.
- Geometry: path `M25 78V35L50 60L75 26V78` in a 100 × 100 box, stroke 11, mitred joins. The right stroke rises above the left: an idea climbing into a plan.
- The same path drives `src/features/common-ui/ManifestLogo.tsx`, `favicon.svg` / `favicon.ico`, `logo192.png`, `logo512.png`, `apple-touch-icon.png`, `og-image.png`, the iOS app icons, `agent-plugin/assets/icon.png`, `docs/images/logo.png` and the README banner. Change them together and re-render the PNGs.

## Partners

- `open-media-mark-light.png` / `open-media-mark-dark.png`: the Open Media mark for light and dark backgrounds (96 px, downscaled from Open Media's `assets/brand/logo-*.png`). Used by the "Continue with Open Media" button.

Naming: `<partner>-mark-<light|dark>.png`. Agents: keep the originals' proportions, never recolour a mark, and keep each file small (it loads on the login page).
