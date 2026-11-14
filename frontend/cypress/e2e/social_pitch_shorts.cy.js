import { E2E_PERSONAS } from "../support/e2ePersonas";

const openShorts = () => {
  cy.contains("Discover", { timeout: 15000 }).click();
  cy.url({ timeout: 15000 }).should("include", "/discover");
  cy.get('[data-testid="tab-shorts"]', { timeout: 15000 }).click();
  cy.url({ timeout: 15000 }).should("include", "view=shorts");
  cy.get('[data-testid="shorts-page"]', { timeout: 15000 }).should("be.visible");
  cy.get('[data-testid^="short-clip-"]', { timeout: 20000 }).should("have.length.at.least", 1);
};

describe("Seeded persona sign-in smoke", () => {
  E2E_PERSONAS.forEach((persona) => {
    it(`${persona.displayName} can sign in`, () => {
      cy.loginAsPersona(persona.slug);
      cy.contains("New Idea", { timeout: 15000 }).should("be.visible");
    });
  });
});

describe("Pitch Shorts social interactions", () => {
  beforeEach(() => {
    cy.loginAsPersona("alice-chen");
    openShorts();
  });

  it("Alice Chen can exercise like, save, follow, share, comment, and invest flows", () => {
    const commentText = `Alice Chen social pass ${Date.now()}`;

    cy.get('[data-testid^="short-clip-"]').first().as("clip");

    cy.get("@clip")
      .find('[data-testid^="short-like-"]')
      .invoke("attr", "aria-label")
      .then((label) => {
        const expectedToast = label?.startsWith("Unlike") ? "Removed like." : "Liked reel.";
        cy.get("@clip").find('[data-testid^="short-like-"]').click({ force: true });
        cy.get('[data-testid="shorts-feedback"]', { timeout: 10000 }).should("contain.text", expectedToast);
      });

    cy.get("@clip")
      .find('[data-testid^="short-save-"]')
      .invoke("attr", "aria-label")
      .then((label) => {
        const expectedToast = label?.startsWith("Unsave") ? "Removed from saved." : "Saved reel.";
        cy.get("@clip").find('[data-testid^="short-save-"]').click({ force: true });
        cy.get('[data-testid="shorts-feedback"]', { timeout: 10000 }).should("contain.text", expectedToast);
      });

    cy.get("@clip")
      .find('[data-testid^="short-follow-"]')
      .invoke("text")
      .then((text) => {
        const currentState = text.trim();
        const expectedState = currentState === "Following" ? "Follow" : "Following";
        cy.get("@clip").find('[data-testid^="short-follow-"]').click({ force: true });
        cy.get("@clip").find('[data-testid^="short-follow-"]').should("contain.text", expectedState);
      });

    cy.get("@clip").find('[data-testid^="short-share-"]').click({ force: true });
    cy.get('[data-testid="shorts-feedback"]', { timeout: 10000 }).should("be.visible");

    cy.get("@clip").find('[data-testid^="short-comment-"]').click({ force: true });
    cy.get('[data-testid="short-comments-modal"]', { timeout: 10000 }).should("be.visible");
    cy.get('[data-testid="short-comments-input"]').type(commentText);
    cy.get('[data-testid="short-comments-submit"]').click();
    cy.contains(commentText, { timeout: 10000 }).should("be.visible");
    cy.get('[data-testid="short-comments-close"]').click();

    cy.get('[data-testid^="short-invest-"]').first().click({ force: true });
    cy.get('[data-testid="investment-modal"]', { timeout: 10000 }).should("be.visible");
    cy.get('[data-testid="investment-cash-amount"]').clear().type("25000");
    cy.get('[data-testid="investment-equity"]').clear().type("4.5");
    cy.get('[data-testid="investment-submit"]').click();
    cy.get('[data-testid="shorts-feedback"]', { timeout: 15000 }).should("contain.text", "Investment submitted.");
  });
});
