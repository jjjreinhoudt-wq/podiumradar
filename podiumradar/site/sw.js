/* Podiumradar service worker.
   Verhoog VERSION bij elke wijziging aan dit bestand of aan de lijst SHELL.
   index.html, app.js, pwa.js en data.json gaan altijd eerst naar het netwerk
   (network-first), dus updates komen direct door; de cache is alleen voor offline.
   data.json en spotify.json staan bewust NIET in SHELL: de pagina haalt ze zelf op (anders eerst twee keer 1 MB), de kopie
   voor offline wordt gemaakt bij het eerste gewone verzoek. */
const VERSION = "v6";
const CACHE = "podiumradar-" + VERSION;
const FONTS = "podiumradar-fonts"; // los van VERSION: fonts veranderen niet
const SHELL = ["./", "index.html", "over.html", "app.js", "pwa.js", "manifest.json", "fonts.css", "nl.json",
  "fonts/archivo-latin.woff2", "fonts/archivo-latin-ext.woff2",
  "icon.svg", "icon-180.png", "icon-192.png", "icon-512.png", "icon-maskable-512.png"];
const FRESH = /\/(?:index\.html|app\.js|pwa\.js|data\.json|spotify\.json)$/;

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE)
    .then(c => Promise.all(SHELL.map(u => c.add(new Request(u, { cache: "reload" })).catch(() => {}))))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k.startsWith("podiumradar-") && k !== CACHE && k !== FONTS).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Kopie bewaren onder de URL zonder querystring
async function put(cacheName, req, res) {
  if (!res || !(res.ok || res.type === "opaque")) return;
  const c = await caches.open(cacheName);
  await c.put(req.url.split("?")[0], res);
}

async function networkFirst(e, req) {
  try {
    // Altijd bij de server navragen (ook langs de HTTP-cache van de browser);
    // cache:"no-store" van de app (data.json) blijft no-store.
    const res = await fetch(req.url, { cache: req.cache === "no-store" ? "no-store" : "no-cache", credentials: "same-origin" });
    if (res.ok) e.waitUntil(put(CACHE, req, res.clone()));
    return res;
  } catch (err) {
    const c = await caches.open(CACHE);
    const hit = await c.match(req, { ignoreSearch: true })
      || (req.mode === "navigate" && (await c.match("./") || await c.match("index.html")));
    if (hit) return hit;
    throw err;
  }
}

async function staleWhileRevalidate(e, req) {
  const c = await caches.open(CACHE);
  const hit = await c.match(req, { ignoreSearch: true });
  const net = fetch(req).then(res => { if (res.ok) put(CACHE, req, res.clone()); return res; });
  if (hit) { e.waitUntil(net.catch(() => {})); return hit; }
  return net;
}

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // externe verzoeken niet onderscheppen
  if (!url.pathname.startsWith(new URL(self.registration.scope).pathname)) return;
  if (url.pathname.endsWith("/sw.js")) return;
  if (req.mode === "navigate" || url.pathname.endsWith("/") || FRESH.test(url.pathname)) e.respondWith(networkFirst(e, req));
  else e.respondWith(staleWhileRevalidate(e, req));
});
