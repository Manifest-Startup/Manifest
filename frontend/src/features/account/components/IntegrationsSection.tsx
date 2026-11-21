import React, { useEffect, useRef, useState } from 'react';
import { useQuery, useMutation } from '@apollo/client/react';
import { useSearchParams } from 'react-router-dom';
import { useMessage } from 'features/notifications/context/MessageContext';
import { trackEvent } from 'features/analytics/projectAnalytics';
import {
  GET_INTEGRATIONS,
  CONNECT_INTEGRATION,
  DISCONNECT_INTEGRATION,
  START_INTEGRATION_CONNECTION,
} from 'features/core/apollo/queries';
import OtherPartners from './OtherPartners';
import { 
  HiSearch,
  HiOutlineCheckCircle,
  HiXCircle
} from 'react-icons/hi';
import {
  getIntegrationCatalogEntry,
  integrationCatalog,
  integrationCategories,
  type IntegrationAvailability,
  type IntegrationCatalogEntry,
} from 'features/account/lib/integrationsCatalog';

// Placeholder icon component for missing icons
const PlaceholderIcon: React.FC<{ className?: string; letter: string }> = ({ className, letter }) => (
  <span className={className} style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>
    {letter}
  </span>
);

// Wrapper components for react-icons v5 compatibility
const CheckIcon: React.FC<{ className?: string }> = ({ className }) => {
  // eslint-disable-next-line @typescript-eslint/ban-ts-comment
  // @ts-ignore - react-icons v5 type compatibility
  return <HiOutlineCheckCircle className={className} />;
};

const SearchIcon: React.FC<{ className?: string }> = ({ className }) => {
  // eslint-disable-next-line @typescript-eslint/ban-ts-comment
  // @ts-ignore - react-icons v5 type compatibility
  return <HiSearch className={className} />;
};

const XIcon: React.FC<{ className?: string }> = ({ className }) => {
  // eslint-disable-next-line @typescript-eslint/ban-ts-comment
  // @ts-ignore - react-icons v5 type compatibility
  return <HiXCircle className={className} />;
};

interface Integration {
  id: IntegrationCatalogEntry['id'];
  name: IntegrationCatalogEntry['name'];
  description: IntegrationCatalogEntry['description'];
  icon: IntegrationCatalogEntry['icon'];
  category: IntegrationCatalogEntry['category'];
  connected: boolean;
  /** Connected through the partner's own sign-in (vs. added as a partner by name). */
  linked: boolean;
  brandColor: IntegrationCatalogEntry['brandColor'];
  availability: IntegrationAvailability;
}


interface IntegrationCardProps {
  integration: Integration;
  onToggle: (id: string, connected: boolean) => void;
  isConnecting?: boolean;
}

