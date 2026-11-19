/* Service worker du pilotage MDB : l'application s'ouvre même sans réseau (dernière version vue).
   Les données (API) ne sont jamais mises en cache ici : l'application garde sa propre copie locale. */
const CACHE = "pilotage-mdb-v1";
const COQUILLE = ["/pilotage", "/pilotage/connexion", "/pilotage/manifest.webmanifest", "/pilotage/icone-192.png"];

self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(COQUILLE).catch(() => {}))); self.skipWaiting(); });
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  if (!url.pathname.startsWith("/pilotage")) return;
  // Réseau d'abord (version à jour), cache en secours hors ligne.
  e.respondWith(fetch(e.request).then(r => {
    if (r.ok && !r.redirected) { const copie = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copie)); }
    return r;
  }).catch(() => caches.match(e.request).then(r => r || caches.match("/pilotage"))));
});
