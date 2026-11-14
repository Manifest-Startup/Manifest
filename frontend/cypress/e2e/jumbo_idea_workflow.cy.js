describe('Jumbo Idea Workflow', () => {
  const ideaTitle = 'Cypress Jumbo Test Idea';
  const ideaDescription = '3D food printing startup concept';

  it('should create an idea and edit its content', () => {
    cy.loginAsDefaultUser();
    cy.get('[data-testid="new-idea-button"]', { timeout: 15000 }).should('be.visible').click();

    cy.url({ timeout: 15000 }).should('match', /\/ideas\/[^/]+\/description$/);
    cy.get('input[type="text"]', { timeout: 10000 }).first().clear().type(ideaTitle);
    cy.get('.ProseMirror[contenteditable="true"]', { timeout: 10000 }).first().clear().type(ideaDescription, { delay: 10 });

    cy.get('input[type="text"]').first().should('have.value', ideaTitle);
    cy.get('.ProseMirror[contenteditable="true"]').first().should('contain.text', ideaDescription);
    cy.contains(/All changes saved|Saving/i, { timeout: 10000 }).should('exist');
  });
});
