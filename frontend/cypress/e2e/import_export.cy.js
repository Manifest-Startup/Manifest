describe('Import/Export Ideas', () => {
  const openImportExportModal = () => {
    cy.get('[aria-label="Toggle Profile Dropdown Menu"]', { timeout: 15000 }).click();
    cy.contains('button', /^Account$/, { timeout: 10000 }).click({ force: true });
    cy.url({ timeout: 10000 }).should('include', '/account');
    cy.get('body').then(($body) => {
      if ($body.find('button:contains("Settings")').length > 0) {
        cy.contains('button', 'Settings').click({ force: true });
      }
    });
    cy.get('[data-testid="import-export-button"]', { timeout: 15000 }).scrollIntoView().click({ force: true });
    cy.contains('Import & Export Ideas', { timeout: 10000 }).should('be.visible');
  };

  const mockExportMutation = (expectedFormat) => {
    cy.intercept('POST', '**/graphql', (req) => {
      if (req.body?.operationName === 'ExportIdeas' && req.body.variables?.format === expectedFormat) {
        req.reply({
          statusCode: 200,
          body: {
            data: {
              exportIdeas: {
                content: 'dGVzdA==',
                format: expectedFormat,
                filename: `ideas_export.${expectedFormat === 'markdown' ? 'md' : expectedFormat}`,
              },
            },
          },
        });
      }
    }).as(`export${expectedFormat}`);
  };

  const mockImportMutation = () => {
    cy.intercept('POST', '**/graphql', (req) => {
      if (req.body?.operationName === 'ImportIdeas') {
        req.reply({
          statusCode: 200,
          body: {
            data: {
              importIdeas: {
                importedCount: 2,
                skippedCount: 0,
                errors: [],
              },
            },
          },
        });
      }
    }).as('importIdeas');
  };

  beforeEach(() => {
    cy.loginAsDefaultUser();
  });

  it('should navigate to account settings and open import/export modal', () => {
    openImportExportModal();
    cy.contains('Export').should('be.visible');
    cy.contains('Import').should('be.visible');
  });

  it('should export ideas as JSON', () => {
    mockExportMutation('json');
    openImportExportModal();
    cy.get('input[name="exportFormat"][value="json"]').check({ force: true });
    cy.contains('button', /^Export Ideas$/).click({ force: true });
    cy.wait('@exportjson');
    cy.contains('Successfully exported ideas as JSON').should('be.visible');
  });

  it('should export ideas as CSV', () => {
    mockExportMutation('csv');
    openImportExportModal();
    cy.get('input[name="exportFormat"][value="csv"]').check({ force: true });
    cy.contains('button', /^Export Ideas$/).click({ force: true });
    cy.wait('@exportcsv');
    cy.contains('Successfully exported ideas as CSV').should('be.visible');
  });

  it('should export ideas as Markdown', () => {
    mockExportMutation('markdown');
    openImportExportModal();
    cy.get('input[name="exportFormat"][value="markdown"]').check({ force: true });
    cy.contains('button', /^Export Ideas$/).click({ force: true });
    cy.wait('@exportmarkdown');
    cy.contains('Successfully exported ideas as MARKDOWN').should('be.visible');
  });

  it('should switch between import and export tabs', () => {
    openImportExportModal();
    cy.contains('Export Format').should('be.visible');
    cy.contains('button', /^Import$/).click();
    cy.contains('Import ideas from JSON, CSV, Markdown, or Google Keep (ZIP)').should('be.visible');
    cy.contains('button', /^Export$/).click();
    cy.contains('Export Format').should('be.visible');
  });

  it('should import ideas from JSON file', () => {
    mockImportMutation();
    openImportExportModal();
    cy.contains('button', /^Import$/).click();

    const ideasJson = JSON.stringify({
      ideas: [
        { title: 'Imported Test Idea 1', description: 'Imported from Cypress' },
        { title: 'Imported Test Idea 2', description: 'Another imported idea' },
      ],
    });

    cy.get('input[type="file"][accept=".json,.csv,.md,.markdown,.zip"]').selectFile(
      {
        contents: Cypress.Buffer.from(ideasJson),
        fileName: 'test_ideas.json',
        mimeType: 'application/json',
      },
      { force: true }
    );

    cy.contains('test_ideas.json').should('be.visible');
    cy.contains('button', /^Import Ideas$/).click({ force: true });
    cy.wait('@importIdeas');
    cy.contains('Successfully imported 2 idea(s)').should('be.visible');
  });

  it('should reject invalid file types', () => {
    openImportExportModal();
    cy.contains('button', /^Import$/).click();

    cy.get('input[type="file"][accept=".json,.csv,.md,.markdown,.zip"]').selectFile(
      {
        contents: Cypress.Buffer.from('plain text'),
        fileName: 'test.txt',
        mimeType: 'text/plain',
      },
      { force: true }
    );

    cy.contains('test.txt').should('not.exist');
    cy.contains('button', /^Import Ideas$/).should('be.disabled');
  });

  it('should show Google Keep instructions', () => {
    openImportExportModal();
    cy.contains('button', /^Import$/).click();
    cy.contains('Import from Google Keep').should('exist');
    cy.contains('Google Takeout').should('exist');
  });

  it('should close modal when cancel is clicked', () => {
    openImportExportModal();
    cy.contains('button', 'Cancel').click();
    cy.contains('Import & Export Ideas').should('not.exist');
  });

  it('should close modal when X button is clicked', () => {
    openImportExportModal();
    cy.get('button[aria-label="Close"]').click();
    cy.contains('Import & Export Ideas').should('not.exist');
  });

  it('should handle file removal in import tab', () => {
    openImportExportModal();
    cy.contains('button', /^Import$/).click();

    cy.get('input[type="file"][accept=".json,.csv,.md,.markdown,.zip"]').selectFile(
      {
        contents: Cypress.Buffer.from(JSON.stringify({ ideas: [] })),
        fileName: 'test.json',
        mimeType: 'application/json',
      },
      { force: true }
    );

    cy.contains('test.json').should('be.visible');
    cy.contains('button', 'Remove file').click();
    cy.contains('test.json').should('not.exist');
    cy.contains('Drag and drop a file here').should('exist');
  });
});
