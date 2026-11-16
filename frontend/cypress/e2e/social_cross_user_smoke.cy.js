const openShorts = () => {
  cy.contains("Discover", { timeout: 15000 }).click();
  cy.url({ timeout: 15000 }).should("include", "/discover");
  cy.get('[data-testid="tab-shorts"]', { timeout: 15000 }).click();
  cy.url({ timeout: 15000 }).should("include", "view=shorts");
  cy.get('[data-testid="shorts-page"]', { timeout: 15000 }).should("be.visible");
};

// Reel likes run on Open Media: run with CYPRESS_openMedia=1 (see social_pitch_shorts.cy.js).
const describeWithOpenMedia = Cypress.env("openMedia") ? describe : describe.skip;

describeWithOpenMedia("Cross-user social state smoke", () => {
  it("keeps reel like state scoped to the current user", () => {
    let clipTestId = "";
    let bobInitialLabel = "";

    cy.loginAsPersona("bob-okonkwo");
    openShorts();
    cy.get('[data-testid^="short-clip-"]').first().as("bobClip");
    cy.get("@bobClip")
      .invoke("attr", "data-testid")
      .then((value) => {
        clipTestId = value;
      });
    cy.get("@bobClip")
      .find('[data-testid^="short-like-"]')
      .invoke("attr", "aria-label")
      .then((value) => {
        bobInitialLabel = value;
      });

    cy.resetAuthState();
    cy.loginAsPersona("alice-chen");
    openShorts();

    cy.get(`[data-testid="${clipTestId}"]`)
      .find('[data-testid^="short-like-"]')
      .click({ force: true });
    cy.get('[data-testid="shorts-feedback"]', { timeout: 10000 }).should("be.visible");

    cy.resetAuthState();
    cy.loginAsPersona("bob-okonkwo");
    openShorts();

    cy.get(`[data-testid="${clipTestId}"]`, { timeout: 15000 })
      .find('[data-testid^="short-like-"]')
      .should("have.attr", "aria-label", bobInitialLabel);
  });
});
