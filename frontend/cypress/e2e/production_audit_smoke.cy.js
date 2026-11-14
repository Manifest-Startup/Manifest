describe('Production audit smoke', () => {
  beforeEach(() => {
    cy.loginAsDefaultUser();
  });

  it('renders the authenticated ideas workspace with a create path', () => {
    cy.url({ timeout: 15000 }).should('include', '/ideas');
    cy.get('[data-testid="ideas-list"]', { timeout: 15000 }).should('be.visible');
    cy.get('[data-testid="new-idea-button"]').should('be.visible');
    cy.get('[data-testid="ideas-loading-state"]').should('not.exist');
  });

  it('loads account settings and exposes import/export controls', () => {
    cy.visit('/account');
    cy.contains(/Loading account workspace/i, { timeout: 15000 }).should('not.exist');
    cy.contains('button', /^Settings$/).click({ force: true });
    cy.get('[data-testid="import-export-button"]', { timeout: 15000 }).scrollIntoView().should('be.visible');
  });

  it('exits pitch reels loading into a user-actionable state', () => {
    cy.visit('/shorts');
    cy.get('[data-testid="shorts-page"]', { timeout: 15000 }).should('be.visible');
    cy.contains(/Loading pitch reels/i, { timeout: 15000 }).should('not.exist');
    cy.contains(/No pitch reels yet|Retry|Open workspace|Invest/i, { timeout: 15000 }).should('exist');
  });

  it('keeps voice launcher behavior consistent by route', () => {
    cy.visit('/ideas');
    cy.get('[data-testid="voice-launcher"]', { timeout: 15000 }).should('be.visible');
    cy.visit('/account');
    cy.get('[data-testid="voice-launcher"]', { timeout: 15000 }).should('be.visible');
    cy.visit('/shorts');
    cy.get('[data-testid="voice-launcher"]').should('not.exist');
  });
});
