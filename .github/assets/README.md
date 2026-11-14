# README assets

Images used by the root `README.md`. Nothing here is served by the app.

| File | What it is | How it was made |
| --- | --- | --- |
| `banner-light.png`, `banner-dark.png` | README banner for light and dark GitHub themes | Rendered at 3200 × 1200 from [`source/banner.html`](source/banner.html) |
| `hero-light.jpg`, `hero-dark.jpg` | The public manifeststartup.com landing page on desktop and phone, in light and dark appearance | Captured with headless Chromium on 2026-10-26 and placed in a browser and phone frame |
| `cli-terminal.png` | Real `manifest-dev --help` output | Run from `src/manifest_dev` and rendered as a terminal card |

## Visual identity

The README follows manifeststartup.com's own design tokens:

- **Type:** Manrope 600 with tight tracking for headlines and UI, Newsreader italic for the accent word, the same pair the site loads.
- **Colors:** ink `#16212c`, secondary `#566170`, border `#e7e7e5`, accent `#2f62e8`, accent soft `#ecf1ff`, success `#079455`, and the amber "Demo · In development" pill (`#b54708`). The dark banner uses the site's `.dark` tokens (`#10151c`, accent `#8faeff`). Badges use ink, accent and amber for the demo status.
- **Layout and motif:** left-aligned copy on the site's faint 40 px grid; a demo idea note (the same example as the public landing page) flows into a draft Business Model Canvas with market brief, business model and pitch outline. It is an illustration, not a screenshot.
- **Tone:** numbered promises (01, 02, 03, as on the landing page) instead of emoji.

Re-render after editing the source; see [`source/README.md`](source/README.md).

Rules for agents:

- Screenshots show only public pages or demo data. Never capture real user ideas, messages, investor data, emails or keys.
- Retake images when the UI changes, and keep README captions accurate.
- Keep files small (JPEG for screenshots).
