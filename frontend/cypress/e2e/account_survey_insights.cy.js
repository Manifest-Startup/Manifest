describe('Account Survey Insights', () => {
  beforeEach(() => {
    cy.loginAsDefaultUser();
  });

  it('shows the survey insight snapshot on the account settings surface', () => {
    cy.intercept('POST', '/graphql', (req) => {
      if (req.body?.query?.includes('surveyInsights')) {
        req.reply({
          data: {
            surveyInsights: {
              generatedAt: '2026-04-05T12:00:00Z',
              windowDays: 90,
              totalResponses: 22,
              researchResponses: 14,
              productFeedbackResponses: 8,
              researchSignupIntentAvg: 4.1,
              researchFollowUpRate: 42.9,
              productPmfVeryDisappointedPct: 37.5,
              productNpsScore: 18,
              productProgressAvg: 3.7,
              productDeliverableAvg: 3.9,
              productAiQualityAvg: 4.2,
              topResearchValueProps: [{ label: 'Investor- or share-ready outputs without starting from scratch', count: 6, percentage: 42.9 }],
              topResearchBarriers: [{ label: 'Doing market research or finding comparable companies', count: 5, percentage: 35.7 }],
              topResearchFirstOutputs: [{ label: 'A market / comparable research brief', count: 7, percentage: 50 }],
              topResearchTrustSignals: [{ label: 'Citations or links behind claims and research', count: 6, percentage: 42.9 }],
              topProductBenefits: [{ label: 'It gives shape to rough ideas faster', count: 4, percentage: 50 }],
              topProductTasks: [{ label: 'Generate or refine documents (deck, PRD, canvas, patent, etc.)', count: 5, percentage: 62.5 }],
              topActionThemes: [{ theme: 'Research credibility', count: 4 }],
            },
          },
        });
      }
    }).as('surveyInsights');

    cy.visit('/account');
    cy.contains('button', 'Settings', { timeout: 10000 }).click();
    cy.wait('@surveyInsights');
    cy.get('[data-testid="survey-insights-panel"]', { timeout: 10000 }).should('be.visible');
    cy.contains('Survey insights').should('be.visible');
    cy.contains('Marketability').should('be.visible');
    cy.contains('Research credibility (4)').should('be.visible');
  });
});
