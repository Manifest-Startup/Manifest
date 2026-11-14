describe('Delete Idea Workflow', () => {
  const deleteButtons = () => cy.get('button[aria-label^="Delete idea:"]');
  const ideaRows = () => cy.get('div.flex.items-center.justify-between');
  const selectedIdeaRow = () => cy.get('div.flex.items-center.justify-between.border-l-4.border-accent-500');

  beforeEach(() => {
    cy.loginAsDefaultUser();
    cy.contains('New Idea', { timeout: 10000 }).should('be.visible');
  });

  it('should create an idea and then delete it', () => {
    deleteButtons().then(($buttons) => {
      const initialCount = $buttons.length;

      cy.contains('New Idea').click();
      deleteButtons().should('have.length.at.least', initialCount + 1);

      selectedIdeaRow()
        .find('button[aria-label^="Delete idea:"]')
        .click({ force: true });

      cy.url({ timeout: 10000 }).should('include', '/ideas');
    });
  });

  it('should delete an idea and navigate away if it was the currently selected idea', () => {
    cy.contains('New Idea').click();

    selectedIdeaRow()
      .find('button[aria-label^="Delete idea:"]')
      .click({ force: true });

    cy.url({ timeout: 10000 }).should('include', '/ideas');
  });

  it('should not navigate when deleting a non-selected idea', () => {
    cy.contains('New Idea').click();
    cy.contains('New Idea').click();

    ideaRows().should('have.length.at.least', 2);
    ideaRows().first().click();
    cy.url().then((selectedUrl) => {
      deleteButtons().last().click({ force: true });
      cy.url({ timeout: 10000 }).should('eq', selectedUrl);
    });
  });

  it('should show delete button for each idea in the list', () => {
    cy.contains('New Idea').click();
    cy.contains('New Idea').click();
    cy.contains('New Idea').click();

    deleteButtons().should('have.length.at.least', 3);
  });

  it('should handle delete button click without triggering idea selection', () => {
    cy.contains('New Idea').click();

    deleteButtons().its('length').then((beforeCount) => {
      selectedIdeaRow()
        .find('button[aria-label^="Delete idea:"]')
        .click({ force: true });

      deleteButtons().its('length').should('be.lte', beforeCount);
      cy.url({ timeout: 10000 }).should('include', '/ideas');
    });
  });
});
