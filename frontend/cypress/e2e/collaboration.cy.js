describe('Collaboration Features', () => {
  const loginAndOpenIdea = () => {
    cy.loginAsDefaultUser();
    cy.get('body').then(($body) => {
      if ($body.find('[data-testid=\"share-button\"]').length === 0) {
        cy.contains('New Idea', { timeout: 10000 }).should('be.visible').click();
      }
    });
    cy.get('[data-testid="share-button"]', { timeout: 15000 }).should('be.visible');
    cy.get('[data-testid="version-button"]', { timeout: 15000 }).should('be.visible');
  };

  beforeEach(() => {
    loginAndOpenIdea();
  });

  describe('Share Button', () => {
    it('should display share button on idea page when logged in', () => {
      cy.get('[data-testid="share-button"]', { timeout: 10000 }).should('exist');
    });
  });

  describe('Version History Button', () => {
    it('should display version history button on idea page when logged in', () => {
      cy.get('[data-testid="version-button"]', { timeout: 10000 }).should('exist');
    });
  });

  describe('Share Modal', () => {
    it('should open share modal when share button is clicked', () => {
      cy.get('[data-testid="share-button"]').click();
      cy.contains('Share Idea').should('be.visible');
    });

    it('should have email input field in share modal', () => {
      cy.get('[data-testid="share-button"]').click();
      cy.get('input[type="email"]').should('exist');
    });

    it('should have role selector in share modal', () => {
      cy.get('[data-testid="share-button"]').click();
      cy.get('select').should('exist');
      cy.get('option').should('have.length.at.least', 3);
    });

    it('should close share modal when X is clicked', () => {
      cy.get('[data-testid="share-button"]').click();
      cy.contains('Share Idea').should('be.visible');
      cy.get('[data-testid="close-modal"]').click();
      cy.contains('Share Idea').should('not.exist');
    });
  });

  describe('Version History Modal', () => {
    it('should open version history modal when version button is clicked', () => {
      cy.get('[data-testid="version-button"]').click();
      cy.contains('Version History').should('be.visible');
    });

    it('should have save version button', () => {
      cy.get('[data-testid="version-button"]').click();
      cy.contains('Save Version').should('exist');
    });

    it('should have version note input', () => {
      cy.get('[data-testid="version-button"]').click();
      cy.get('input[placeholder*="Version note"]').should('exist');
    });

    it('should close version history modal when X is clicked', () => {
      cy.get('[data-testid="version-button"]').click();
      cy.contains('Version History').should('be.visible');
      cy.get('[data-testid="close-modal"]').click();
      cy.contains('Version History').should('not.exist');
    });
  });

  describe('Access Control', () => {
    it('should show access section in share modal', () => {
      cy.get('[data-testid="share-button"]').click();
      cy.contains('People with access').should('be.visible');
    });
  });

  describe('Role Options', () => {
    it('should have viewer, commenter, and editor roles available', () => {
      cy.get('[data-testid="share-button"]').click();
      cy.get('select option').should('contain', 'Viewer');
      cy.get('select option').should('contain', 'Commenter');
      cy.get('select option').should('contain', 'Editor');
    });
  });
});
