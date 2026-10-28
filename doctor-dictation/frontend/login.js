(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const H = { "Content-Type": "application/json", "X-DD-Client": "1" };
  const msg = (t) => { $("msg").textContent = t || ""; };
  const show = (which) => { $("loginForm").hidden = which !== "login"; $("changeForm").hidden = which !== "change"; };
  async function post(url, body) {
    try {
      const r = await fetch(url, { method: "POST", headers: H, body: JSON.stringify(body) });
      let data = {}; try { data = await r.json(); } catch (e) { /* keep {} */ }
      return { ok: r.ok, status: r.status, data };
    } catch (e) {
      return { ok: false, status: 0, data: { error: "Could not reach the server. Check your connection and try again." } };
    }
  }
  // Run one submit with its button disabled so a double click cannot send twice.
  async function submit(form, fn) {
    const btn = form.querySelector("button[type=submit]");
    btn.disabled = true;
    try { await fn(); } finally { btn.disabled = false; }
  }
  $("loginForm").addEventListener("submit", (e) => {
    e.preventDefault(); msg("");
    submit($("loginForm"), async () => {
      const r = await post("/api/v1/auth/login", { username: $("username").value, password: $("password").value });
      if (!r.ok) { msg(r.data.error || "Could not sign in"); return; }
      if (r.data.must_change_password) {
        show("change"); $("changeUser").value = $("username").value; $("current").value = $("password").value; $("password").value = ""; $("newpw").focus();
      } else window.location.assign("/");
    });
  });
  $("changeForm").addEventListener("submit", (e) => {
    e.preventDefault(); msg("");
    submit($("changeForm"), async () => {
      if ($("newpw").value !== $("confirm").value) { msg("The two new passwords do not match"); return; }
      const r = await post("/api/v1/auth/change-password", { current_password: $("current").value, new_password: $("newpw").value });
      if (!r.ok) { msg(r.data.error || "Could not change the password"); return; }
      window.location.assign("/");
    });
  });
  $("signoutLink").addEventListener("click", async () => {
    msg("");
    const r = await post("/api/v1/auth/logout", {});
    if (!r.ok && r.status === 0) { msg(r.data.error); return; }      // unreachable: stay here
    for (const id of ["username", "password", "current", "newpw", "confirm", "changeUser"]) $(id).value = "";
    show("login"); $("username").focus();
  });
  (async () => {                                 // already signed in? skip the form
    try {
      const r = await fetch("/api/v1/auth/me");
      if (r.status !== 200) return;
      const me = await r.json();
      if (me.must_change_password) show("change"); else window.location.assign("/");
    } catch (e) { /* stay on the form */ }
  })();
})();
