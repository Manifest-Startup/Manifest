const ORA_INGEST_URL = "https://ingest.ora.ai/v1/events";
const TRANSMITTER = "cloudflare-worker/4.7.0";
const MAX_BATCH = 1000;
const MAX_BATCH_AGE_MS = 5000;
const MAX_QUERY_CHARS = 2048;
const ASSET_EXTENSIONS = new Set([
  "js", "mjs", "css", "map", "png", "jpg", "jpeg", "gif", "svg", "webp", "avif", "ico",
  "woff", "woff2", "ttf", "otf", "eot", "mp4", "webm", "mp3", "wav",
]);
const KEEP_PARAMS = ["utm_source", "utm_medium", "utm_campaign", "ref", "source"];

let buffer = [];
let flushPending = false;

function reportable(request) {
  if (!/^(GET|HEAD|POST|PUT|PATCH|DELETE)$/.test(request.method)) return false;
  const url = new URL(request.url);
  if (url.pathname === "/__ora/status") return false;
  const extension = url.pathname.slice(url.pathname.lastIndexOf(".") + 1).toLowerCase();
  if (url.pathname.includes(".") && ASSET_EXTENSIONS.has(extension)) return false;
  const destination = request.headers.get("sec-fetch-dest");
  if (destination !== null && !["document", "iframe", "frame"].includes(destination)) return false;
  const purpose = `${request.headers.get("sec-purpose") ?? ""} ${request.headers.get("purpose") ?? ""}`;
  return !purpose.toLowerCase().includes("prefetch");
}

function safeQuery(url) {
  const allowed = new URLSearchParams();
  for (const name of KEEP_PARAMS) {
    const value = url.searchParams.get(name);
    if (value) allowed.set(name, value.slice(0, 128));
  }
  let query = allowed.toString();
  while (query.length > MAX_QUERY_CHARS) {
    const [name, value] = [...allowed].reduce((largest, item) => item[1].length > largest[1].length ? item : largest);
    if (!value) break;
    allowed.set(name, value.slice(0, Math.max(0, value.length - (query.length - MAX_QUERY_CHARS))));
    query = allowed.toString();
  }
  return query || undefined;
}

async function dailyVisitorHash(request, salt) {
  if (!salt) return undefined;
  const ip = request.headers.get("cf-connecting-ip") ?? "";
  const ua = request.headers.get("user-agent") ?? "";
  const day = new Date().toISOString().slice(0, 10);
  const payload = new TextEncoder().encode(`${ip}|${ua}|${day}|${salt}`);
  const digest = await crypto.subtle.digest("SHA-256", payload);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function flush(env) {
  if (!env.ORA_INGEST_KEY || buffer.length === 0) return;
  const batch = buffer.slice(0, MAX_BATCH);
  buffer = buffer.slice(MAX_BATCH);
  try {
    const response = await fetch(ORA_INGEST_URL, {
      method: "POST",
      headers: {
        authorization: `Bearer ${env.ORA_INGEST_KEY}`,
        "content-type": "application/x-ndjson",
        "x-ora-batch-id": crypto.randomUUID(),
        "x-ora-transmitter": TRANSMITTER,
      },
      body: batch.map((event) => JSON.stringify(event)).join("\n"),
      signal: AbortSignal.timeout(5000),
    });
    if (response.status === 202) return;
    console.warn(`[ora] ingest returned ${response.status}`);
    if (response.status === 429 || response.status >= 500) buffer = batch.concat(buffer).slice(0, MAX_BATCH * 5);
  } catch (error) {
    console.warn(`[ora] ingest request failed: ${error}`);
    buffer = batch.concat(buffer).slice(0, MAX_BATCH * 5);
  }
}

function scheduleFlush(ctx, env) {
  if (flushPending) return;
  flushPending = true;
  ctx.waitUntil((async () => {
    await new Promise((resolve) => setTimeout(resolve, MAX_BATCH_AGE_MS));
    flushPending = false;
    await flush(env);
  })());
}

export async function recordOraRequest(request, response, env, ctx, startedAt) {
  if (!env.ORA_INGEST_KEY || !reportable(request)) return;
  const url = new URL(request.url);
  let referer;
  try {
    const value = request.headers.get("referer");
    if (value) referer = new URL(value).origin;
  } catch {
    referer = undefined;
  }
  let query = safeQuery(url);
  const event = {
    id: crypto.randomUUID(),
    ts: new Date().toISOString(),
    host: url.hostname,
    path: url.pathname.slice(0, 2048),
    query: query ? `?${query}` : undefined,
    method: request.method,
    status: response.status,
    ua: (request.headers.get("user-agent") ?? "").slice(0, 512),
    referer,
    vh: await dailyVisitorHash(request, env.ORA_SALT),
    cc: request.headers.get("cf-ipcountry") ?? undefined,
    durMs: Math.max(0, Date.now() - startedAt),
    headers: {
      accept: request.headers.get("accept") ?? undefined,
      "accept-language": request.headers.get("accept-language") ?? undefined,
      "sec-fetch-mode": request.headers.get("sec-fetch-mode") ?? undefined,
      "sec-fetch-dest": request.headers.get("sec-fetch-dest") ?? undefined,
    },
  };
  buffer.push(event);
  if (buffer.length >= MAX_BATCH) await flush(env);
  else scheduleFlush(ctx, env);
}
