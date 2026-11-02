// The two-app demo banner (spec §12): shown only when the server says DEMO_BANNER=1 (GET /api/health demo_banner).
(function (root) {
  "use strict";
  const el = root.document.getElementById("demoBanner");
  if (!el) return;
  root.fetch("/api/health", { headers: { Accept: "application/json" } })
    .then((r) => (r.ok ? r.json() : null))
    .then((j) => { el.hidden = !(j && j.demo_banner === true); })
    .catch(() => { el.hidden = true; });
})(window);
