// Plain list of integration service ids, kept apart from integrationsCatalog
// so callers that only need to recognise an id (the Business Model Canvas
// view) don't pull the catalogue's icon set into their bundle.
// integrationServiceIds.test.ts keeps this list in sync with the catalogue.
export const integrationServiceIds = [
  'google',
  'apple',
  'microsoft',
  'notion',
  'slack',
  'asana',
  'trello',
  'jira',
  'monday',
  'clickup',
  'meta',
  'linkedin',
  'x',
  'reddit',
  'zapier',
  'n8n',
  'make',
  'figma',
  'canva',
  'adobe',
  'openai',
  'github',
  'gitlab',
  'bitbucket',
  'vercel',
  'stripe',
  'quickbooks',
  'xero',
  'google-analytics',
  'hubspot',
  'mailchimp',
  'salesforce',
  'dropbox',
  'box',
  'docusign',
  'hellosign',
  'intercom',
  'zendesk',
  'shopify',
  'woocommerce',
] as const;

export type IntegrationServiceId = (typeof integrationServiceIds)[number];

export const knownIntegrationServiceIds: ReadonlySet<string> = new Set(integrationServiceIds);
