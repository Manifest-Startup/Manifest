import React, { useState } from 'react';
import { useMutation, useQuery } from '@apollo/client/react';
import {
  DISCONNECT_INTEGRATION,
  GET_INTEGRATIONS,
  START_INTEGRATION_CONNECTION,
} from 'features/core/apollo/queries';
import { useMessage } from 'features/notifications/context/MessageContext';
import { knownIntegrationServiceIds } from 'features/account/lib/integrationServiceIds';

/** A partner's name as a service id: "Acme Logistics" -> "acme-logistics". */
export const partnerServiceId = (name: string) =>
  name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40);

/**
 * Any company can be a key partner, not only the services in the catalogue:
 * add it by name here (agents use startIntegrationConnection the same way).
 */
const OtherPartners: React.FC<{ autoFocus?: boolean }> = ({ autoFocus = false }) => {
  const [name, setName] = useState('');
  const { setMessage } = useMessage();
  const { data } = useQuery(GET_INTEGRATIONS);
  const [startConnection, { loading }] = useMutation(START_INTEGRATION_CONNECTION, {
    refetchQueries: [{ query: GET_INTEGRATIONS }],
  });
  const [disconnect] = useMutation(DISCONNECT_INTEGRATION, {
    refetchQueries: [{ query: GET_INTEGRATIONS }],
  });

  const others = (data?.integrations ?? []).filter(
    (integration) => !knownIntegrationServiceIds.has(integration.serviceId),
  );

  const handleAdd = async (event: React.FormEvent) => {
    event.preventDefault();
    const serviceId = partnerServiceId(name);
    if (!serviceId) {
      return;
    }
    if (knownIntegrationServiceIds.has(serviceId)) {
      setMessage(`${name.trim()} is in the list above: use its Connect button.`, 'info');
      return;
    }
    try {
      const result = await startConnection({ variables: { serviceId, name: name.trim() } });
      const outcome = result.data?.startIntegrationConnection;
      if (outcome?.connectUrl) {
        window.location.assign(outcome.connectUrl);
        return;
      }
      setMessage(outcome?.message ?? `${name.trim()} added.`, 'success');
      setName('');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not add that partner.', 'error');
    }
  };

  return (
    <div className="mb-6">
      <h3 className="mb-1 text-sm font-semibold text-theme-primary">Other partners</h3>
      <p className="mb-3 text-sm text-theme-secondary">
        Suppliers, agencies, distributors: anyone you work with. They show under Key Partners on your canvases.
      </p>
      {others.length > 0 && (
        <ul className="mb-3 flex flex-wrap gap-2" aria-label="Other partners">
          {others.map((partner) => (
            <li
              key={partner.serviceId}
              className="inline-flex items-center gap-2 rounded-full bg-stone-100 py-1 pl-3 pr-1 text-sm dark:bg-neutral800"
            >
              <span className="font-medium text-theme-primary">{partner.serviceName}</span>
              <button
                type="button"
                className="rounded-full px-2 py-0.5 text-xs text-theme-secondary hover:bg-stone-200 dark:hover:bg-neutral700"
                aria-label={`Remove ${partner.serviceName}`}
                onClick={() => disconnect({ variables: { serviceId: partner.serviceId } })}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <form className="flex gap-2" onSubmit={handleAdd}>
        <input
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Add a partner, e.g. Acme Logistics"
          aria-label="Partner name"
          maxLength={80}
          autoFocus={autoFocus}
          className="manifest-field"
        />
        <button
          type="submit"
          disabled={loading || !partnerServiceId(name)}
          className="manifest-control manifest-control-primary shrink-0 px-4"
        >
          Add
        </button>
      </form>
    </div>
  );
};

export default OtherPartners;
