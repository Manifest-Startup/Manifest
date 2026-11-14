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
