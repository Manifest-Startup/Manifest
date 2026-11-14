import { defineConfig, devices } from "@playwright/test";

/**
 * Manifest continuous production-test suite.
 *
 * Tests run against the deployed site (MANIFEST_TEST_TARGET_URL, defaults
 * to https://manifeststartup.com). Each test posts its result to the
 * deployed backend's /api/internal/production-tests/results via the
 * custom reporter at ./reporter/manifest-reporter.ts. The reporter is
 * wired in automatically via reporters[] below — no manual hook needed
 * in tests.
 *
 * Local invocation: set MANIFEST_TEST_TARGET_URL to your local dev URL
 * (e.g. http://localhost:5000) and DROP MANIFEST_AGENT_LOOP_SECRET so the
 * reporter falls back to "log only". See docs/PRODUCTION_TESTING.md.
 */

const TARGET_URL = process.env.MANIFEST_TEST_TARGET_URL || "https://manifeststartup.com";

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "playwright-report" }],
    ["./reporter/manifest-reporter.ts"],
  ],
  use: {
    baseURL: TARGET_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
