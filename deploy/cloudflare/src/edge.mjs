// Pure request-routing helpers for the Manifest edge Worker (unit-tested).

export const BACKEND_PREFIXES = [
  "/graphql",
  "/socket.io/",
  "/api/",
  "/auth/",
  "/scim/",
  "/generated/",
  "/trust",
  "/ping",
  "/health",
  "/healthz",
  "/.well-known/",
  "/openapi.json",
  "/agents.md",
  "/AGENTS.md",
  "/pricing.md",
  "/internal/"
];

// Agent-discovery documents served by the backend (app/routes/agent_discovery_routes.py).
const EXACT = new Set([
  "/graphql", "/trust", "/ping", "/health", "/healthz", "/openapi.json",
  "/agents.md", "/AGENTS.md", "/pricing.md", "/index.md",
  "/about.md", "/contact.md", "/docs.md", "/docs/api.md", "/privacy.md",
  "/legal/privacy.md", "/legal/terms.md"
]);
const LEGACY_FILES_PREFIX = "/generated/pdfs/";
const SPA_AUTH_PATHS = new Set(["/auth/forgot-password", "/auth/reset-password"]);

export function isBackendPath(pathname) {
  if (SPA_AUTH_PATHS.has(pathname)) return false;
  if (EXACT.has(pathname)) return true;
  return BACKEND_PREFIXES.some((p) => p.endsWith("/") && pathname.startsWith(p)) ||
    pathname.startsWith("/graphql/");
}

// Live voice can run as its own service (same image, see render.yaml); unset = the backend.
export const VOICE_PATH_PREFIX = "/api/voice-agent/live";

export function originFor(pathname, env) {
  if (env.VOICE_ORIGIN && pathname.startsWith(VOICE_PATH_PREFIX)) return env.VOICE_ORIGIN;
  return env.BACKEND_ORIGIN;
}

export function requireOrigin(raw) {
  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new Error("BACKEND_ORIGIN must be a valid URL");
  }
  if (url.protocol !== "https:") throw new Error("BACKEND_ORIGIN must use HTTPS");
  return url;
}

/** Map a legacy /generated/pdfs/<bucket>/<object> URL to durable public storage. */
export function legacyFileUrl(pathname, filesPublicBase) {
  if (!filesPublicBase || !pathname.startsWith(LEGACY_FILES_PREFIX)) return null;
  const rest = pathname.slice(LEGACY_FILES_PREFIX.length);
  const parts = rest.split("/");
  if (parts.length < 2 || parts.some((p) => p === "" || p === "." || p === "..")) return null;
  return `${filesPublicBase.replace(/\/+$/, "")}/${rest}`;
}

/** Build the request forwarded to the backend origin. */
export function buildOriginRequest(request, originUrl, edgeSecret = "") {
  const incoming = new URL(request.url);
  const target = new URL(incoming.pathname + incoming.search, originUrl);
  const headers = new Headers(request.headers);
  for (const name of ["forwarded", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto",
    "x-forwarded-port", "x-real-ip", "x-manifest-edge"]) {
    headers.delete(name);
  }
  headers.set("x-forwarded-host", incoming.host);
  headers.set("x-forwarded-proto", incoming.protocol.slice(0, -1));
  const clientIp = request.headers.get("cf-connecting-ip");
  if (clientIp) headers.set("x-forwarded-for", clientIp);
  headers.delete("host");
  if (edgeSecret) headers.set("x-manifest-edge", edgeSecret);
  return new Request(target, {
    method: request.method,
    headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
    redirect: "manual",
    duplex: "half" // required by Node for streamed bodies; ignored by Workers
  });
}

/** Rewrite absolute redirects that point at the origin host back to the public host. */
export function rewriteLocation(response, originUrl, publicUrl) {
  const location = response.headers.get("location");
  if (!location) return response;
  let loc;
  try {
    loc = new URL(location, originUrl);
  } catch {
    return response;
  }
  if (loc.host !== originUrl.host) return response;
  loc.protocol = publicUrl.protocol;
  loc.host = publicUrl.host;
  const rewritten = new Response(response.body, response);
  rewritten.headers.set("location", loc.toString());
  return rewritten;
}

