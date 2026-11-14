const PROTOCOL_VERSION = "2025-06-18";
const API_ROOT = "/api/v1";
const IDEA_FIELDS = {
  id: { type: "string", description: "Manifest identifier for this idea." },
  title: { type: "string", description: "Founder-provided idea title." },
  description: { type: ["string", "null"], description: "Founder-provided idea description." },
  created_at: { type: ["string", "null"], description: "Creation time in ISO 8601 format." },
  updated_at: { type: ["string", "null"], description: "Most recent update time in ISO 8601 format." },
  is_published: { type: "boolean", description: "Whether this idea is publicly published." },
  has_business_model_canvas: { type: "boolean", description: "Whether a business model canvas exists." },
  has_pitch_deck: { type: "boolean", description: "Whether a pitch deck exists." },
  has_prd: { type: "boolean", description: "Whether a product requirements document exists." },
  has_patent: { type: "boolean", description: "Whether a provisional patent draft exists." },
};
const ideaOutput = {
  type: "object",
  properties: { object: { type: "string" }, ...IDEA_FIELDS },
  required: ["object", "id", "title"],
  additionalProperties: false,
};
const listOutput = {
  type: "object",
  properties: {
    object: { type: "string", description: "Always 'list'." },
    data: { type: "array", items: ideaOutput, description: "Ideas owned by the authenticated API key." },
  },
  required: ["object", "data"],
  additionalProperties: false,
};

const tools = [
  {
    name: "list_ideas",
    description: "Use this when the user asks to review or find their Manifest startup ideas. It returns the idea IDs, titles, descriptions, timestamps, publication state, and document availability for ideas owned by the authenticated API key.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    outputSchema: listOutput,
    annotations: { readOnlyHint: true, destructiveHint: false },
  },
  {
    name: "create_idea",
    description: "Use this after the user asks to save a new startup concept in Manifest. It creates one private idea in the workspace owned by the authenticated API key and returns its ID and document availability flags.",
    inputSchema: {
      type: "object",
      properties: {
        title: { type: "string", minLength: 1, maxLength: 500, description: "Short name for the startup idea." },
        description: { type: "string", description: "Optional explanation of the product, users, and problem it addresses." },
      },
      required: ["title"],
      additionalProperties: false,
    },
    outputSchema: ideaOutput,
    annotations: { readOnlyHint: false, destructiveHint: false },
  },
  {
    name: "get_idea",
    description: "Use this when the user asks about one saved Manifest idea or before changing or generating documents for it. It returns that owner's idea details and flags showing which generated documents are available.",
    inputSchema: { type: "object", properties: { idea_id: { type: "string", description: "The Manifest idea ID returned by list_ideas or create_idea." } }, required: ["idea_id"], additionalProperties: false },
    outputSchema: ideaOutput,
    annotations: { readOnlyHint: true, destructiveHint: false },
  },
  {
    name: "update_idea",
    description: "Use this when the user asks to revise a saved Manifest idea. It changes only the supplied title or description, keeps all other fields intact, and returns the updated idea summary.",
    inputSchema: {
      type: "object",
      properties: {
        idea_id: { type: "string", description: "The Manifest idea ID to update." },
        title: { type: "string", minLength: 1, maxLength: 500, description: "Replacement title; omit to keep the current title." },
        description: { type: "string", description: "Replacement description; omit to keep the current description." },
      },
      required: ["idea_id"],
      additionalProperties: false,
    },
    outputSchema: ideaOutput,
    annotations: { readOnlyHint: false, destructiveHint: false },
  },
  {
    name: "delete_idea",
    description: "Use this only after the user explicitly confirms permanent removal of a specific saved idea. It deletes that idea from the owner's workspace and returns a deletion confirmation with the ID.",
    inputSchema: { type: "object", properties: { idea_id: { type: "string", description: "The Manifest idea ID whose deletion the user confirmed." } }, required: ["idea_id"], additionalProperties: false },
    outputSchema: {
      type: "object",
      properties: {
        deleted: { type: "boolean", description: "True when the idea was deleted." },
        id: { type: "string", description: "The ID of the deleted idea." },
      },
      required: ["deleted", "id"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: true },
  },
  {
    name: "generate_documents",
    description: "Use this when the user requests new startup planning drafts for a saved Manifest idea. It synchronously generates the selected business model canvas, pitch deck, PRD, or provisional patent draft and reports each document's result status.",
    inputSchema: {
      type: "object",
      properties: {
        idea_id: { type: "string", description: "The Manifest idea ID to generate documents for." },
        document_types: {
          type: "array",
          description: "One or more supported draft document types to generate.",
          items: { type: "string", enum: ["business_model_canvas", "pitch_deck", "prd", "patent"], description: "Supported draft type." },
        },
      },
      required: ["idea_id", "document_types"],
      additionalProperties: false,
    },
    outputSchema: {
      type: "object",
      properties: {
        object: { type: "string", description: "Always 'generation_result'." },
        idea_id: { type: "string", description: "The Manifest idea ID." },
        documents: { type: "object", additionalProperties: true, description: "Generation status keyed by document type." },
        status: { type: "string", description: "Overall generation status." },
      },
      required: ["object", "idea_id", "documents", "status"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: false },
  },
  {
    name: "get_usage",
    description: "Use this when the user asks about API consumption or plan capacity. It returns the account tier, monthly request and token usage, request allowance, and per-minute rate limit for the API key owner.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    outputSchema: {
      type: "object",
      properties: {
        object: { type: "string", description: "Always 'usage'." },
        tier: { type: "string", description: "Current API billing tier." },
        requests_used: { type: "integer", description: "Requests used this month." },
        requests_limit: { type: "integer", description: "Monthly request allowance; -1 means unlimited." },
        tokens_used: { type: "integer", description: "Tokens used this month." },
        rate_limit_per_minute: { type: "integer", description: "Maximum requests allowed per minute." },
      },
      required: ["tier", "requests_used", "requests_limit", "tokens_used", "rate_limit_per_minute"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, destructiveHint: false },
  },
];

function jsonRpcError(id, code, message) {
  return response({ jsonrpc: "2.0", id: id ?? null, error: { code, message } });
}

function response(payload, status = 200, protocolVersion = PROTOCOL_VERSION) {
  return new Response(payload == null ? null : JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "access-control-allow-origin": "*",
      "access-control-allow-headers": "authorization, content-type, mcp-protocol-version, accept",
      "access-control-allow-methods": "GET, POST, OPTIONS",
      "mcp-protocol-version": protocolVersion,
    },
  });
}

