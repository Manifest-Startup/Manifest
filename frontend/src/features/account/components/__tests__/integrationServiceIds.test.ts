import { integrationCatalog } from 'features/account/lib/integrationsCatalog';
import { integrationServiceIds, knownIntegrationServiceIds } from 'features/account/lib/integrationServiceIds';

describe('integrationServiceIds', () => {
  it('matches the integration catalogue exactly', () => {
    expect([...integrationServiceIds].sort()).toEqual(integrationCatalog.map((entry) => entry.id).sort());
  });

  it('recognises catalogue ids only', () => {
    expect(knownIntegrationServiceIds.has('notion')).toBe(true);
    expect(knownIntegrationServiceIds.has('not-a-service')).toBe(false);
  });
});
