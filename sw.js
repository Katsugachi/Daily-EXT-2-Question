const CACHE_NAME = "daily-ext2-runtime-v1";
const CORE_ASSETS = [
  "./",
  "index.html",
  "styles.css",
  "fonts.css",
  "fonts/roboto-latin-400-normal.woff2",
  "fonts/roboto-latin-500-normal.woff2",
  "fonts/roboto-latin-700-normal.woff2",
  "google-product-tokens.css",
  "google-product-components.css",
  "mathjax-config.js",
  "app.js",
  "data/questions.json"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(CORE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))))
      .then(() => self.clients.claim())
  );
});

async function networkFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    const response = await fetch(request, { cache: "no-store" });
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await cache.match(request);
    if (cached) return cached;
    if (request.mode === "navigate") {
      const shell = await cache.match("index.html") || await cache.match("./");
      if (shell) return shell;
    }
    throw error;
  }
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
  event.respondWith(networkFirst(event.request));
});
