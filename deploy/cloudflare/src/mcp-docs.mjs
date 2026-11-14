const VERSION = "2025-06-18";
const DOCUMENTS = {
  api: { title: "Manifest API reference", path: "/docs/api.md" },
  pricing: { title: "Manifest API pricing and limits", path: "/pricing.md" },
  agents: { title: "Manifest agent guide", path: "/agents.md" },
  home: { title: "About Manifest", path: "/index.md" },
  privacy: { title: "Manifest privacy policy", path: "/legal/privacy.md" },
};
const tools = [
  {
    name: "list_manifest_documents",
    description: "Use when an agent needs to discover available Manifest product documentation. Returns document identifiers, titles, and public URLs for the API, pricing, agent guide, home, and privacy policy.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    outputSchema: {
      type: "object",
      properties: { documents: { type: "array", items: { type: "object", properties: { id: { type: "string" }, title: { type: "string" }, url: { type: "string" } }, required: ["id", "title", "url"] } } },
      required: ["documents"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, destructiveHint: false },
  },
  {
    name: "read_manifest_document",
    description: "Use to answer a question that depends on a specific Manifest document. Returns the full current Markdown text for the selected public page, so cite its links and details directly.",
    inputSchema: {
      type: "object",
      properties: { document_id: { type: "string", enum: Object.keys(DOCUMENTS), description: "Document identifier from list_manifest_documents." } },
      required: ["document_id"],
      additionalProperties: false,
    },
    outputSchema: {
      type: "object",
      properties: { id: { type: "string" }, title: { type: "string" }, url: { type: "string" }, markdown: { type: "string" } },
      required: ["id", "title", "url", "markdown"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, destructiveHint: false },
  },
];

function reply(payload, status = 200) {
  return new Response(payload == null ? null : JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "access-control-allow-origin": "*",
      "access-control-allow-headers": "content-type, mcp-protocol-version, accept",
      "access-control-allow-methods": "GET, POST, OPTIONS",
      "mcp-protocol-version": VERSION,
    },
  });
}

function error(id, code, message) {
  return reply({ jsonrpc: "2.0", id: id ?? null, error: { code, message } });
}

function resultText(value) {
  return { content: [{ type: "text", text: JSON.stringify(value) }], structuredContent: value };
}

export async function handleManifestDocsMcpRequest(request, fetchDocument) {
  if (request.method === "OPTIONS") return reply(null, 204);
  if (request.method === "GET") {
    if ((request.headers.get("accept") ?? "").includes("text/event-stream")) return reply({ error: "Server-initiated event streams are not supported." }, 405);
    return reply({ name: "Manifest documentation MCP", transport: "streamable-http", endpoint: "/docs/mcp" });
  }
  if (request.method !== "POST") return new Response("Method not allowed", { status: 405, headers: { allow: "GET, POST, OPTIONS" } });

  let message;
  try {
    const reader = request.body?.getReader();
    if (!reader) return error(null, -32700, "Parse error");
    const chunks = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 16_384) {
        await reader.cancel();
        return reply({ error: "Request body too large." }, 413);
      }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    message = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return error(null, -32700, "Parse error");
  }
  if (!message || Array.isArray(message) || message.jsonrpc !== "2.0" || typeof message.method !== "string") return error(message?.id, -32600, "Invalid Request");
  if (message.method.startsWith("notifications/")) return reply(null, 202);

  if (message.method === "initialize") {
    return reply({ jsonrpc: "2.0", id: message.id, result: {
      protocolVersion: VERSION,
      capabilities: { tools: {} },
      serverInfo: { name: "manifest-docs", title: "Manifest Documentation", version: "1.0.0" },
      instructions: "This read-only server provides public Manifest documentation. It does not access user workspaces or perform product actions.",
    } });
  }
  if (message.method === "ping") return reply({ jsonrpc: "2.0", id: message.id, result: {} });
  if (message.method === "tools/list") return reply({ jsonrpc: "2.0", id: message.id, result: { tools } });
  if (message.method !== "tools/call") return error(message.id, -32601, "Method not found");

  const name = message.params?.name;
  const args = message.params?.arguments ?? {};
  if (name === "list_manifest_documents") {
    const documents = Object.entries(DOCUMENTS).map(([id, doc]) => ({ id, title: doc.title, url: `https://manifeststartup.com${doc.path}` }));
    return reply({ jsonrpc: "2.0", id: message.id, result: resultText({ documents }) });
  }
  if (name !== "read_manifest_document" || typeof args.document_id !== "string" || !DOCUMENTS[args.document_id]) return error(message.id, -32602, "Unknown tool or document");
  const doc = DOCUMENTS[args.document_id];
  try {
    const upstream = await fetchDocument(new Request(new URL(doc.path, request.url), { headers: { accept: "text/markdown" } }));
    if (!upstream.ok) return reply({ jsonrpc: "2.0", id: message.id, result: { ...resultText({ error: "Document unavailable." }), isError: true } });
    const markdown = await upstream.text();
    if (markdown.length > 256_000) return reply({ jsonrpc: "2.0", id: message.id, result: { ...resultText({ error: "Document exceeds the size limit." }), isError: true } });
    const result = { id: args.document_id, title: doc.title, url: `https://manifeststartup.com${doc.path}`, markdown };
    return reply({ jsonrpc: "2.0", id: message.id, result: resultText(result) });
  } catch {
    return reply({ jsonrpc: "2.0", id: message.id, result: { ...resultText({ error: "Document unavailable." }), isError: true } });
  }
}
