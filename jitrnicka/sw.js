// Jitrnička a Jelítko – offline: recordings from the cache first (their names never change), the page and its data
// from the network first (so changes arrive), from the cache when there is no signal.
const C = "jj-offline";
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
const scope = () => self.registration.scope;
async function ranged(req, res) {   // <audio> asks for byte ranges; answer them from the cached file
  const h = req.headers.get("range"), m = h && /bytes=(\d*)-(\d*)/.exec(h);
  if (!m) return res;
  const buf = await res.arrayBuffer(), n = buf.byteLength;
  const a = m[1] === "" ? Math.max(0, n - +m[2]) : +m[1], b = m[1] !== "" && m[2] !== "" ? Math.min(n - 1, +m[2]) : n - 1;
  if (a >= n) return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${n}` } });
  return new Response(buf.slice(a, b + 1), { status: 206, headers: { "Content-Type": res.headers.get("Content-Type") || "audio/mpeg", "Content-Range": `bytes ${a}-${b}/${n}`, "Content-Length": String(b - a + 1), "Accept-Ranges": "bytes" } });
}
self.addEventListener("fetch", e => {
  const r = e.request; if (r.method !== "GET") return;
  const u = new URL(r.url);
  if (u.origin !== location.origin) {
    if (/^fonts\.(googleapis|gstatic)\.com$/.test(u.hostname)) e.respondWith(caches.open(C).then(async c => {   // the fonts: cached the first time they load
      const hit = await c.match(r); if (hit) return hit;
      const res = await fetch(r); try { await c.put(r, res.clone()); } catch (err) {} return res;
    }));
    return;
  }
  if (!u.href.startsWith(scope())) return;
  if (/\/(audio|music)\//.test(u.pathname)) {
    e.respondWith(caches.open(C).then(async c => {
      const hit = await c.match(u.origin + u.pathname);
      if (hit) return ranged(r, hit);
      const res = await fetch(r);   // played once online = there offline too (other voices, samples)
      if (res.status === 200 && !r.headers.get("range")) { try { await c.put(u.origin + u.pathname, res.clone()); } catch (err) {} }
      return res;
    }));
    return;
  }
  const key = r.mode === "navigate" ? scope() : u.origin + u.pathname;
  e.respondWith(caches.open(C).then(async c => {
    try {
      const res = await fetch(r);
      if (res.ok && (r.mode === "navigate" || /\.(json|webmanifest|png)$/.test(u.pathname)) && (await c.match(key) || r.mode === "navigate")) await c.put(key, res.clone());
      return res;
    } catch (err) {
      return (await c.match(key)) || (r.mode === "navigate" ? await c.match(scope()) : null) || Response.error();
    }
  }));
});
