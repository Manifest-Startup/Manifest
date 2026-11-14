import {
  buildOriginRequest,
  isBackendPath,
  legacyFileUrl,
  requireOrigin,
  rewriteLocation
} from "./edge.mjs";
import { handleManifestMcpRequest } from "./mcp.mjs";
import { handleManifestDocsMcpRequest } from "./mcp-docs.mjs";
import { recordOraRequest } from "./ora-reporting.mjs";

async function proxyToOrigin(request, env) {
  const origin = requireOrigin(env.BACKEND_ORIGIN);
  const response = await fetch(buildOriginRequest(request, origin, env.EDGE_SHARED_SECRET));
  if (response.status === 101) return response; // WebSocket upgrade (Socket.IO)
  return rewriteLocation(response, origin, new URL(request.url));
}

async function serveLegacyFile(request, env, ctx) {
  const target = legacyFileUrl(new URL(request.url).pathname, env.FILES_PUBLIC_BASE);
  if (!target || !["GET", "HEAD"].includes(request.method)) return null;
  const cache = caches.default;
  const cached = await cache.match(request);
  if (cached) return cached;
  const upstream = await fetch(target, { method: request.method });
  if (!upstream.ok) return null; // fall back to the backend copy
  const response = new Response(upstream.body, upstream);
  response.headers.set("cache-control", "public, max-age=86400");
  if (request.method === "GET") ctx.waitUntil(cache.put(request, response.clone()));
  return response;
}

