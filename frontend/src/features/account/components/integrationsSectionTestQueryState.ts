/**
 * Shared mutable state for IntegrationsSection.test useQuery mock.
 * Jest mock factories may only `require` this module (no outer-scope refs).
 * Lives outside __tests__ so Jest does not treat it as a test file.
 */
type IntegrationRow = {
  integrationId: string;
  userId: string;
  serviceName: string;
  serviceId: string;
  connectedAt: string;
  metadata: null;
};

export const refetchMock = jest.fn();

export const queryState: {
  loading: boolean;
  /** When loading, component ignores data; null means no integrations. */
  data: { integrations: IntegrationRow[] } | null;
} = { loading: false, data: { integrations: [] } };

export const resetQueryState = () => {
  queryState.loading = false;
  queryState.data = { integrations: [] };
};
