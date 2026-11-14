const modelContext = document.modelContext;

if (modelContext && typeof modelContext.registerTool === "function") {
  const controller = new AbortController();
  let appToolsRegistered = false;
  const readPublicPage = async (path, signal) => {
    const response = await fetch(path, { headers: { Accept: "text/markdown" }, signal });
    if (!response.ok) throw new Error(`Manifest returned HTTP ${response.status}`);
    return response.text();
  };

  void Promise.all([
    document.modelContext.registerTool({
      name: "read_manifest_api_docs",
      title: "Read Manifest API documentation",
      description: "Use when answering questions about Manifest API endpoints, authentication, scopes, request formats, or errors. Returns the public API reference as Markdown.",
      inputSchema: { type: "object", properties: {}, additionalProperties: false },
      annotations: { readOnlyHint: true, consequentialHint: false },
      async execute(_input, options) {
        return { content: [{ type: "text", text: await readPublicPage("/docs/api.md", options?.signal) }] };
      },
    }, { signal: controller.signal }),
    document.modelContext.registerTool({
      name: "read_manifest_pricing",
      title: "Read Manifest API pricing",
      description: "Use when the user asks about Manifest API plans, request limits, or usage tiers. Returns the current public pricing and rate-limit information as Markdown.",
      inputSchema: { type: "object", properties: {}, additionalProperties: false },
      annotations: { readOnlyHint: true, consequentialHint: false },
      async execute(_input, options) {
        return { content: [{ type: "text", text: await readPublicPage("/pricing.md", options?.signal) }] };
      },
    }, { signal: controller.signal }),
  ]).catch(() => {
    // WebMCP is optional; browsers without it continue to use the site normally.
  });

  const registerAppTools = () => {
    const api = window.manifestWebMcpApi;
    if (!api || appToolsRegistered) return;
    appToolsRegistered = true;
    void Promise.all([
      modelContext.registerTool({
        name: "list_manifest_ideas",
        title: "List workspace ideas",
        description: "Lists ideas in the signed-in user's Manifest workspace. Requires an authenticated session; only ideas available to that account are returned.",
        inputSchema: { type: "object", properties: {}, additionalProperties: false },
        annotations: { readOnlyHint: true, consequentialHint: false },
        async execute(_input, options) {
          if (options?.signal?.aborted) throw new Error("Request cancelled.");
          return { content: [{ type: "text", text: JSON.stringify(await api.listIdeas()) }] };
        },
      }, { signal: controller.signal }),
      modelContext.registerTool({
        name: "read_manifest_idea",
        title: "Read a workspace idea",
        description: "Reads one idea by ID from the signed-in user's Manifest workspace. Requires an authenticated session and access to the idea.",
        inputSchema: { type: "object", properties: { ideaId: { type: "string", description: "The Manifest idea ID." } }, required: ["ideaId"], additionalProperties: false },
        annotations: { readOnlyHint: true, consequentialHint: false },
        async execute(input, options) {
          if (options?.signal?.aborted) throw new Error("Request cancelled.");
          return { content: [{ type: "text", text: JSON.stringify(await api.readIdea(input.ideaId)) }] };
        },
      }, { signal: controller.signal }),
      modelContext.registerTool({
        name: "create_manifest_idea",
        title: "Create a workspace idea",
        description: "Creates an idea in the signed-in user's Manifest workspace. This changes workspace data and requires an authenticated session.",
        inputSchema: { type: "object", properties: { title: { type: "string", description: "The new idea's title." }, description: { type: "string", description: "Optional idea description." } }, required: ["title"], additionalProperties: false },
        annotations: { readOnlyHint: false, consequentialHint: true },
        async execute(input, options) {
          if (options?.signal?.aborted) throw new Error("Request cancelled.");
          return { content: [{ type: "text", text: JSON.stringify(await api.createIdea(input.title, input.description)) }] };
        },
      }, { signal: controller.signal }),
      modelContext.registerTool({
        name: "update_manifest_idea",
        title: "Update a workspace idea",
        description: "Updates the title or description of an idea in the signed-in user's Manifest workspace. This changes workspace data and requires an authenticated session.",
        inputSchema: { type: "object", properties: { ideaId: { type: "string", description: "The Manifest idea ID." }, title: { type: "string", description: "Replacement title." }, description: { type: "string", description: "Replacement description." } }, required: ["ideaId"], additionalProperties: false },
        annotations: { readOnlyHint: false, consequentialHint: true },
        async execute(input, options) {
          if (options?.signal?.aborted) throw new Error("Request cancelled.");
          return { content: [{ type: "text", text: JSON.stringify(await api.updateIdea(input.ideaId, input.title, input.description)) }] };
        },
      }, { signal: controller.signal }),
    ]).catch(() => {
      appToolsRegistered = false;
    });
  };
  window.addEventListener("manifest:webmcp-ready", registerAppTools);
  registerAppTools();
}
