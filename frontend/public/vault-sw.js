/*
 * Offline app shell for local vault mode (ADR 0011). Registered only when a browser keeps
 * its ideas in a folder, so the app opens without a connection. Caches the app's own files
 * (the HTML shell and fingerprinted /assets); never ideas, API responses or other sites.
 */
const CACHE = "manifest-shell-v1";
const SHELL = "/index.html";

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      const response = await fetch(SHELL, { cache: "no-cache" });
      if (!response.ok) return;
      await cache.put(SHELL, response.clone());
      // Precache the scripts and styles the shell loads first; the rest is cached on use.
      const html = await response.text();
      const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1]);
      await Promise.all(assets.map((url) => cache.add(url).catch(() => undefined)));
    })(),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)));
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Pages: the network first (new deploys show up), the cached shell when offline.
  if (request.mode === "navigate") {
    event.respondWith(
      (async () => {
        try {
          const response = await fetch(request);
          if (response.ok) (await caches.open(CACHE)).put(SHELL, response.clone());
          return response;
        } catch {
          return (await caches.match(SHELL)) || Response.error();
        }
      })(),
    );
    return;
  }

  // Fingerprinted assets never change: cache first, then keep a copy.
  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(
      (async () => {
        const cached = await caches.match(request);
        if (cached) return cached;
        const response = await fetch(request);
        if (response.ok) (await caches.open(CACHE)).put(request, response.clone());
        return response;
      })(),
    );
  }
});
