describe("Privacy consent", () => {
  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it("shows the consent banner on a fresh visit without blocking the hero", () => {
    cy.visit("/");
    cy.contains("Privacy choices", { timeout: 10000 }).should("be.visible");
    cy.contains("The Social Network for Startup Builders and Investors", { timeout: 10000 }).should("be.visible");
  });

  it("stores an essential-only choice and hides the banner", () => {
    cy.visit("/");
    cy.contains("Essential only", { timeout: 10000 }).click();
    cy.contains("Privacy choices").should("not.exist");
    cy.getCookie("manifest_privacy_consent").should("exist");
  });
});