function textResult(value, isError = false) {
  return { content: [{ type: "text", text: JSON.stringify(value) }], isError, structuredContent: value };
}

function apiRequestFor(request, path, method, body) {
  const url = new URL(`${API_ROOT}${path}`, request.url);
  const headers = new Headers({ accept: "application/json" });
  const authorization = request.headers.get("authorization");
  if (authorization) headers.set("authorization", authorization);
  if (body !== undefined) headers.set("content-type", "application/json");
  return new Request(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function invokeTool(request, name, args, proxyApi) {
  const id = encodeURIComponent(String(args.idea_id ?? ""));
  switch (name) {
    case "list_ideas":
      return proxyApi(apiRequestFor(request, "/ideas", "GET"));
    case "create_idea":
      return proxyApi(apiRequestFor(request, "/ideas", "POST", args));
    case "get_idea":
      return proxyApi(apiRequestFor(request, `/ideas/${id}`, "GET"));
    case "update_idea": {
      const { idea_id, ...patch } = args;
      return proxyApi(apiRequestFor(request, `/ideas/${id}`, "PATCH", patch));
    }
    case "delete_idea":
      return proxyApi(apiRequestFor(request, `/ideas/${id}`, "DELETE"));
    case "generate_documents": {
      const { idea_id, ...body } = args;
      return proxyApi(apiRequestFor(request, `/ideas/${id}/generate`, "POST", body));
    }
    case "get_usage":
      return proxyApi(apiRequestFor(request, "/usage", "GET"));
    default:
      return null;
  }
}

/** Stateless JSON-RPC endpoint backed by the existing, permission-checked REST API. */
export async function handleManifestMcpRequest(request, proxyApi) {
  if (request.method === "OPTIONS") return response(null, 204);
  if (request.method === "GET") {
    if ((request.headers.get("accept") ?? "").includes("text/event-stream")) {
      return response({ error: "Server-initiated event streams are not supported." }, 405);
    }
    return response({ name: "Manifest MCP", transport: "streamable-http", endpoint: "/mcp" });
  }
  if (request.method !== "POST") return new Response("Method not allowed", { status: 405, headers: { allow: "GET, POST, OPTIONS" } });

  const length = Number(request.headers.get("content-length") ?? 0);
  if (length > 32_768) return response({ error: "Request body too large." }, 413);
  let message;
  try {
    const reader = request.body?.getReader();
    if (!reader) return jsonRpcError(null, -32700, "Parse error");
    const chunks = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 32_768) {
        await reader.cancel();
        return response({ error: "Request body too large." }, 413);
      }
      chunks.push(value);
    }
    const body = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      body.set(chunk, offset);
      offset += chunk.byteLength;
    }
    message = JSON.parse(new TextDecoder().decode(body));
  } catch {
    return jsonRpcError(null, -32700, "Parse error");
  }
  if (!message || Array.isArray(message) || typeof message !== "object" || message.jsonrpc !== "2.0" || typeof message.method !== "string") {
    return jsonRpcError(message?.id, -32600, "Invalid Request");
  }
  if (message.method.startsWith("notifications/")) return response(null, 202);

  switch (message.method) {
    case "initialize":
      return response({
        jsonrpc: "2.0",
        id: message.id,
        result: {
          protocolVersion: PROTOCOL_VERSION,
          capabilities: { tools: {} },
          serverInfo: { name: "manifest-api", title: "Manifest API", version: "1.0.0" },
          instructions: "Use a Manifest API key in the Authorization: Bearer header. Tools operate only on data owned by that key. Ask for confirmation before delete_idea.",
        },
      });
    case "ping":
      return response({ jsonrpc: "2.0", id: message.id, result: {} });
    case "tools/list":
      return response({ jsonrpc: "2.0", id: message.id, result: { tools } });
    case "tools/call": {
      const name = message.params?.name;
      const args = message.params?.arguments ?? {};
      if (typeof name !== "string" || !tools.some((tool) => tool.name === name)) {
        return jsonRpcError(message.id, -32602, "Unknown tool");
      }
      if (!args || typeof args !== "object" || Array.isArray(args)) {
        return jsonRpcError(message.id, -32602, "Tool arguments must be an object");
      }
      try {
        const upstream = await invokeTool(request, name, args, proxyApi);
        if (!upstream) return jsonRpcError(message.id, -32602, "Unknown tool");
        const payload = await upstream.json().catch(() => ({ error: "Invalid JSON from Manifest API" }));
        const result = textResult(payload, !upstream.ok);
        if (!upstream.ok) result.structuredContent = { status: upstream.status, ...payload };
        return response({ jsonrpc: "2.0", id: message.id, result });
      } catch {
        return response({
          jsonrpc: "2.0",
          id: message.id,
          result: textResult({ error: "Manifest API request failed." }, true),
        });
      }
    }
    default:
      return jsonRpcError(message.id, -32601, "Method not found");
  }
}
