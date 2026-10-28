/* Session plumbing for the main app. Wraps fetch so app.js and letterhead.js need no changes. */
(function () {
  "use strict";
  const UNSAFE = new Set(["POST", "PUT", "DELETE", "PATCH"]);
  const nativeFetch = window.fetch.bind(window);
  let leaving = false;

  function toLogin() {
    if (leaving) return;
    leaving = true;
    window.location.assign("/login");
  }

  window.fetch = async function (input, init) {
    const opts = Object.assign({}, init || {});
    const method = String(opts.method || (input && input.method) || "GET").toUpperCase();
    if (UNSAFE.has(method)) {
      const h = new Headers(opts.headers || (input && input.headers) || {});
      h.set("X-DD-Client", "1");
      opts.headers = h;                       // FormData bodies keep their own multipart Content-Type
    }
    const r = await nativeFetch(input, opts);
    if (r.status === 401) { toLogin(); return r; }
    if (r.status === 403) {
      try {
        const body = await r.clone().json();
        if (body && body.code === "must_change_password") toLogin();
      } catch (e) { /* not JSON: leave it to the caller */ }
    }
    return r;
  };

  async function init() {
    const out = document.getElementById("signOutBtn");
    let me = null;
    try {
      const r = await nativeFetch("/api/v1/auth/me");
      if (r.status === 200) me = await r.json();
      else if (r.status === 401) { toLogin(); return; }
    } catch (e) { /* offline: keep the page usable */ }
    if (!me) return;                          // single mode (404): no sign-out button, no top-bar change
    if (me.must_change_password) { toLogin(); return; }   // the login page shows the change-password step
    const clinic = document.getElementById("topClinic");
    const doctor = document.getElementById("topDoctor");
    window.DDUser = me;                       // app.js keeps the top bar on the signed-in user's own name
    if (clinic && me.clinic_name && clinic.textContent.trim() === "Clinic") clinic.textContent = me.clinic_name;   // the Profile's clinic name (app.js) wins once known; the account's name is only the fallback
    if (doctor && me.display_name && doctor.textContent.trim() === "Doctor") doctor.textContent = me.display_name;   // app.js's profile name wins once known
    if (out) {
      out.hidden = false;
      out.addEventListener("click", async () => {
        try { await window.fetch("/api/v1/auth/logout", { method: "POST" }); } catch (e) { /* ignore */ }
        window.location.assign("/login");
      });
    }
  }
  document.addEventListener("DOMContentLoaded", init);
})();
