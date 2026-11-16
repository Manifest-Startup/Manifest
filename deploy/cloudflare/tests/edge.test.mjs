import assert from "node:assert/strict";
import test from "node:test";
import {
  buildOriginRequest,
  isBackendPath,
  legacyFileUrl,
  requireOrigin,
  rewriteLocation
} from "../src/edge.mjs";

test("routes backend paths to origin and everything else to static assets", () => {
  for (const p of ["/graphql", "/graphql/", "/socket.io/?EIO=4", "/api/v1/ideas", "/auth/login",
    "/scim/v2/Users", "/trust", "/openapi.json", "/.well-known/api-catalog", "/agents.md",
    "/internal/openapi.json", "/ping", "/health", "/healthz", "/generated/pdfs/a/b.pdf",
    "/api/integrations/open-media/connect", "/api/integrations/open-media/callback",
    "/api/webhooks/open-media"]) {
    assert.equal(isBackendPath(p.split("?")[0]), true, p);
  }
  for (const p of ["/", "/ideas/123", "/assets/index.js", "/apiary", "/authors", "/trusty", "/robots.txt",
    "/oauth/open-media-client.json"]) {
    assert.equal(isBackendPath(p), false, p);
  }
});

test("requires an https origin", () => {
  assert.throws(() => requireOrigin("http://x.onrender.com"), /HTTPS/);
  assert.throws(() => requireOrigin("nope"), /valid URL/);
  assert.equal(requireOrigin("https://x.onrender.com").host, "x.onrender.com");
});

test("maps legacy generated file URLs to public storage safely", () => {
  const base = "https://ref.supabase.co/storage/v1/object/public/";
  assert.equal(legacyFileUrl("/generated/pdfs/patents/u/spec.pdf", base),
    "https://ref.supabase.co/storage/v1/object/public/patents/u/spec.pdf");
  assert.equal(legacyFileUrl("/generated/pdfs/patents/u/spec.pdf", ""), null);
  assert.equal(legacyFileUrl("/generated/pdfs/onlybucket", base), null);
  assert.equal(legacyFileUrl("/generated/pdfs/a/../secret", base), null);
  assert.equal(legacyFileUrl("/api/x", base), null);
});

test("forwards to origin with trusted forwarding headers", async () => {
  const req = new Request("https://manifeststartup.com/graphql?x=1", {
    method: "POST",
    headers: { "x-forwarded-host": "evil", "x-forwarded-for": "6.6.6.6", "x-manifest-edge": "forged",
      "cf-connecting-ip": "203.0.113.9", cookie: "s=1" },
    body: "{}"
  });
  const out = buildOriginRequest(req, new URL("https://manifest-backend.onrender.com"), "edge-secret");
  assert.equal(out.url, "https://manifest-backend.onrender.com/graphql?x=1");
  assert.equal(out.headers.get("x-forwarded-host"), "manifeststartup.com");
  assert.equal(out.headers.get("x-forwarded-proto"), "https");
  assert.equal(out.headers.get("x-forwarded-for"), "203.0.113.9");
  assert.equal(out.headers.get("cookie"), "s=1");
  assert.equal(out.headers.get("x-manifest-edge"), "edge-secret");
  const unsigned = buildOriginRequest(new Request("https://manifeststartup.com/ping",
    { headers: { "x-manifest-edge": "forged" } }), new URL("https://o.example"));
  assert.equal(unsigned.headers.get("x-manifest-edge"), null);
  assert.equal(await out.text(), "{}");
});

test("rewrites origin redirects to the public host only", () => {
  const origin = new URL("https://manifest-backend.onrender.com");
  const pub = new URL("https://manifeststartup.com/auth/login");
  const r1 = rewriteLocation(new Response(null, { status: 302, headers: { location: "https://manifest-backend.onrender.com/app?a=1" } }), origin, pub);
  assert.equal(r1.headers.get("location"), "https://manifeststartup.com/app?a=1");
  const r2 = rewriteLocation(new Response(null, { status: 302, headers: { location: "https://accounts.google.com/o" } }), origin, pub);
  assert.equal(r2.headers.get("location"), "https://accounts.google.com/o");
});
