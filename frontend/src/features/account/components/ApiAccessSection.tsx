import React, { useCallback, useEffect, useMemo, useState } from "react";

import { openMediaSignInUrl } from "features/auth/openMediaSignIn";
import { buildSessionHeaders } from "features/auth/session";
import Button from "features/common-ui/Button";
import Input from "features/common-ui/Input";

interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  status: string;
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
}

interface ApiClient {
  id: string;
  name: string;
  tier: string;
  status: string;
  created_at: string;
  keys: ApiKey[];
}

interface UsageStats {
  tier: string;
  requests_used: number;
  requests_limit: number;
  tokens_used: number;
  rate_limit_per_minute: number;
}

interface Tier {
  id: string;
  name: string;
  price: number;
  requests_per_month: number;
  rate_limit_per_minute: number;
  features: string[];
}

const formatTierName = (tier: string) => tier.charAt(0).toUpperCase() + tier.slice(1);

const formatDate = (value: string | null) => {
  if (!value) {
    return "Never used";
  }

  return `Used ${new Date(value).toLocaleDateString()}`;
};

const ApiAccessSection: React.FC = () => {
  const [clients, setClients] = useState<ApiClient[]>([]);
  const [usage, setUsage] = useState<UsageStats | null>(null);
  const [tiers, setTiers] = useState<Tier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Creating, rotating and revoking keys needs a sign-in from the last few minutes.
  const [needsFreshSignIn, setNeedsFreshSignIn] = useState(false);
  const [showNewKeyModal, setShowNewKeyModal] = useState(false);
  const [newKeyName, setNewKeyName] = useState("My API Key");
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [creating, setCreating] = useState(false);

  const getAuthHeaders = useCallback(() => {
    return buildSessionHeaders({
      "Content-Type": "application/json",
    });
  }, []);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [clientsRes, usageRes, tiersRes] = await Promise.all([
        fetch("/api/keys/clients", { headers: getAuthHeaders(), credentials: "include" }),
        fetch("/api/keys/usage", { headers: getAuthHeaders(), credentials: "include" }),
        fetch("/api/keys/tiers"),
      ]);

      if (clientsRes.ok) {
        const data = await clientsRes.json();
        setClients(data.clients || []);
      }

      if (usageRes.ok) {
        const data = await usageRes.json();
        setUsage(data.usage);
      }

      if (tiersRes.ok) {
        const data = await tiersRes.json();
        setTiers(data.tiers || []);
      }
    } catch (err) {
      setError("Failed to load API data");
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const createApiKey = async () => {
    try {
      setCreating(true);
      setError(null);

      let clientId = clients[0]?.id;

      if (!clientId) {
        const createClientRes = await fetch("/api/keys/clients", {
          method: "POST",
          headers: getAuthHeaders(),
          credentials: "include",
          body: JSON.stringify({ name: "Default Client" }),
        });

        if (!createClientRes.ok) {
          throw new Error("Failed to create API client");
        }

        const data = await createClientRes.json();
        clientId = data.client.id;
      }

      const res = await fetch("/api/keys/keys", {
        method: "POST",
        headers: getAuthHeaders(),
        credentials: "include",
        body: JSON.stringify({ client_id: clientId, name: newKeyName }),
      });

      if (res.status === 401 && res.headers.get("X-Step-Up-Required")) {
        setNeedsFreshSignIn(true);
        return;
      }
      if (!res.ok) {
        throw new Error("Failed to create API key");
      }

      const data = await res.json();
      setCreatedKey(data.key.full_key);
      await fetchData();
    } catch (err) {
      setError("Failed to create API key");
    } finally {
      setCreating(false);
    }
  };

  const revokeKey = async (keyId: string) => {
    if (!window.confirm("Are you sure you want to revoke this key? This cannot be undone.")) {
      return;
    }

    try {
      setError(null);
      const res = await fetch(`/api/keys/keys/${keyId}`, {
        method: "DELETE",
        headers: getAuthHeaders(),
        credentials: "include",
      });

      if (res.status === 401 && res.headers.get("X-Step-Up-Required")) {
        setNeedsFreshSignIn(true);
        return;
      }
      if (!res.ok) {
        throw new Error("Failed to revoke key");
      }

      await fetchData();
    } catch (err) {
      setError("Failed to revoke key");
    }
  };

  const copyToClipboard = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const allKeys = useMemo(() => clients.flatMap((client) => client.keys.filter((key) => key.status === "active")), [clients]);
  const usagePercent =
    usage && usage.requests_limit > 0 ? Math.min((usage.requests_used / usage.requests_limit) * 100, 100) : 0;

  const summaryCards = [
    {
      label: "Tier",
      value: usage ? formatTierName(usage.tier) : "Unavailable",
      helper: usage ? `${usage.rate_limit_per_minute} req/min limit` : "Waiting for usage data",
    },
    {
      label: "Utilization",
      value: usage ? `${usagePercent.toFixed(0)}%` : "0%",
      helper: usage ? "Current monthly consumption" : "No usage data yet",
    },
    {
      label: "Active Keys",
      value: allKeys.length.toString(),
      helper: allKeys.length > 0 ? "Ready for integrations" : "Create a key to get started",
    },
  ];

  if (loading) {
    return (
      <section className="manifest-panel p-4 sm:p-5">
        <div className="animate-pulse space-y-4">
          <div className="h-6 w-32 rounded-full bg-gray200 dark:bg-neutral700" />
          <div className="grid gap-3 md:grid-cols-3">
            {[1, 2, 3].map((item) => (
              <div className="h-28 rounded-lg bg-gray100 dark:bg-neutral800" key={item} />
            ))}
          </div>
          <div className="h-32 rounded-lg bg-gray100 dark:bg-neutral800" />
        </div>
      </section>
    );
  }

  return (
    <>
      <section className="manifest-panel p-4 sm:p-5">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <span className="manifest-kicker">Developer Access</span>
            <h2 className="mt-4 text-3xl font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">API Access</h2>
            <p className="manifest-subtitle mt-3 max-w-3xl text-sm sm:text-base">
              Access Manifest programmatically through the GraphQL API and supporting key-management endpoints. Keep integrations,
              automations, and external tools aligned to the same backend capability used by the product.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <a
              href="/docs/api"
              target="_blank"
              rel="noopener noreferrer"
              className="manifest-control manifest-control-secondary"
            >
              View API Docs
            </a>
            <Button variant="primary" onClick={() => setShowNewKeyModal(true)}>
              Create Key
            </Button>
          </div>
        </div>

        {needsFreshSignIn ? (
          <div
            role="alert"
            className="mt-5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800/60 dark:bg-amber-950/30 dark:text-amber-100"
          >
            For your security, managing API keys needs a recent sign-in.{" "}
            <a className="font-semibold underline" href={openMediaSignInUrl("/account")} data-testid="api-keys-sign-in-again">
              Continue with Open Media
            </a>{" "}
            and try again.
          </div>
        ) : null}

        {error ? (
          <div className="mt-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-900/20 dark:text-red-300">
            {error}
          </div>
        ) : null}

        <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-3">
              {summaryCards.map((card) => (
                <article className="manifest-card px-5 py-5" key={card.label}>
                  <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">{card.label}</p>
                  <p className="mt-3 text-3xl font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">{card.value}</p>
                  <p className="mt-2 text-sm text-gray500 dark:text-gray400">{card.helper}</p>
                </article>
              ))}
            </div>

            {usage ? (
              <div className="manifest-panel-muted p-5">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-sm font-semibold text-neutral900 dark:text-white">Monthly Usage</p>
                    <p className="mt-1 text-sm text-gray500 dark:text-gray400">
                      {usage.requests_used.toLocaleString()} /{" "}
                      {usage.requests_limit === -1 ? "Unlimited" : usage.requests_limit.toLocaleString()} requests
                    </p>
                  </div>
                  <span className="manifest-pill">{usage.rate_limit_per_minute} req/min</span>
                </div>
                <div className="mt-4 h-3 overflow-hidden rounded-full bg-white/85 dark:bg-neutral800">
                  <div
                    className={`h-full rounded-full transition-all ${
                      usagePercent >= 90 ? "bg-red-500" : usagePercent >= 70 ? "bg-amber-500" : "bg-accent-500"
                    }`}
                    style={{ width: `${usagePercent}%` }}
                  />
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <div className="manifest-card px-4 py-4">
                    <p className="text-xs font-medium text-gray500 dark:text-gray400">Tier</p>
                    <p className="mt-2 text-sm font-semibold text-neutral900 dark:text-white">{formatTierName(usage.tier)}</p>
                  </div>
                  <div className="manifest-card px-4 py-4">
                    <p className="text-xs font-medium text-gray500 dark:text-gray400">Tokens Used</p>
                    <p className="mt-2 text-sm font-semibold text-neutral900 dark:text-white">{usage.tokens_used.toLocaleString()}</p>
                  </div>
                </div>
              </div>
            ) : null}
          </div>

          <div className="manifest-panel-muted p-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-neutral900 dark:text-white">Active API Keys</p>
                <p className="mt-1 text-sm text-gray500 dark:text-gray400">Create, audit, and revoke keys without leaving the workspace.</p>
              </div>
            </div>

            <div className="mt-4 space-y-3">
              {allKeys.length === 0 ? (
                <div className="manifest-empty px-5 py-8 text-center">
                  <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-white/80 shadow-none dark:bg-neutral800">
                    <svg className="h-6 w-6 text-accent-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                    </svg>
                  </div>
                  <p className="mt-4 text-sm font-semibold text-neutral900 dark:text-white">No API keys yet</p>
                  <p className="mt-1 text-sm text-gray500 dark:text-gray400">Create a key to start using the API.</p>
                </div>
              ) : (
                allKeys.map((key) => (
                  <article className="manifest-card px-4 py-4" key={key.id}>
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-neutral900 dark:text-white">{key.name}</p>
                        <p className="mt-1 font-mono text-xs text-gray500 dark:text-gray400">{key.key_prefix}...</p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <span className="manifest-pill">{formatDate(key.last_used_at)}</span>
                          {key.expires_at ? <span className="manifest-pill">Expires {new Date(key.expires_at).toLocaleDateString()}</span> : null}
                        </div>
                      </div>
                      <Button variant="ghost" className="justify-start sm:justify-center" onClick={() => revokeKey(key.id)}>
                        Revoke
                      </Button>
                    </div>
                  </article>
                ))
              )}
            </div>
          </div>
        </div>

        {tiers.length > 0 ? (
          <div className="mt-6 border-t border-gray200 pt-6 dark:border-neutral700">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-sm font-semibold text-neutral900 dark:text-white">Upgrade Your Plan</p>
                <p className="mt-1 text-sm text-gray500 dark:text-gray400">Select the capacity profile that matches your integration volume.</p>
              </div>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {tiers.map((tier) => {
                const isCurrent = usage?.tier === tier.id;
                return (
                  <article
                    className={`rounded-lg border px-4 py-4 ${
                      isCurrent
                        ? "border-accent-200 bg-accent-50 shadow-none dark:border-accent-800 dark:bg-accent-900/20"
                        : "manifest-card"
                    }`}
                    key={tier.id}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-neutral900 dark:text-white">{tier.name}</p>
                      {isCurrent ? <span className="manifest-pill">Current</span> : null}
                    </div>
                    <p className="mt-4 text-3xl font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">
                      {tier.price === 0 ? "Free" : tier.price === -1 ? "Custom" : `$${tier.price}`}
                    </p>
                    <p className="mt-2 text-sm text-gray500 dark:text-gray400">
                      {tier.requests_per_month === -1 ? "Unlimited" : tier.requests_per_month.toLocaleString()} req/month
                    </p>
                    <p className="mt-1 text-sm text-gray500 dark:text-gray400">{tier.rate_limit_per_minute} req/min</p>
                  </article>
                );
              })}
            </div>
          </div>
        ) : null}
      </section>

      {showNewKeyModal ? (
        <div className="manifest-modal-backdrop">
          <div className="manifest-modal manifest-modal-compact" role="dialog" aria-modal="true" aria-labelledby="api-key-modal-title">
            {createdKey ? (
              <>
                <div className="manifest-modal-header">
                  <div>
                    <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">API Key Created</p>
                    <h3 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-neutral900 dark:text-white" id="api-key-modal-title">
                      Store this key securely
                    </h3>
                  </div>
                </div>
                <div className="manifest-modal-body space-y-4">
                  <p className="text-sm leading-6 text-gray500 dark:text-gray300">Copy this key now. You won't be able to see it again.</p>
                  <div className="manifest-code-block relative">
                    <code className="block break-all pr-10">{createdKey}</code>
                    <button
                      onClick={() => copyToClipboard(createdKey)}
                      aria-label="Copy API key"
                      className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-xl bg-white/10 text-white hover:bg-white/20"
                    >
                      {copied ? (
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                        </svg>
                      )}
                    </button>
                  </div>
                  <Button
                    variant="primary"
                    className="w-full"
                    onClick={() => {
                      setShowNewKeyModal(false);
                      setCreatedKey(null);
                      setNewKeyName("My API Key");
                    }}
                  >
                    Done
                  </Button>
                </div>
              </>
            ) : (
              <>
                <div className="manifest-modal-header">
                  <div>
                    <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Provision Key</p>
                    <h3 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-neutral900 dark:text-white" id="api-key-modal-title">
                      Create API Key
                    </h3>
                  </div>
                  <button
                    aria-label="Close"
                    className="rounded-2xl p-2 text-gray500 hover:bg-white/70 hover:text-neutral900 dark:hover:bg-neutral800 dark:hover:text-white"
                    onClick={() => {
                      setShowNewKeyModal(false);
                      setNewKeyName("My API Key");
                    }}
                  >
                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
                <div className="manifest-modal-body space-y-5">
                  <div>
                    <label className="mb-2 block text-sm font-semibold text-neutral900 dark:text-white">Key Name</label>
                    <Input
                      type="text"
                      value={newKeyName}
                      onChange={(e) => setNewKeyName(e.target.value)}
                      placeholder="e.g., Production Key"
                      className="w-full"
                    />
                  </div>
                  <div className="manifest-empty px-4 py-4 text-sm leading-6">
                    Use descriptive names like <strong>Production Backend</strong> or <strong>Zapier Automation</strong> so keys remain auditable later.
                  </div>
                  <div className="flex gap-3">
                    <Button
                      variant="secondary"
                      className="flex-1"
                      onClick={() => {
                        setShowNewKeyModal(false);
                        setNewKeyName("My API Key");
                      }}
                    >
                      Cancel
                    </Button>
                    <Button variant="primary" className="flex-1" onClick={createApiKey} disabled={creating || !newKeyName.trim()}>
                      {creating ? "Creating..." : "Create"}
                    </Button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
};

export default ApiAccessSection;
