/** @type {import('lighthouse').Config} */
module.exports = {
  ci: {
    collect: {
      numberOfRuns: 1,
      settings: {
        preset: "desktop",
        // CI headless Chrome often needs explicit flags to paint content (avoids NO_FCP flakes).
        chromeFlags:
          "--no-sandbox --disable-dev-shm-usage --disable-gpu --window-size=1280,720",
      },
      startServerCommand: "npx vite preview --host 127.0.0.1 --port 4173 --strictPort",
      startServerReadyPattern: "4173",
      url: ["http://127.0.0.1:4173/"],
    },
    assert: {
      assertions: {
        "categories:performance": ["warn", { minScore: 0.35 }],
        "cumulative-layout-shift": ["warn", { maxNumericValue: 0.35 }],
        "total-blocking-time": ["warn", { maxNumericValue: 900 }],
      },
    },
  },
};
