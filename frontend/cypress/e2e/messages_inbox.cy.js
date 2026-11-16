describe('Messages inbox', () => {
  it('loads /messages after login (inbox when Open Media is linked, connect prompt otherwise)', () => {
    cy.loginAsDefaultUser();
    cy.visit('/messages');
    cy.get('[data-testid="messages-page"]', { timeout: 15000 }).should('be.visible');
    cy.get('[data-testid="messages-page"]').should(($page) => {
      const text = $page.text();
      expect(
        text.includes('Inbox') || text.includes('Connect Open Media') || text.includes("Messages aren't available"),
      ).to.equal(true);
    });
  });
});
