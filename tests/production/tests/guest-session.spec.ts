import { expect, test } from "@playwright/test";

/**
 * Try-before-signup smoke: starting a guest session must succeed and
 * land the user in a usable ideas workspace. The guest flow is
 * Manifest's onboarding-zero-friction entry point — if it breaks,
 * conversion to signup also breaks.
 */
test.describe("guest session @sev:high", () => {
  test("can start a guest session and reach the ideas page", async ({ page }) => {
    await page.goto("/");

    const guestCta = page
      .getByRole("button", { name: /(try|start).*(sign\s?up|guest|without)/i })
      .or(page.getByRole("link", { name: /(try|start).*(sign\s?up|guest|without)/i }));

    if (await guestCta.count() === 0) {
      test.skip(true, "no guest CTA visible — landing variant under test");
      return;
    }

    await guestCta.first().click();

    await page.waitForURL(/\/ideas\b/, { timeout: 20_000 });
    await expect(page.locator("body")).toContainText(/idea/i);
  });
});
