import { expect, test } from "@playwright/test";

/**
 * Landing-page smoke. The deployed root must:
 *  - return 2xx
 *  - render the brand name
 *  - not log any uncaught console errors in the first render frame
 *
 * Failures here are high severity — a broken landing page is
 * effectively an outage. Tag the test accordingly so the issue label
 * comes back as severity:high.
 */
test.describe("landing @sev:high", () => {
  test("renders Manifest brand and is free of console errors", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });

    const response = await page.goto("/");
    expect(response, "navigation response").not.toBeNull();
    expect(response!.status(), "landing http status").toBeLessThan(400);

    await expect(page).toHaveTitle(/manifest/i);
    await expect(
      page.getByText(/manifest/i).first(),
    ).toBeVisible();

    expect(consoleErrors, "console errors during initial render").toEqual([]);
  });
});
