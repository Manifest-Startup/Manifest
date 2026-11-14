describe('Floating Voice Button E2E Tests', () => {
  beforeEach(() => {
    cy.loginAsDefaultUser();
  });

  describe('Button Visibility', () => {
    it('should display floating button on Ideas page', () => {
      cy.get('[data-testid="voice-launcher"]').should('be.visible');
    });

    it('should hide floating button on immersive Pitch Reels', () => {
      cy.visit('/discover');
      cy.url({ timeout: 10000 }).should('include', '/shorts');
      cy.get('[data-testid="voice-launcher"]').should('not.exist');
    });

    it('should display floating button on Account page', () => {
      cy.visit('/account');
      cy.get('[data-testid="voice-launcher"]').should('be.visible');
    });

    it('should be positioned in bottom-right corner', () => {
      cy.get('[data-testid="voice-launcher"]').should('have.class', 'fixed');
      cy.get('[data-testid="voice-launcher"]').should('have.class', 'bottom-6');
      cy.get('[data-testid="voice-launcher"]').should('have.class', 'right-6');
    });
  });

  describe('Modal Interaction', () => {
    it('should open modal when button clicked', () => {
      cy.get('[data-testid="voice-launcher"]').click();
      cy.contains('Manifest Voice').should('be.visible');
    });

    it('should show greeting message in modal', () => {
      cy.get('[data-testid="voice-launcher"]').click();
      cy.contains('.fixed.inset-0', /startup idea|problem worth solving|current idea context/i).should('be.visible');
    });

    it('should show status indicator', () => {
      cy.get('[data-testid="voice-launcher"]').click();
      cy.contains(/Ready|Listening|Speaking|Thinking/i).should('be.visible');
    });

    it('should close modal when close button clicked', () => {
      cy.get('[data-testid="voice-launcher"]').click();
      cy.contains('Manifest Voice').should('be.visible');
      cy.get('button[aria-label="Close voice mode"]').click();
      cy.get('[data-testid="voice-launcher"]').should('be.visible');
    });
  });

  describe('Design Standards', () => {
    it('should use the voice launcher styling hook', () => {
      cy.get('[data-testid="voice-launcher"]').should('have.class', 'voice-launcher');
    });

    it('should be circular', () => {
      cy.get('[data-testid="voice-launcher"]').should('have.class', 'rounded-full');
    });

    it('should have shadow for depth', () => {
      cy.get('[data-testid="voice-launcher"]').should('have.class', 'shadow-[0_28px_64px_-28px_rgba(8,12,28,0.75),0_18px_44px_-24px_rgba(96,140,255,0.45),inset_0_1px_0_rgba(255,255,255,0.22)]');
    });

    it('should have hover effect', () => {
      cy.get('[data-testid="voice-launcher"]').should('have.class', 'hover:-translate-y-0.5');
    });
  });

  describe('Responsive Design', () => {
    it('should display correctly on mobile', () => {
      cy.viewport('iphone-x');
      cy.get('[data-testid="voice-launcher"]').should('be.visible');
    });

    it('should display correctly on tablet', () => {
      cy.viewport('ipad-2');
      cy.get('[data-testid="voice-launcher"]').should('be.visible');
    });

    it('should display modal properly on mobile', () => {
      cy.viewport('iphone-x');
      cy.get('[data-testid="voice-launcher"]').click();
      cy.contains('Manifest Voice').should('be.visible');
    });
  });
});

describe('Verified Badge E2E Tests', () => {
  beforeEach(() => {
    cy.loginAsDefaultUser();
  });

  describe('Badge Display', () => {
    it('should display verified badges next to ideas', () => {
      cy.get('button[aria-label*="Published"], button[aria-label*="Not published"]').should('exist');
    });

    it('should be circular like X/Instagram badges', () => {
      cy.get('button[aria-label*="Published"], button[aria-label*="Not published"]')
        .first()
        .should('have.class', 'rounded-full');
    });
  });

  describe('Badge Interaction', () => {
    it('should toggle publish status when clicked', () => {
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

      cy.get('button[aria-label*="Not published"]').first().as('badge');
      cy.get('@badge').click();
      cy.wait('@togglePublishIdea');
      cy.get('@badge').should('exist');
    });
  });
});
