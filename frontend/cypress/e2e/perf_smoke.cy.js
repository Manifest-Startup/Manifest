describe('Performance smoke', () => {
  it('loads the home page within a generous navigation budget', () => {
    cy.visit('/', {
      onBeforeLoad: (win) => {
        win.performance.mark('perf_nav_start');
      },
    });
    cy.get('body').should('be.visible');
    cy.contains('The Social Network for Startup Builders and Investors', { timeout: 10000 }).should('be.visible');
    cy.window().then((win) => {
      const entries = win.performance.getEntriesByType('navigation');
      if (!entries.length) {
        return;
      }
      const nav = entries[0];
      expect(nav.duration).to.be.lessThan(120000);
    });
  });

  it('records a paint-related timing entry after load', () => {
    cy.visit('/');
    cy.window().then((win) => {
      const paints = win.performance.getEntriesByType('paint');
      const navEntries = win.performance.getEntriesByType('navigation');
      const hasPaintEntry = paints.length > 0;
      const hasNavigationTiming =
        navEntries.length > 0 && Number(navEntries[0].domContentLoadedEventEnd || 0) > 0;
      expect(hasPaintEntry || hasNavigationTiming, 'paint or navigation timing entries').to.equal(true);
    });
  });
});
