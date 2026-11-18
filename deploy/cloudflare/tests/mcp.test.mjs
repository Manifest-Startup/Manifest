import assert from "node:assert/strict";
import { test } from "node:test";
import generated from "../src/mcp-tools.generated.json" with { type: "json" };
import { handleManifestMcpRequest } from "../src/mcp.mjs";

const URL_MCP = "https://manifeststartup.com/mcp";

function rpc(method, params, token = "session.jwt.token") {
  const headers = { "content-type": "application/json", accept: "application/json, text/event-stream", "cf-connecting-ip": "203.0.113.7" };
  if (token) headers.authorization = `Bearer ${token}`;
  return new Request(URL_MCP, {
    method: "POST",
    headers,
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  });
}

function recorder(reply = { data: {} }, status = 200) {
  const calls = [];
  const proxy = async (request) => {
    calls.push({ url: request.url, method: request.method, auth: request.headers.get("authorization"), ip: request.headers.get("cf-connecting-ip"), body: request.body ? await request.json() : null });
    return Response.json(typeof reply === "function" ? reply(calls.at(-1)) : reply, { status });
  };
  return { calls, proxy };
}

test("requests without a token get an OAuth challenge", async () => {
  const res = await handleManifestMcpRequest(rpc("initialize", {}, null), recorder().proxy);
  assert.equal(res.status, 401);
  assert.match(res.headers.get("www-authenticate"), /resource_metadata="https:\/\/manifeststartup.com\/.well-known\/oauth-protected-resource\/mcp"/);
});

test("a signed-in agent sees every generated tool, without call internals", async () => {
  const res = await handleManifestMcpRequest(rpc("tools/list"), recorder().proxy);
  const { result } = await res.json();
  assert.equal(result.tools.length, generated.tools.length);
  assert.ok(result.tools.length > 100);
  assert.ok(result.tools.every((t) => !("_call" in t) && t.inputSchema.type === "object"));
  const names = new Set(result.tools.map((t) => t.name));
  for (const name of ["create_idea", "generate_pitch_deck", "send_message", "my_portfolio", "invite_collaborator"]) {
    assert.ok(names.has(name), name);
  }
  for (const excluded of ["start_guest_session", "open_media_realtime_token", "save_openai_api_key"]) {
    assert.ok(!names.has(excluded), excluded);
  }
});

test("API keys keep the original small tool set", async () => {
  const res = await handleManifestMcpRequest(rpc("tools/list", {}, "manifest_sk_abc"), recorder().proxy);
  const { result } = await res.json();
  assert.ok(result.tools.some((t) => t.name === "generate_documents"));
  assert.ok(result.tools.length < 10);
});

test("initialize negotiates a supported protocol version", async () => {
  const res = await handleManifestMcpRequest(rpc("initialize", { protocolVersion: "2025-11-25" }), recorder().proxy);
  const { result } = await res.json();
  assert.equal(result.protocolVersion, "2025-11-25");
  assert.equal(result.serverInfo.name, "manifest");
  assert.match(result.instructions, /confirm: true/);
});

test("GraphQL tools forward the caller's token and variables", async () => {
  const { calls, proxy } = recorder({ data: { createIdea: { ideaId: "i1", title: "Solar" } } });
  const res = await handleManifestMcpRequest(rpc("tools/call", { name: "create_idea", arguments: { title: "Solar" } }), proxy);
  const { result } = await res.json();
  assert.equal(calls[0].url, "https://manifeststartup.com/graphql");
  assert.equal(calls[0].auth, "Bearer session.jwt.token");
  assert.equal(calls[0].ip, "203.0.113.7");
  assert.match(calls[0].body.query, /^mutation CreateIdea\(/);
  assert.deepEqual(calls[0].body.variables, { title: "Solar" });
  assert.equal(result.isError, false);
  assert.deepEqual(result.structuredContent, { createIdea: { ideaId: "i1", title: "Solar" } });
});

test("destructive tools need confirm: true and never call the backend without it", async () => {
  const { calls, proxy } = recorder({ data: { deleteIdea: true } });
  const first = await (await handleManifestMcpRequest(rpc("tools/call", { name: "delete_idea", arguments: { ideaId: "i1" } }), proxy)).json();
  assert.equal(calls.length, 0);
  assert.equal(first.result.structuredContent.needs_confirmation, true);
  await handleManifestMcpRequest(rpc("tools/call", { name: "delete_idea", arguments: { ideaId: "i1", confirm: true } }), proxy);
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].body.variables, { ideaId: "i1" });
});

test("unknown or missing arguments are explained", async () => {
  const { calls, proxy } = recorder();
  const bad = await (await handleManifestMcpRequest(rpc("tools/call", { name: "create_idea", arguments: { nope: 1 } }), proxy)).json();
  assert.equal(bad.result.isError, true);
  assert.match(bad.result.content[0].text, /Unknown argument|Missing required/);
  assert.equal(calls.length, 0);
});

test("REST tools fill path parameters and the body", async () => {
  const { calls, proxy } = recorder({ ok: true });
  await handleManifestMcpRequest(rpc("tools/call", { name: "keys_delete_client", arguments: { client_id: "a/b", confirm: true } }), proxy);
  assert.equal(calls[0].method, "DELETE");
  assert.equal(calls[0].url, "https://manifeststartup.com/api/keys/clients/a%2Fb");
  await handleManifestMcpRequest(rpc("tools/call", { name: "privacy_set_consent", arguments: { analytics_enabled: false } }), proxy);
  assert.deepEqual(calls[1].body, { analytics_enabled: false });
});

test("GraphQL errors become tool errors; an expired session asks for sign-in again", async () => {
  const failing = recorder({ errors: [{ message: "Idea not found" }] });
  const res = await (await handleManifestMcpRequest(rpc("tools/call", { name: "idea", arguments: { ideaId: "x" } }), failing.proxy)).json();
  assert.equal(res.result.isError, true);
  assert.match(res.result.content[0].text, /Idea not found/);
  const expired = recorder({ detail: "expired" }, 401);
  const challenge = await handleManifestMcpRequest(rpc("tools/call", { name: "me", arguments: {} }), expired.proxy);
  assert.equal(challenge.status, 401);
  assert.ok(challenge.headers.get("www-authenticate"));
});

test("no tool selects credentials into agent context", () => {
  for (const tool of generated.tools) {
    if (tool._call.via !== "graphql") continue;
    assert.doesNotMatch(tool._call.document, /\b(accessToken|refreshToken|mergeSecret|apiKey|password)\b/, tool.name);
  }
});

test("every write tool says so in its annotations", () => {
  for (const tool of generated.tools) {
    const a = tool.annotations;
    assert.equal(typeof a.readOnlyHint, "boolean");
    if (a.destructiveHint) assert.ok("confirm" in tool.inputSchema.properties, tool.name);
    if (tool._call.via === "rest") assert.equal(a.readOnlyHint, tool._call.method === "GET", tool.name);
  }
});
