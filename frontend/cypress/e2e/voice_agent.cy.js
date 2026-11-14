describe('Voice Agent E2E Tests', () => {
  beforeEach(() => {
    cy.loginAsDefaultUser();
  });

  it('should display the floating voice button on ideas page', () => {
    cy.get('button[aria-label*="voice"]', { timeout: 10000 }).should('be.visible');
  });

  it('should open and close the voice modal', () => {
    cy.get('button[aria-label*="voice"]').click();
    cy.contains('Manifest Voice').should('be.visible');
    cy.get('button[aria-label="Close"]').click();
    cy.get('button[aria-label*="voice"]').should('be.visible');
  });

  it('should show greeting, status, and action button in modal', () => {
    cy.get('button[aria-label*="voice"]').click();
    cy.contains('.fixed.inset-0', /startup idea|problem worth solving|current idea context/i).should('be.visible');
    cy.contains(/Ready|Listening|Speaking|Thinking/i).should('be.visible');
    cy.contains('button', /Tap to Speak|Tap to Stop/i).should('be.visible');
  });

  it('should display on discover page for logged in users', () => {
    cy.visit('/discover');
    cy.get('button[aria-label*="voice"]').should('be.visible');
  });

  it('should display on account page for logged in users', () => {
    cy.visit('/account');
    cy.get('button[aria-label*="voice"]').should('be.visible');
  });
});
