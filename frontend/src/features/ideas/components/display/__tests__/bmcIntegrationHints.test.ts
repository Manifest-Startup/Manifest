import {
  parseBusinessModelCanvasSections,
  parseKeyPartnersIntegrationHints,
} from '../bmcIntegrationHints';

describe('bmcIntegrationHints', () => {
  it('strips the machine-readable key partners block and keeps only known integration ids', () => {
    const parsed = parseKeyPartnersIntegrationHints(`Strategic partners include payment processors and e-sign vendors.

\`\`\`bmc-key-partners-integrations
{"suggestedServiceIds":["stripe","unknown-tool","docusign","STRIPE"]}
\`\`\``);

    expect(parsed.content).toContain('Strategic partners include payment processors');
    expect(parsed.content).not.toContain('suggestedServiceIds');
    expect(parsed.suggestedServiceIds).toEqual(['stripe', 'docusign']);
  });

  it('parses key partners hints while leaving other BMC sections untouched', () => {
    const sections = parseBusinessModelCanvasSections(`# Key Partners
Legal workflows, payments, and collaboration all matter here.

\`\`\`bmc-key-partners-integrations
{"suggestedServiceIds":["slack","github"]}
\`\`\`

# Channels
- Founder communities
- Outbound email`);

    expect(sections).toEqual([
      {
        title: 'Key Partners',
        content: 'Legal workflows, payments, and collaboration all matter here.',
        suggestedServiceIds: ['slack', 'github'],
      },
      {
        title: 'Channels',
        content: '- Founder communities\n- Outbound email',
        suggestedServiceIds: [],
      },
    ]);
  });
});
