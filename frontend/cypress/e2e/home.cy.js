describe('Manifest Home Page', () => {
  it('shows the hero section with buttons', () => {
    cy.visit('/');
    // Wait for page to load
    cy.get('body').should('be.visible');
    cy.contains('Turn your idea into a plan.', { timeout: 10000 }).should('be.visible');
    cy.contains('Explore the demo').should('exist');
    cy.contains('How it works').should('exist');
  });

  it('shows the Open Media login page and signs in', function() {
    cy.clearCookies();
    cy.clearLocalStorage();
    cy.visit('/');
    cy.get('body').should('be.visible');
    cy.contains('Sign in', { timeout: 10000 }).click();
    cy.url().should('include', '/login');
    cy.contains('One account for Manifest and Open Media.').should('be.visible');
    cy.get('[data-testid="try-without-account"]').should('be.visible');
    cy.get('input[type="password"]').should('not.exist');
    // Old links land on the login page.
    cy.visit('/auth/forgot-password');
    cy.url().should('include', '/login');
    // Demo-mode stacks sign in the demo user; real stacks go through Open Media.
    cy.signInWithOpenMedia();
    cy.get('[data-testid="new-idea-button"]', { timeout: 15000 }).should('be.visible');
  });
});
