/* Dumansız Hava – çevrimdışı destek.
   Strateji: ağ öncelikli. İnternet varken her istek doğrudan siteden gelir (davranış değişmez);
   kayıtlı kopya yalnızca ağ isteği başarısız olursa kullanılır.
   Yalnızca bu sitenin sayfası ve ikonları kaydedilir; dış servisler (geri bildirim, analitik) hiç ele alınmaz. */
const CACHE = "dh-v1";
const PRECACHE = ["/", "/apple-touch-icon.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)).catch(() => {}).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k.startsWith("dh-") && k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function cacheable(res) {
  return res && res.ok && res.type === "basic" && !res.redirected;
}

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;      // dış servisler: dokunma
  if (url.pathname.startsWith("/cdn-cgi/")) return;     // Cloudflare: dokunma
  if (url.pathname === "/sw.js") return;

  const isPage = req.mode === "navigate";
  const isIcon = url.pathname === "/apple-touch-icon.png";
  if (!isPage && !isIcon) return;                       // diğer her şey: tarayıcının normal davranışı

  e.respondWith(
    fetch(req).then(res => {
      if (cacheable(res)) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(isPage ? "/" : req, copy)).catch(() => {});
      }
      return res;
    }).catch(() =>
      caches.open(CACHE).then(c => c.match(isPage ? "/" : req)).then(hit => hit || Response.error())
    )
  );
});
