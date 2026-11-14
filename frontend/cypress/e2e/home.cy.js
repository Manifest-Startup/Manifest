describe('Manifest Home Page', () => {
  it('shows the hero section with buttons', () => {
    cy.visit('/');
    // Wait for page to load
    cy.get('body').should('be.visible');
    cy.contains('Turn your idea into a plan.', { timeout: 10000 }).should('be.visible');
    cy.contains('Explore the demo').should('exist');
    cy.contains('How it works').should('exist');
  });

  it('login', function() {
    cy.clearCookies();
    cy.clearLocalStorage();
    cy.visit('/');
    // Wait for page to load
    cy.get('body').should('be.visible');
    // Click the "Sign In" button in the top right
    cy.contains('Sign in', { timeout: 10000 }).click();
    // Wait for login form to appear
    cy.get('[type="email"]', { timeout: 5000 }).should('be.visible');
    // Fill in email and password
    cy.get('[type="email"]').clear().type('hello@manifeststartup.com');
    cy.get('[type="password"]').clear().type('Mnfst_E2e_CI_9x!');
    // Click the "Login" button
    cy.get('button[type="submit"]').click();
    // Wait for navigation and assert that the 'New Idea' button is visible after login
    cy.url({ timeout: 10000 }).should('include', '/ideas');
    cy.get('[data-testid="new-idea-button"]', { timeout: 15000 }).should('be.visible');
  });
});
