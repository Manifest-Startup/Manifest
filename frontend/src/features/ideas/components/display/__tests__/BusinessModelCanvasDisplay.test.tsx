import React from 'react';
import { MockedProvider } from '@apollo/client/testing/react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { userVar } from 'features/core/apollo/localState';
import { GET_INTEGRATIONS } from 'features/core/apollo/queries';
import { BusinessModelCanvasDisplay } from '../BusinessModelCanvasDisplay';

const integrationsMock = {
  request: {
    query: GET_INTEGRATIONS,
  },
  result: {
    data: {
      integrations: [
        {
          integrationId: 'integration-1',
          userId: 'user-1',
          serviceName: 'Stripe',
          serviceId: 'stripe',
          connectedAt: '2026-04-17T00:00:00Z',
          metadata: null,
        },
        {
          integrationId: 'integration-2',
          userId: 'user-1',
          serviceName: 'Open Media',
          serviceId: 'open_media',
          connectedAt: '2026-04-17T00:00:00Z',
          metadata: null,
        },
        {
          integrationId: 'integration-3',
          userId: 'user-1',
          serviceName: 'Acme Logistics',
          serviceId: 'acme-logistics',
          connectedAt: '2026-04-17T00:00:00Z',
          metadata: null,
        },
      ],
    },
  },
};

describe('BusinessModelCanvasDisplay', () => {
  beforeEach(() => {
    userVar({
      isLoggedIn: true,
      isGuest: false,
      userData: { userId: 'user-1', email: 'founder@example.com' },
    });
  });

  afterEach(() => {
    act(() => {
      userVar({ isLoggedIn: false, isGuest: false, userData: null });
    });
  });

  it('renders key partner integration chips and hides the raw JSON block', async () => {
    render(
      <MockedProvider mocks={[integrationsMock]} addTypename={false}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <BusinessModelCanvasDisplay
            content={`# Key Partners
Stripe can support payments, while DocuSign can streamline signature-heavy onboarding.

\`\`\`bmc-key-partners-integrations
{"suggestedServiceIds":["stripe","docusign"]}
\`\`\`

# Channels
Direct outbound and founder communities.`}
            fallbackMessage="Fallback"
          />
        </MemoryRouter>
      </MockedProvider>,
    );

    expect(screen.queryByText(/suggestedServiceIds/i)).not.toBeInTheDocument();

    // Every connected partner is a key partner: catalogue services, Open Media
    // (messaging) and partners added by name.
    await waitFor(() => {
      expect(screen.getByRole('link', { name: /stripe: connected/i })).toHaveAttribute(
        'href',
        '/account?focusIntegration=stripe',
      );
    });
    expect(screen.getByRole('link', { name: /open media: connected/i })).toHaveAttribute('href', '/account');
    expect(screen.getByRole('link', { name: /acme logistics: connected/i })).toBeInTheDocument();

    // Suggestions only list partners not yet connected.
    expect(screen.getByText('Suggested')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /connect docusign/i })).toHaveAttribute(
      'href',
      '/account?focusIntegration=docusign',
    );
    expect(screen.queryByRole('link', { name: /connect stripe/i })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /add a partner/i })).toHaveAttribute(
      'href',
      '/account?focusIntegration=other',
    );
  });
});