// Each public route gets its own title, description, canonical URL and first heading in the
// pre-hydration shell, so crawlers, link previews and screen readers see the page they asked
// for instead of the home page (issue #6). Signed-in app routes are marked noindex.
const SITE = "https://manifeststartup.com";
export const ROUTE_SHELLS = {
  "/about": ["About Manifest", "Manifest is an ideas-to-reality platform for founders: it drafts the business model, pitch deck, product requirements and early patent paperwork from the founder's own description of the idea."],
  "/contact": ["Contact Manifest", "How to reach the Manifest team with product and general questions."],
  "/docs": ["Manifest documentation", "Guides for founders, the REST and GraphQL API, the MCP server and the agent plugin."],
  "/docs/guide": ["Manifest founder guide", "How to go from a rough startup idea to a business model canvas, pitch deck, product requirements and a provisional patent draft in Manifest."],
  "/legal/terms": ["Manifest Terms of Service", "The terms that apply when you use Manifest."],
  "/legal/privacy": ["Manifest Privacy Policy", "What Manifest collects, why, how long it keeps it and how to exercise your rights."],
  "/privacy": ["Manifest privacy", "Your privacy controls, consent and data requests in Manifest."],
  "/developers": ["Build with Manifest", "API keys, the REST and GraphQL API, the MCP server and the agent plugin for building on Manifest."],
  "/research": ["Founder research survey", "Tell us how you take a startup idea forward; it shapes what Manifest builds next."],
  "/feedback/survey": ["Manifest product feedback", "Tell the Manifest team what works and what doesn't."],
  "/learn-more": ["How Manifest works", "From a rough idea to an investable plan: qualification, business model canvas, pitch deck, product requirements and patent drafts in one workspace."],
  "/pitch-reels": ["Pitch shorts on Manifest", "Short video pitches from founders building on Manifest."],
  "/pitch-shorts": ["Pitch shorts on Manifest", "Short video pitches from founders building on Manifest."],
  "/shorts": ["Pitch shorts on Manifest", "Short video pitches from founders building on Manifest."],
  "/discover": ["Discover startup ideas on Manifest", "Published startup ideas and pitch shorts from founders on Manifest."],
  "/auth": ["Sign in to Manifest", "Sign in to Manifest with Open Media to work on your startup ideas."],
  "/login": ["Sign in to Manifest", "Sign in to Manifest with Open Media to work on your startup ideas."],
  "/signup": ["Create your Manifest account", "Start turning your startup idea into a plan."],
};
const PRIVATE_SHELL_ROUTES = /^\/(ideas|account|messages|portfolio|admin|home)(\/|$)/;

function escapeHtml(value) {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

export function shellForRoute(html, pathname) {
  const meta = ROUTE_SHELLS[pathname];
  if (!meta) {
    if (!PRIVATE_SHELL_ROUTES.test(pathname)) return html;
    return html.replace("</head>", '    <meta name="robots" content="noindex" />\n  </head>');
  }
  const [title, description] = meta.map(escapeHtml);
  const url = `${SITE}${pathname}`;
  return html
    .replace(/<title>[^<]*<\/title>/, `<title>${title} · Manifest</title>`)
    .replace(/(<meta name="description" content=")[^"]*/, `$1${description}`)
    .replace(/(<meta property="og:title" content=")[^"]*/, `$1${title}`)
    .replace(/(<meta property="og:description" content=")[^"]*/, `$1${description}`)
    .replace(/(<meta property="og:url" content=")[^"]*/, `$1${url}`)
    .replace(/(<link rel="canonical" href=")[^"]*/, `$1${url}`)
    .replace(
      /(<main id="manifest-static-shell"[^>]*>\s*)<h1>[^<]*<\/h1>\s*<p>[^<]*<\/p>/,
      `$1<h1>${title}</h1>\n        <p>${description}</p>`
    );
}
