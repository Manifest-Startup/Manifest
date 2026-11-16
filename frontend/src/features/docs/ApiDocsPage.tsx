import PageHeader from "features/common-ui/PageHeader";
import React, { useState } from "react";
import { Link } from "react-router-dom";

import MarkdownDocument from "./MarkdownDocument";

const sections = [
  { id: "overview", label: "Overview" },
  { id: "authentication", label: "Authentication" },
  { id: "surfaces", label: "Surfaces" },
  { id: "examples", label: "Examples" },
  { id: "billing", label: "Billing" },
  { id: "errors", label: "Errors" },
  { id: "reference", label: "Full reference" },
];

const surfaces = [
  {
    name: "POST /graphql",
    auth: "Session JWT or auth cookies",
    audience: "Main web app and authenticated clients",
    summary: "Primary application API for ideas, messaging, collaboration, social features, investing, guest flows, and pitch reels.",
  },
  {
    name: "REST /api/v1/*",
    auth: "Bearer manifest_sk_... API key",
    audience: "External integrations and automation",
    summary: "Public REST surface for idea CRUD, generation triggers, and usage-aware automation with API keys.",
  },
  {
    name: "REST /api/keys/*",
    auth: "Session JWT or auth cookies",
    audience: "Authenticated users managing API clients and keys",
    summary: "Create clients, issue keys, revoke keys, inspect usage, and fetch tier limits from account-backed routes.",
  },
  {
    name: "REST /api/voice-agent/*",
    auth: "Session JWT or auth cookies",
    audience: "Voice-capable product clients",
    summary: "Voice session, app-control, qualification, transcription, and TTS routes used by the Manifest Voice experience.",
  },
];

const operations = [
  {
    kind: "SESSION",
    name: "Sign in to get a session cookie",
    summary: "Browser sessions come from Continue with Open Media (GET /api/auth/open-media/start). Scripts and agents should use an API key instead.",
    code: `# In a browser: open the page below, continue with Open Media, and the
# session_token cookie is set when you return.
open "http://localhost:8000/api/auth/open-media/start?next=/ideas"`,
  },
  {
    kind: "QUERY",
    name: "List ideas over GraphQL",
    summary: "Once you have a valid session JWT or cookie, query the founder workspace directly through GraphQL.",
    code: `query {
  ideas {
    ideaId
    title
    description
    isPublished
    generatedAssetCount
  }
}`,
  },
  {
    kind: "MUTATION",
    name: "Create and update ideas",
    summary: "Use GraphQL mutations for the same create-and-iterate workflow that powers the web app.",
    code: `mutation {
  createIdea(
    title: "AI venture assistant"
    description: "Help founders turn startup ideas into execution-ready plans"
  ) {
    ideaId
    title
  }
}`,
  },
  {
    kind: "API KEY",
    name: "Call the public REST API",
    summary: "Use API keys only for the public `/api/v1` routes, not for the main GraphQL session-based surface.",
    code: `curl http://localhost:8000/api/v1/ideas \\
  -H "Authorization: Bearer manifest_sk_your_api_key"`,
  },
  {
    kind: "VOICE",
    name: "Inspect voice capabilities",
    summary: "Use the voice-agent capabilities route to inspect the deterministic command catalog available to authenticated voice sessions.",
    code: `curl http://localhost:8000/api/voice-agent/capabilities \\
  -H "Authorization: Bearer <session-jwt>"`,
  },
];

const plans = [
  { name: "Free", price: "$0", requests: "1,000 req/month", limit: "10 req/min" },
  { name: "Starter", price: "$29", requests: "10,000 req/month", limit: "60 req/min" },
  { name: "Pro", price: "$99", requests: "100,000 req/month", limit: "300 req/min" },
  { name: "Enterprise", price: "Custom", requests: "Unlimited", limit: "1,000 req/min" },
];

const errorCodes = [
  { code: "missing_api_key", status: "401", description: "No API key was provided for a `/api/v1` request." },
  { code: "invalid_format", status: "401", description: "The authorization header was not sent in `Bearer <token>` format." },
  { code: "invalid_api_key", status: "401", description: "The supplied API key was invalid or revoked." },
  { code: "rate_limit_exceeded", status: "429", description: "The request exceeded the per-minute limit for the client's tier." },
  { code: "monthly_limit_exceeded", status: "429", description: "The client has exhausted its allowed monthly request volume." },
  { code: "forbidden", status: "403", description: "The authenticated caller does not have access to the requested resource." },
];