const IntegrationCard: React.FC<IntegrationCardProps> = ({ 
  integration, 
  onToggle,
  isConnecting = false 
}) => {
  const IconComponent = integration.icon;
  
  return (
    <div className="manifest-card group relative flex h-full min-w-0 items-center gap-3 px-3.5 py-3">
      <div
        className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg text-white"
        style={{ backgroundColor: integration.brandColor }}
      >
        {IconComponent ? (
          React.createElement(IconComponent as React.ComponentType<{ className?: string }>, {
            className: "w-5 h-5",
          })
        ) : (
          <PlaceholderIcon className="text-base font-bold" letter={integration.name.charAt(0)} />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-1.5">
          <h4 className="truncate text-sm font-semibold text-theme-primary">{integration.name}</h4>
          {integration.connected && (
            <span className="inline-flex shrink-0 items-center gap-0.5 text-xs font-medium text-green-700 dark:text-green-400">
              <CheckIcon className="h-3.5 w-3.5" />
              {integration.linked ? 'Linked' : 'Added as partner'}
            </span>
          )}
        </div>
        <p className="mt-0.5 line-clamp-2 text-xs leading-5 text-theme-secondary">{integration.description}</p>
      </div>

      {integration.availability === 'coming_soon' && !integration.connected ? (
        <span
          className="shrink-0 rounded-full border border-dashed border-theme-primary px-2.5 py-1 text-xs font-medium text-theme-secondary select-none"
          aria-label={`${integration.name} integration coming soon`}
          data-testid={`integration-coming-soon-${integration.id}`}
        >
          Coming soon
        </span>
      ) : (
        <button
          onClick={() => onToggle(integration.id, integration.connected)}
          disabled={isConnecting}
          aria-label={`${integration.connected ? 'Disconnect' : 'Connect'} ${integration.name}`}
          className="manifest-control manifest-control-secondary shrink-0 !min-h-[32px] rounded-full !px-3 !py-1 text-xs font-semibold"
        >
          {isConnecting
            ? 'Connecting...'
            : integration.connected
              ? 'Disconnect'
              : 'Connect'
          }
        </button>
      )}
    </div>
  );
};

const IntegrationsSection: React.FC<{ showHeader?: boolean }> = ({ showHeader = true }) => {
  const [searchParams] = useSearchParams();
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const integrationRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const { setMessage } = useMessage();
  const focusIntegrationId = searchParams.get('focusIntegration')?.trim().toLowerCase() || '';
  
  const { data: integrationsData, loading: integrationsLoading, refetch } = useQuery(GET_INTEGRATIONS);
  const [connectIntegration] = useMutation(CONNECT_INTEGRATION, {
    refetchQueries: [{ query: GET_INTEGRATIONS }],
  });
  const [startConnection] = useMutation(START_INTEGRATION_CONNECTION, {
    refetchQueries: [{ query: GET_INTEGRATIONS }],
  });
  const [disconnectIntegration] = useMutation(DISCONNECT_INTEGRATION, {
    refetchQueries: [{ query: GET_INTEGRATIONS }],
  });

  const connectedIntegrations = new Set(
    integrationsData?.integrations?.map((integration) => integration.serviceId) || []
  );
  const linkedIntegrations = new Set(
    integrationsData?.integrations?.filter((integration) => integration.linked).map((integration) => integration.serviceId) || []
  );

  // Open Media has its own Account section (it is also how people sign in).
  const integrationsWithStatus: Integration[] = integrationCatalog.filter(integration => !integration.managedElsewhere).map(integration => ({
    ...integration,
    availability: integration.availability ?? 'available',
    connected: connectedIntegrations.has(integration.id),
    linked: linkedIntegrations.has(integration.id),
  }));

  useEffect(() => {
    if (!focusIntegrationId) {
      return;
    }

    const focusIntegration = getIntegrationCatalogEntry(focusIntegrationId);
    if (!focusIntegration) {
      return;
    }

    setSelectedCategory(focusIntegration.category);
    setSearchQuery(focusIntegration.name);
  }, [focusIntegrationId]);

  const filteredIntegrations = integrationsWithStatus.filter(integration => {
    const matchesCategory = selectedCategory === 'All' || integration.category === selectedCategory;
    const matchesSearch = integration.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         integration.description.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  });

  const handleToggle = async (integrationId: string, isConnected: boolean) => {
    if (isConnected) {
      await handleDisconnect(integrationId);
    } else {
      await handleConnect(integrationId);
    }
  };

  const handleConnect = async (integrationId: string) => {
    setConnectingId(integrationId);
    trackEvent('integration_connect_started', { service: integrationId });
    try {
      // One path for the app and agents: partners without their own sign-in
      // are added straight away; the rest continue to the provider's sign-in.
      const started = await startConnection({ variables: { serviceId: integrationId } });
      const outcome = started.data?.startIntegrationConnection;
      if (outcome && outcome.status !== 'needs_browser') {
        setMessage(outcome.message, 'success');
        trackEvent('integration_connect_outcome', {
          service: integrationId,
          outcome: 'saved_without_oauth',
          oauth: false,
        });
        refetch();
        setConnectingId(null);
        return;
      }
      if (outcome?.connectUrl && integrationId === 'open_media') {
        window.location.assign(outcome.connectUrl);
        return;
      }

      setMessage(`Opening ${integrationId} sign-in...`, 'info');

      const response = await fetch(`/auth/${integrationId}/start`, {
        method: 'GET',
        credentials: 'include',
      });

      const contentType = response.headers.get('content-type') || '';
      const data = contentType.includes('application/json')
        ? await response.json()
        : { detail: 'Unexpected response from auth service.' };

      if (!response.ok) {
        throw new Error(data.detail || data.message || `Failed to start ${integrationId} connection.`);
      }
      
      if (data.error === 'not_configured') {
        await connectIntegration({
          variables: {
            input: {
              serviceId: integrationId,
              accessToken: null,
              refreshToken: null,
              expiresAt: null,
              metadata: null,
            }
          }
        });
        setMessage(`${integrationId} added as a partner. Linking its account will be available once its sign-in is set up.`, 'success');
        trackEvent('integration_connect_outcome', {
          service: integrationId,
          outcome: 'saved_without_oauth',
          oauth: false,
        });
        refetch();
        setConnectingId(null);
        return;
      }
      
      if (data.auth_url) {
        const width = 600;
        const height = 700;
        const left = window.screenX + (window.outerWidth - width) / 2;
        const top = window.screenY + (window.outerHeight - height) / 2;
        
        const popup = window.open(
          data.auth_url,
          `oauth_${integrationId}`,
          `width=${width},height=${height},left=${left},top=${top},toolbar=no,menubar=no,scrollbars=yes,resizable=yes`
        );
        
        const handleMessage = (event: MessageEvent) => {
          if (event.data?.type === 'oauth_callback') {
            window.removeEventListener('message', handleMessage);
            if (event.data.status === 'success') {
              setMessage(`Successfully connected to ${event.data.provider}`, 'success');
              trackEvent('integration_connect_outcome', {
                service: integrationId,
                outcome: 'success',
                oauth: true,
              });
              refetch();
            } else {
              setMessage(`Failed to connect: ${event.data.message}`, 'error');
              trackEvent('integration_connect_outcome', {
                service: integrationId,
                outcome: 'failure',
                oauth: true,
              });
            }
            setConnectingId(null);
          }
        };
        
        window.addEventListener('message', handleMessage);
        
        const checkClosed = setInterval(() => {
          if (popup?.closed) {
            clearInterval(checkClosed);
            window.removeEventListener('message', handleMessage);
            setConnectingId(null);
            refetch();
          }
        }, 500);
        
        return;
      }
      
      throw new Error(data.detail || 'Failed to start OAuth flow');
    } catch (error: any) {
      console.error('Failed to connect integration:', error);
      trackEvent('integration_connect_outcome', {
        service: integrationId,
        outcome: 'failure',
        oauth: false,
      });
      setMessage(`Failed to connect to ${integrationId}: ${error.message}`, 'error');
      setConnectingId(null);
    }
  };

  const handleDisconnect = async (integrationId: string) => {
    setConnectingId(integrationId);
    try {
      await disconnectIntegration({
        variables: { serviceId: integrationId }
      });
      setMessage(`Successfully disconnected from ${integrationId}`, 'success');
      trackEvent('integration_disconnect_outcome', {
        service: integrationId,
        outcome: 'success',
      });
      refetch();
    } catch (error: any) {
      console.error('Failed to disconnect integration:', error);
      trackEvent('integration_disconnect_outcome', {
        service: integrationId,
        outcome: 'failure',
      });
      setMessage(`Failed to disconnect from ${integrationId}: ${error.message}`, 'error');
    } finally {
      setConnectingId(null);
    }
  };

  // Connected apps come first so people can see and manage what they use.
  const connectedFirst = filteredIntegrations.filter((integration) => integration.connected);
  const groupedIntegrations = filteredIntegrations.reduce(
    (acc, integration) => {
      const group = integration.connected ? 'Connected' : integration.category;
      if (!acc[group]) {
        acc[group] = [];
      }
      acc[group].push(integration);
      return acc;
    },
    (connectedFirst.length > 0 ? { Connected: [] } : {}) as Record<string, Integration[]>,
  );

  useEffect(() => {
    if (!focusIntegrationId) {
      return;
    }

    const targetCard = integrationRefs.current[focusIntegrationId];
    if (!targetCard) {
      return;
    }

    if (typeof targetCard.scrollIntoView === 'function') {
      targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [focusIntegrationId, filteredIntegrations]);

  return (
    <section className="manifest-panel p-4 sm:p-5">
      {showHeader ? (
        <div className="mb-5">
          <h2 className="text-xl font-semibold mb-2 text-theme-primary tracking-tight">
            Integrations
          </h2>
          <p className="text-sm text-theme-secondary leading-relaxed">
            Connect the tools and companies you work with. Connected partners show under Key Partners on every canvas.
          </p>
        </div>
      ) : null}

      <div ref={(node) => { integrationRefs.current.other = node; }}>
        <OtherPartners autoFocus={focusIntegrationId === 'other'} />
      </div>

      {/* Search Bar */}
      <div className="relative mb-6">
        <SearchIcon className="absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
        <input
          type="text"
          placeholder="Search integrations..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="manifest-field pl-12"
          aria-label="Search integrations"
        />
      </div>

      {/* Category Filter */}
      <div className="mb-5 flex flex-wrap gap-2">
        {integrationCategories.map((category) => (
          <button
            key={category}
            onClick={() => setSelectedCategory(category)}
            aria-pressed={selectedCategory === category}
            className={`manifest-control ${selectedCategory === category ? 'manifest-control-primary' : 'manifest-control-secondary'}`}
          >
            {category}
          </button>
        ))}
      </div>

      {/* Integrations Grid */}
      <div className="space-y-8">
        {Object.entries(groupedIntegrations).map(([category, categoryIntegrations]) => (
          <div key={category}>
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-[0.08em] text-theme-secondary">{category}</h3>
            <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2">
              {categoryIntegrations.map((integration) => (
                <div
                  key={integration.id}
                  ref={(element) => {
                    integrationRefs.current[integration.id] = element;
                  }}
                  data-integration-id={integration.id}
                >
                  <IntegrationCard
                    integration={integration}
                    onToggle={handleToggle}
                    isConnecting={connectingId === integration.id}
                  />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {integrationsLoading && (
        <div className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
          <p className="text-theme-secondary mt-4">Loading integrations...</p>
        </div>
      )}

      {!integrationsLoading && filteredIntegrations.length === 0 && (
        <div className="text-center py-12">
          <XIcon className="mx-auto w-12 h-12 text-gray-300 mb-4" />
          <p className="text-theme-secondary font-medium">No integrations found matching your search.</p>
        </div>
      )}
    </section>
  );
};

export default IntegrationsSection;
