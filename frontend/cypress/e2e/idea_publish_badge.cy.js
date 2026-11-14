describe('Idea publish badge', () => {
  it('shows publish controls on the ideas list', () => {
    cy.loginAsDefaultUser();
    cy.get('[data-testid="idea-publish-badge"]', { timeout: 15000 }).should('have.length.at.least', 1);
    cy.get('[data-testid="idea-publish-badge"]').first().should('be.visible').and('have.class', 'rounded-full');
  });

  it('sends TogglePublishIdea when a draft badge is clicked', () => {
    cy.loginAsDefaultUser();

    cy.intercept('POST', '**/graphql', (req) => {
      if (req.body?.operationName === 'TogglePublishIdea') {
        req.reply({
          statusCode: 200,
          body: {
            data: {
              togglePublishIdea: {
                ideaId: req.body.variables.ideaId,
                isPublished: true,
              },
            },
          },
        });
      }
    }).as('togglePublishIdea');

    cy.get('button[aria-label*="Not published"]', { timeout: 15000 }).first().click();
    cy.wait('@togglePublishIdea');
  });
});
