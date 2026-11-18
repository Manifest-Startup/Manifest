# Banner source

`banner.html` is the self-contained source of `../banner-light.png` and `../banner-dark.png`. One file holds both themes; the dark theme is a `prefers-color-scheme: dark` media query using the site's `.dark` tokens. It uses the SF Pro system font stack, so render it on a Mac. Nothing here is served by the app.

Re-render from the repository root with headless Chromium at a 1600 × 600 viewport and a device scale factor of 2, once per color scheme. With Playwright:

```js
const page = await browser.newPage({ viewport: { width: 1600, height: 600 }, deviceScaleFactor: 2, colorScheme: 'light' });
await page.goto('file://' + path.resolve('.github/assets/source/banner.html'));
await page.evaluate(() => document.fonts.ready);
await page.screenshot({ path: '.github/assets/banner-light.png' });
```

Notes for agents: keep the "Demo · In development" pill while the site carries that label, use only demo ideas (never a real user's idea), and view both PNGs before committing.