async function handleRequest(request, env, ctx) {
    const { pathname } = new URL(request.url);
    if (request.method === "GET" && pathname === "/__ora/status") {
      return Response.json(
        { reporting: Boolean(env.ORA_INGEST_KEY), domainId: env.ORA_DOMAIN_ID || null },
        { headers: { "cache-control": "no-store" } }
      );
    }
    if (pathname === "/docs/mcp") {
      return handleManifestDocsMcpRequest(request, (documentRequest) => proxyToOrigin(documentRequest, env));
    }
    if (pathname === "/mcp") {
      return handleManifestMcpRequest(request, (apiRequest) => proxyToOrigin(apiRequest, env));
    }
    const userAgent = request.headers.get("user-agent") || "";
    const wantsMarkdown = (request.headers.get("accept") || "").includes("text/markdown");
    const isAgentBrowser = /ChatGPT-User|Claude-User|Perplexity-User/i.test(userAgent);
    if (pathname === "/.well-known/agent-skills/index.json") {
      return env.ASSETS.fetch(request);
    }
    if (pathname === "/.well-known/mcp/server-card.json") {
      return env.ASSETS.fetch(request);
    }
    if (pathname === "/.well-known/mcp/docs-server-card.json") {
      return env.ASSETS.fetch(request);
    }
    if (pathname === "/auth.md") {
      return env.ASSETS.fetch(request);
    }
    if (pathname === "/api/llms.txt") {
      return env.ASSETS.fetch(request);
    }
    if (pathname === "/schema-map.xml" || pathname === "/structured-data.jsonl") {
      const asset = await env.ASSETS.fetch(request);
      if (!asset.ok) return asset;
      const headers = new Headers(asset.headers);
      headers.set(
        "Content-Type",
        pathname === "/schema-map.xml" ? "application/xml; charset=utf-8" : "application/x-jsonlines; charset=utf-8"
      );
      return new Response(asset.body, { status: asset.status, headers });
    }
    if (pathname === "/pricing") {
      const asset = await env.ASSETS.fetch(request);
      if (!asset.ok) return asset;
      const headers = new Headers(asset.headers);
      headers.set("Content-Type", "text/html; charset=utf-8");
      headers.set("Cache-Control", "public, max-age=300");
      return new Response(asset.body, { status: asset.status, headers });
    }
    if (pathname === "/docs/api") {
      const asset = await env.ASSETS.fetch(new Request(new URL("/docs/api", request.url), request));
      if (!asset.ok) return asset;
      const headers = new Headers(asset.headers);
      headers.set("Content-Type", "text/html; charset=utf-8");
      headers.set("Cache-Control", "public, max-age=300");
      return new Response(asset.body, { status: asset.status, headers });
    }
    if (pathname === "/" && request.method === "GET" && (wantsMarkdown || isAgentBrowser)) {
      const markdownRequest = new Request(new URL("/index.md", request.url), request);
      const markdownResponse = await proxyToOrigin(markdownRequest, env);
      const headers = new Headers(markdownResponse.headers);
      headers.set("Content-Type", "text/markdown; charset=utf-8");
      headers.set("Vary", "Accept, User-Agent");
      return new Response(markdownResponse.body, { status: markdownResponse.status, headers });
    }
    if (!isBackendPath(pathname)) {
      const knownSpaRoutes = new Set([
        "/", "/home", "/research", "/feedback/survey", "/ideas", "/ideas/qualify",
        "/account", "/account/billing", "/admin/cost", "/login", "/signup", "/auth",
        "/auth/forgot-password", "/auth/reset-password", "/learn-more", "/messages",
        "/pitch-reels", "/shorts", "/discover", "/pitch-shorts", "/portfolio", "/docs",
        "/docs/guide", "/docs/api", "/pricing", "/legal/terms", "/legal/privacy", "/about", "/contact",
        "/privacy", "/developers"
      ]);
      const isIdeaRoute = /^\/ideas\/[^/]+(?:\/[^/]+)?$/.test(pathname);
      const isMessageRoute = /^\/messages\/[^/]+$/.test(pathname);
      const hasAssetExtension = /\.[a-zA-Z0-9]{1,10}$/.test(pathname);
      let response;
      if (knownSpaRoutes.has(pathname) || isIdeaRoute || isMessageRoute) {
        response = await env.ASSETS.fetch(new Request(new URL("/", request.url), request));
      } else {
        response = await env.ASSETS.fetch(request);
        if (response.status === 404 && !hasAssetExtension) {
          const wantsMarkdown = (request.headers.get("accept") || "").includes("text/markdown");
          const content = wantsMarkdown
            ? `# Page not found\n\nThere is no page at \`${pathname}\` on manifeststartup.com.\n\n- [Home](/)\n- [Documentation](/docs)\n- [API reference](/docs/api)\n`
            : `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="robots" content="noindex"><title>Page not found · Manifest</title><h1>Page not found</h1><p>There is no page at this address on Manifest.</p><p><a href="/">Home</a> · <a href="/docs">Documentation</a></p></html>`;
          return new Response(content, {
            status: 404,
            headers: {
              "Content-Type": wantsMarkdown ? "text/markdown; charset=utf-8" : "text/html; charset=utf-8",
              "Cache-Control": "no-store",
              "Vary": "Accept"
            }
          });
        }
      }
      if (pathname === "/index.md" && response.ok) {
        const headers = new Headers(response.headers);
        headers.set("Content-Type", "text/markdown; charset=utf-8");
        headers.set("Vary", "Accept, User-Agent");
        return new Response(response.body, { status: response.status, headers });
      }
      if (pathname === "/" && response.ok) {
        const headers = new Headers(response.headers);
        headers.append("Link", '</llms.txt>; rel="describedby"; type="text/plain"');
        headers.append("Link", '</index.md>; rel="alternate"; type="text/markdown"');
        headers.append("Link", '</openapi.json>; rel="service-desc"; type="application/vnd.oai.openapi+json;version=3.1"');
        headers.append("Link", '</.well-known/api-catalog>; rel="api-catalog"');
        headers.append("Link", '</.well-known/ard.json>; rel="ard"; type="application/json"');
        headers.append("Link", '</sitemap.xml>; rel="sitemap"; type="application/xml"');
        headers.set("Vary", "Accept, User-Agent");
        return new Response(response.body, { status: response.status, headers });
      }
      return response;
    }
    try {
      const file = await serveLegacyFile(request, env, ctx);
      if (file) return file;
      return await proxyToOrigin(request, env);
    } catch (error) {
      console.error("Manifest edge proxy error", error);
      return Response.json({ error: "Service temporarily unavailable" }, { status: 503 });
    }
}

export default {
  async fetch(request, env, ctx) {
    const startedAt = Date.now();
    let response;
    try {
      response = await handleRequest(request, env, ctx);
    } catch (error) {
      console.error("Manifest edge proxy error", error);
      response = Response.json({ error: "Service temporarily unavailable" }, { status: 503 });
    }
    ctx.waitUntil(recordOraRequest(request, response, env, ctx, startedAt).catch((error) => {
      console.warn(`[ora] event recording failed: ${error}`);
    }));
    return response;
  },

  async scheduled(_event, env, ctx) {
    const origin = requireOrigin(env.BACKEND_ORIGIN);
    ctx.waitUntil(
      fetch(new URL("/ping", origin), { headers: { "user-agent": "manifest-edge-keepalive" } })
        .then((r) => console.log("keepalive", r.status))
        .catch((e) => console.error("keepalive failed", e))
    );
  }
};