const documentTabs = [
  { id: "api", label: "API reference", path: "/docs/API.md", title: "Manifest API reference" },
  { id: "voice", label: "Voice agent API", path: "/docs/VOICE_AGENT_API.md", title: "Voice agent API reference" },
] as const;

const CodeBlock: React.FC<{ children: string }> = ({ children }) => (
  <pre className="mt-5 overflow-x-auto rounded-lg bg-neutral900 px-5 py-4 text-sm text-gray100 dark:bg-black">
    <code>{children}</code>
  </pre>
);

const ApiDocsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<(typeof documentTabs)[number]["id"]>("api");
  const activeDocument = documentTabs.find((tab) => tab.id === activeTab) ?? documentTabs[0];

  return (
    <div className="manifest-page">
      <div className="manifest-page-shell">
        <PageHeader eyebrow="Documentation" title="API reference" description="Authentication, endpoints, examples, and usage limits.">
          <Link to="/docs/guide" className="manifest-control manifest-control-secondary">Open user guide</Link>
        </PageHeader>

        <div className="grid gap-6 lg:grid-cols-[14rem_minmax(0,1fr)]">
          <aside className="h-fit min-w-0 border-b border-theme-primary pb-4 lg:border-b-0 lg:border-r lg:pr-4 lg:sticky lg:top-24">
            <p className="px-3 text-[0.72rem] font-medium text-gray500 dark:text-gray400">Navigate</p>
            <nav className="mt-3 flex flex-wrap gap-1 lg:flex-col">
              {sections.map((section) => (
                <a
                  key={section.id}
                  href={`#${section.id}`}
                  className="rounded-2xl px-3 py-2.5 text-sm font-semibold text-neutral700 hover:bg-white/70 hover:text-neutral900 dark:text-gray300 dark:hover:bg-neutral800 dark:hover:text-white"
                >
                  {section.label}
                </a>
              ))}
            </nav>
          </aside>

          <main className="min-w-0 space-y-6">
            <section id="overview" className="manifest-reading-surface border-b border-theme-primary">
              <p className="manifest-kicker">Overview</p>
              <h2 className="mt-3 text-xl font-semibold sm:text-2xl tracking-[-0.03em] text-neutral900 dark:text-white">One product backend, several entry points</h2>
              <p className="manifest-subtitle mt-4 max-w-3xl text-sm sm:text-base">
                The same backend powers the founder workspace, guest sessions, collaboration, messaging, pitch reels, account tools,
                and voice experiences. The goal of the API documentation is to make those entry points explicit so integrators do not
                accidentally mix session-authenticated product routes with API-key-authenticated public REST routes.
              </p>
              <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50/80 px-5 py-5 dark:border-amber-900/50 dark:bg-amber-950/20">
                <p className="text-xs font-medium text-amber-700 dark:text-amber-300">Important</p>
                <p className="mt-2 text-sm leading-7 text-neutral900 dark:text-gray100">
                  API keys are for <code className="rounded bg-white px-2 py-1 text-[0.82rem] dark:bg-neutral700">/api/v1/*</code>. The main
                  GraphQL app surface uses a session JWT or auth cookies instead.
                </p>
              </div>
            </section>

            <section id="authentication" className="manifest-reading-surface border-b border-theme-primary">
              <p className="manifest-kicker">Authentication</p>
              <h2 className="mt-3 text-xl font-semibold sm:text-2xl tracking-[-0.03em] text-neutral900 dark:text-white">There are two auth models, and they solve different problems.</h2>
              <div className="mt-6 grid gap-4 lg:grid-cols-2">
                <article className="manifest-card px-5 py-5">
                  <p className="text-xs font-medium text-gray500 dark:text-gray400">Session / JWT auth</p>
                  <p className="mt-3 text-sm leading-7 text-gray500 dark:text-gray300">
                    Used by GraphQL, API-key management routes, and voice-agent routes. Accepted token locations are the
                    <code className="ml-1 rounded bg-gray100 px-2 py-1 text-[0.82rem] dark:bg-neutral700">access_token</code> cookie, the
                    <code className="ml-1 rounded bg-gray100 px-2 py-1 text-[0.82rem] dark:bg-neutral700">session_token</code> cookie, or an
                    <code className="ml-1 rounded bg-gray100 px-2 py-1 text-[0.82rem] dark:bg-neutral700">Authorization: Bearer &lt;jwt&gt;</code> header.
                  </p>
                  <CodeBlock>{`Authorization: Bearer <session-jwt>`}</CodeBlock>
                </article>

                <article className="manifest-card px-5 py-5">
                  <p className="text-xs font-medium text-gray500 dark:text-gray400">API key auth</p>
                  <p className="mt-3 text-sm leading-7 text-gray500 dark:text-gray300">
                    Used only by the public REST API under <code className="rounded bg-gray100 px-2 py-1 text-[0.82rem] dark:bg-neutral700">/api/v1</code>.
                    Create keys from Account settings, store them server-side, and use them for automation or external integrations.
                  </p>
                  <CodeBlock>{`Authorization: Bearer manifest_sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`}</CodeBlock>
                </article>
              </div>
            </section>

            <section id="surfaces" className="manifest-reading-surface border-b border-theme-primary">
              <p className="manifest-kicker">API surfaces</p>
              <h2 className="mt-3 text-xl font-semibold sm:text-2xl tracking-[-0.03em] text-neutral900 dark:text-white">Choose the route family that matches your job to be done.</h2>
              <div className="mt-6 grid gap-4 xl:grid-cols-2">
                {surfaces.map((surface) => (
                  <article key={surface.name} className="manifest-card px-5 py-5">
                    <p className="text-xs font-medium text-gray500 dark:text-gray400">{surface.name}</p>
                    <p className="mt-3 text-sm font-semibold text-neutral900 dark:text-white">{surface.auth}</p>
                    <p className="mt-2 text-sm text-gray500 dark:text-gray300">{surface.audience}</p>
                    <p className="mt-4 text-sm leading-7 text-gray500 dark:text-gray300">{surface.summary}</p>
                  </article>
                ))}
              </div>
              <div className="mt-6 manifest-card px-5 py-5">
                <p className="text-xs font-medium text-gray500 dark:text-gray400">Internal-only routes</p>
                <p className="mt-3 text-sm leading-7 text-gray500 dark:text-gray300">
                  The <code className="rounded bg-gray100 px-2 py-1 text-[0.82rem] dark:bg-neutral700">/api/internal/*</code> survey, website-testing,
                  and production-signals routes are for Manifest's own internal feedback loops and trusted agents. They are not customer-facing product APIs.
                </p>
              </div>
            </section>

            <section id="examples" className="manifest-reading-surface border-b border-theme-primary">
              <p className="manifest-kicker">Examples</p>
              <h2 className="mt-3 text-xl font-semibold sm:text-2xl tracking-[-0.03em] text-neutral900 dark:text-white">Start from working request shapes instead of reverse-engineering the frontend.</h2>
              <div className="mt-6 space-y-4">
                {operations.map((operation) => (
                  <article className="manifest-card overflow-hidden" key={operation.name}>
                    <div className="flex flex-wrap items-center gap-3 border-b border-gray200 px-5 py-4 dark:border-neutral700">
                      <span
                        className={`rounded-full px-3 py-1 text-[0.72rem] font-medium ${
                          operation.kind === "QUERY"
                            ? "bg-accent-50 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300"
                            : operation.kind === "MUTATION"
                              ? "bg-neutral900 text-white dark:bg-white dark:text-neutral900"
                              : operation.kind === "API KEY"
                                ? "bg-sky-50 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
                                : operation.kind === "VOICE"
                                  ? "bg-violet-50 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300"
                                  : "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                        }`}
                      >
                        {operation.kind}
                      </span>
                      <code className="text-sm font-semibold text-neutral900 dark:text-white">{operation.name}</code>
                    </div>
                    <div className="space-y-4 px-5 py-5">
                      <p className="text-sm leading-7 text-gray500 dark:text-gray300">{operation.summary}</p>
                      <CodeBlock>{operation.code}</CodeBlock>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section id="billing" className="manifest-reading-surface border-b border-theme-primary">
              <p className="manifest-kicker">Billing &amp; rate limits</p>
              <h2 className="mt-3 text-xl font-semibold sm:text-2xl tracking-[-0.03em] text-neutral900 dark:text-white">Tier limits matter only for API-key backed public REST usage.</h2>
              <p className="manifest-subtitle mt-4 max-w-3xl text-sm sm:text-base">
                The public tier data exposed by <code className="rounded bg-gray100 px-2 py-1 text-[0.82rem] dark:bg-neutral700">GET /api/keys/tiers</code>
                currently defines the pricing and request limits below.
              </p>
              <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                {plans.map((plan) => (
                  <article className="manifest-card px-5 py-5" key={plan.name}>
                    <p className="text-xs font-medium text-gray500 dark:text-gray400">{plan.name}</p>
                    <p className="mt-3 text-3xl font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">{plan.price}</p>
                    <p className="mt-3 text-sm font-semibold text-neutral900 dark:text-white">{plan.requests}</p>
                    <p className="mt-1 text-sm text-gray500 dark:text-gray400">{plan.limit}</p>
                  </article>
                ))}
              </div>
            </section>

            <section id="errors" className="manifest-reading-surface border-b border-theme-primary">
              <p className="manifest-kicker">Errors</p>
              <h2 className="mt-3 text-xl font-semibold sm:text-2xl tracking-[-0.03em] text-neutral900 dark:text-white">Expect GraphQL errors on the session surface and explicit HTTP errors on API-key REST routes.</h2>
              <div className="mt-6 grid gap-4 lg:grid-cols-2">
                <div className="manifest-card px-5 py-5">
                  <p className="text-xs font-medium text-gray500 dark:text-gray400">GraphQL error envelope</p>
                  <CodeBlock>{`{
  "data": null,
  "errors": [
    {
      "message": "Invalid or expired token"
    }
  ]
}`}</CodeBlock>
                </div>
                <div className="manifest-card px-5 py-5">
                  <p className="text-xs font-medium text-gray500 dark:text-gray400">REST API-key error</p>
                  <CodeBlock>{`{
  "error": {
    "type": "authentication_error",
    "code": "invalid_api_key",
    "message": "Invalid API key provided."
  }
}`}</CodeBlock>
                </div>
              </div>

              <div className="mt-6 overflow-hidden rounded-lg border border-gray200 dark:border-neutral700">
                <table className="w-full border-collapse">
                  <thead className="bg-white/75 dark:bg-neutral800/90">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray500 dark:text-gray400">Code</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray500 dark:text-gray400">Status</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray500 dark:text-gray400">Description</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white/70 text-sm dark:bg-neutral900/75">
                    {errorCodes.map((item) => (
                      <tr className="border-t border-gray200 dark:border-neutral700" key={item.code}>
                        <td className="px-4 py-3">
                          <code className="rounded bg-gray100 px-2 py-1 text-[0.82rem] text-neutral900 dark:bg-neutral700 dark:text-white">
                            {item.code}
                          </code>
                        </td>
                        <td className="px-4 py-3 font-semibold text-neutral900 dark:text-white">{item.status}</td>
                        <td className="px-4 py-3 text-gray500 dark:text-gray300">{item.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section id="reference" className="space-y-4">
              <div className="manifest-reading-surface border-b border-theme-primary">
                <p className="manifest-kicker">Full reference</p>
                <h2 className="mt-3 text-xl font-semibold sm:text-2xl tracking-[-0.03em] text-neutral900 dark:text-white">Read the synced source-of-truth documentation inside the app.</h2>
                <p className="manifest-subtitle mt-4 max-w-3xl text-sm sm:text-base">
                  These markdown documents are copied from the canonical repository docs so the in-app technical reference stays aligned
                  with the backend source of truth.
                </p>
                <div className="mt-6 flex flex-wrap gap-3">
                  {documentTabs.map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setActiveTab(tab.id)}
                      className={`rounded-full px-4 py-2.5 text-sm font-semibold transition-all ${
                        activeTab === tab.id
                          ? "bg-accent-500 text-white shadow-none"
                          : "border border-stone200 bg-white/80 text-neutral900 hover:border-stone300 hover:bg-stone50 dark:border-neutral700 dark:bg-neutral900/85 dark:text-white dark:hover:border-neutral600 dark:hover:bg-neutral800"
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>

              <MarkdownDocument path={activeDocument.path} title={activeDocument.title} />
            </section>
          </main>
        </div>
      </div>
    </div>
  );
};

export default ApiDocsPage;
