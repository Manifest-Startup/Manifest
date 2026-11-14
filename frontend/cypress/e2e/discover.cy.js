describe('Discover Page', () => {
  beforeEach(() => {
    cy.loginAsDefaultUser();
    cy.visit('/discover');
    cy.url({ timeout: 10000 }).should('include', '/shorts');
    cy.get('[data-testid="shorts-page"]', { timeout: 15000 }).should('be.visible');
  });

  it('redirects to the Pitch Reels experience', () => {
    cy.contains('Pitch Reels').should('be.visible');
  });

  it('exits loading into reels, an empty state, or a retryable error', () => {
    cy.contains(/Loading pitch reels/i, { timeout: 15000 }).should('not.exist');
    cy.contains(/No pitch reels yet|Retry|Open workspace|Invest/i, { timeout: 15000 }).should('exist');
  });

  it('hides global voice chrome in immersive reels', () => {
    cy.get('[data-testid="voice-launcher"]').should('not.exist');
  });
});
