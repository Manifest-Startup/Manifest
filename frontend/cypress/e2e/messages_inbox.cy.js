describe('Messages inbox', () => {
  it('loads the inbox at /messages after login', () => {
    cy.loginAsDefaultUser();
    cy.visit('/messages');
    cy.get('[data-testid="messages-page"]', { timeout: 15000 }).should('be.visible');
    cy.contains('Inbox').should('be.visible');
  });
});
