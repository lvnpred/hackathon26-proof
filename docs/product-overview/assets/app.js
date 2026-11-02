/* Renderer for the Product & Codebase Overview. Reads window.DATA (assets/data-*.js); no network needed
   except the optional Mermaid CDN for diagrams (falls back to showing the diagram source). */
(function () {
  "use strict";
  const D = window.DATA;
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const STATUSES = ["Implemented", "Partial", "Demo", "POC", "Mock", "Stub", "Planned", "Deprecated", "Unknown"];
  const COLOR = { Implemented: "--ok", Partial: "--part", Demo: "--demo", POC: "--poc", Mock: "--mock", Stub: "--stub", Planned: "--plan", Deprecated: "--legacy", Unknown: "--faint" };
  const badge = (s, extra = "") => `<span class="badge b-${esc(s)} ${extra}">${esc(s)}</span>`;
  const cat = (s) => `<span class="badge b-cat">${esc(s)}</span>`;
  const plain = (s) => `<span class="badge b-plain">${esc(s)}</span>`;
  const demoBadge = (d) => `<span class="badge ${d === "Ready" ? "b-yes" : d === "Setup" ? "b-setup" : "b-no"}">${d === "Ready" ? "Demo ready" : d === "Setup" ? "Needs setup" : "Not demoable"}</span>`;
  const codeList = (arr) => (arr || []).map((p) => `<code>${esc(p)}</code>`).join("<br>");
  const countBy = (arr, key) => arr.reduce((m, x) => ((m[x[key]] = (m[x[key]] || 0) + 1), m), {});

  /* ---------- stacked status bar ---------- */
  function statusBar(items) {
    const c = countBy(items, "status"), total = items.length;
    const segs = STATUSES.filter((s) => c[s]).map((s) =>
      `<span title="${s}: ${c[s]}" style="width:${(100 * c[s]) / total}%;background:var(${COLOR[s]})"></span>`).join("");
    const legend = STATUSES.filter((s) => c[s]).map((s) => `<span><i style="background:var(${COLOR[s]})"></i>${s} ${c[s]}</span>`).join("");
    return `<div class="bar">${segs}</div><div class="legend">${legend}</div>`;
  }

  /* ---------- drawer ---------- */
  function openDrawer(html) {
    $("#drawer-body").innerHTML = html;
    $("#drawer").classList.add("open"); $("#scrim").classList.add("open");
  }
  function closeDrawer() { $("#drawer").classList.remove("open"); $("#scrim").classList.remove("open"); }
  function featureDetail(f) {
    const demos = D.demos.filter((d) => d.features.includes(f.id));
    return `<button class="close" onclick="window.__closeDrawer()">Close</button>
      <div class="small muted">${esc(f.id)} · ${esc(f.product)} › ${esc(f.module)}</div>
      <h2 style="margin-top:6px">${esc(f.name)}</h2>
      <div>${badge(f.status)} ${plain(f.lifecycle)} ${demoBadge(f.demo)} ${plain("Demo complexity: " + f.complexity)}</div>
      <dl class="kv">
        <dt>User value</dt><dd>${esc(f.value)}</dd>
        <dt>Entry point</dt><dd>${esc(f.entry)}</dd>
        <dt>Dependencies</dt><dd>${esc(f.deps)}</dd>
        <dt>Why this status</dt><dd>${esc(f.why)}</dd>
        <dt>Evidence</dt><dd>${codeList(f.evidence)}</dd>
        <dt>Demos</dt><dd>${demos.length ? demos.map((d) => `<a href="#demos" onclick="window.__go('demos','${d.id}')">${d.id} · ${esc(d.title)}</a>`).join("<br>") : '<span class="muted">No scripted demo</span>'}</dd>
      </dl>`;
  }
  function productDetail(p) {
    const feats = D.features.filter((f) => p.name.startsWith(f.product) || (p.id.startsWith("dd-") && f.product === "Doctor Dictation" && p.name.includes(f.module)) ||
      (p.id.startsWith("cg-") && f.product === "Count Guard" && p.name.toLowerCase().includes(f.module.toLowerCase())));
    return `<button class="close" onclick="window.__closeDrawer()">Close</button>
      <div class="small muted">${esc(p.category)}</div><h2 style="margin-top:6px">${esc(p.name)}</h2>
      <div>${badge(p.status)} ${p.lifecycle ? plain(p.lifecycle) : ""}</div>
      <p>${esc(p.desc)}</p>
      <dl class="kv">
        ${p.purpose ? `<dt>Business purpose</dt><dd>${esc(p.purpose)}</dd>` : ""}
        ${p.persona ? `<dt>Users</dt><dd>${esc(p.persona)}</dd>` : ""}
        ${p.ui ? `<dt>UI entry</dt><dd>${esc(p.ui)}</dd>` : ""}
        ${p.db ? `<dt>Data</dt><dd>${esc(p.db)}</dd>` : ""}
        <dt>Source</dt><dd>${codeList(p.paths)}</dd>
        ${p.evidence ? `<dt>Evidence</dt><dd>${codeList(p.evidence)}</dd>` : ""}
        ${feats.length ? `<dt>Features</dt><dd>${feats.map((f) => `<a href="#" onclick="event.preventDefault();window.__feature('${f.id}')">${f.id} ${esc(f.name)}</a>`).join("<br>")}</dd>` : ""}
      </dl>`;
  }
  const flatProducts = [];
  (function walk(list) { list.forEach((p) => { flatProducts.push(p); if (p.children) walk(p.children); }); })(D.products);

  /* ---------- 1. Executive overview ---------- */
  function renderOverview() {
    const ddF = D.features.filter((f) => f.product === "Doctor Dictation"), cgF = D.features.filter((f) => f.product === "Count Guard");
    const ready = D.demos.filter((d) => d.ready).length;
    $("#overview").innerHTML = `
      <h1>What is in this repository?</h1>
      <p class="lead">Two clinical-workflow apps built for a hackathon (13 Oct – 2 Nov 2026), sharing one repo, one <code>.env</code> and the Meta Muse model key. Since the 2 Nov consolidation they form <b>one patient flow</b>: a Doctor Dictation clinic visit saved with <b>Save &amp; admit to ward</b> is pushed to Count Guard, which follows the patient through ward, theatre and discharge. The apps keep separate servers, databases and code.</p>
      <div class="grid g4">${D.metrics.map((m) => `<div class="card metric"><div class="v">${esc(m.v)}</div><div class="l">${esc(m.l)}</div><div class="s">${esc(m.s)}</div></div>`).join("")}</div>
      <h2>The two apps</h2>
      <div class="grid g2">
        <div class="card"><h3>Doctor Dictation <span class="badge b-Implemented">Shipping-shaped</span></h3>
          <p><b>Problem:</b> OPD doctors in India spend minutes per patient writing prescriptions; STT mangles drug names.</p>
          <p><b>What it does:</b> the doctor dictates the visit → speech-to-text → an LLM drafts a structured sheet → deterministic rules repair drug names and grade every row → Save is blocked until every medicine is verified → PDF on the clinic letterhead with a QR share link, or <b>Save &amp; admit to ward</b>, which hands the patient to Count Guard.</p>
          <p><b>Users:</b> clinic doctors, assistants, clinic admin, app owner. <b>Maturity:</b> multi-clinic tenancy, Docker/Caddy deploy, 3,361 tests; safety data partly missing; admit is single-clinic only.</p>
          ${statusBar(ddF)}</div>
        <div class="card"><h3>Count Guard <span class="badge b-Partial">Research demo</span></h3>
          <p><b>Problem:</b> on a ward, things get lost around one patient — swabs, instruments, medicines, orders, questions.</p>
          <p><b>What it does:</b> one append-only timeline per patient shared by doctor, nurse and patient: intake from Doctor Dictation (push, Sync, New patient); photo proofs with verdicts; theatre with drug-by-voice, a context card and an advice-only swab camera; a server-enforced swab-count hard stop; discharge drafted from the timeline with PDF and .ics; a patient Ask inbox; an AI admin agent whose every action is labelled and undoable. “The system formats. The doctor decides.”</p>
          <p><b>Users:</b> ward doctor, nurse, patient (synthetic data). <b>Maturity:</b> no auth, no deploy. Every AI step has a live switch; live calls to all four models answered on 2 Nov, but the demo default is prepared results, labelled “Prepared”. Older generations archived.</p>
          ${statusBar(cgF)}</div>
      </div>
      <div class="callout"><b>One-line answer:</b> the actual products are <b>Doctor Dictation</b> (OPD prescription) and the <b>Count Guard care app “Ward 4”</b> with its AI admin agent. Every feature of the earlier generations (camera swab counter, “morning” timeline, journey v1) now lives in the care app; their screens and routes sit in <code>count-guard/archive/</code>, unmounted.</div>
      <h2>Main capabilities</h2>
      <div class="grid g3">
        <div class="card tight"><h3>Voice → checked prescription</h3><div class="small muted">STT chain, LLM loop, offline rules fallback, lexicon repair, row pills, verify gate.</div></div>
        <div class="card tight"><h3>Records, PDF & sharing</h3><div class="small muted">Today list, past-day lock, Chromium PDF, letterhead from a photo, 7-day QR link.</div></div>
        <div class="card tight"><h3>Clinic tenancy & learning</h3><div class="small muted">Per-clinic DB, sessions, roles, learned formulary, spoken terms, “Your usual”.</div></div>
        <div class="card tight"><h3>One patient across two apps</h3><div class="small muted">Save &amp; admit → intake → ward → theatre → discharge PDF; Sync as backup; photo verdicts; state machine.</div></div>
        <div class="card tight"><h3>Swab-count hard stop</h3><div class="small muted">Surgery cannot end until a person saves a count that adds up or gives a reason; camera and rules are advice only.</div></div>
        <div class="card tight"><h3>Explainable AI admin</h3><div class="small muted">Rule-based ops agent, policy “Never” list, Undo, Pause, Inspector with evidence.</div></div>
      </div>
      <h2>Feature status at a glance</h2>
      <div class="card">${statusBar(D.features)}<div class="small muted" style="margin-top:6px">${D.features.length} catalogued features · ${ready} of ${D.demos.length} scripted demos run with no keys · method: ${esc(D.meta.method)}</div></div>`;
  }

  /* ---------- 2. Product map ---------- */
  function treeHTML(list) {
    return `<ul class="tree">${list.map((p) => `<li class="${p.children ? "" : "leaf"}">
      <div class="node" data-pid="${p.id}"><span class="tw">${p.children ? "▾" : "•"}</span><span class="nm">${esc(p.name)}</span> ${cat(p.category)} ${badge(p.status)} ${p.lifecycle === "Legacy" || p.lifecycle === "Archived" ? plain(p.lifecycle) : ""}
      <span class="ds">${esc(p.desc)}</span></div>${p.children ? treeHTML(p.children) : ""}</li>`).join("")}</ul>`;
  }
  function renderMap() {
    const cg = flatProducts.find((p) => p.id === "cg"), dd = flatProducts.find((p) => p.id === "dd");
    const col = (title, b, items) => `<div class="card col"><h3>${title} ${b}</h3>${items.map((p) =>
      `<div class="mod" data-pid="${p.id}"><div class="n"><span>${esc(p.name)}</span>${badge(p.status)}</div><div class="d">${esc(p.desc.slice(0, 140))}${p.desc.length > 140 ? "…" : ""}</div></div>`).join("")}</div>`;
    $("#map").innerHTML = `<h1>Product Map</h1>
      <p class="lead">Logical hierarchy derived from code, not folder names. Click any box for its purpose, source and evidence.</p>
      <div class="pm">
        ${col("Doctor Dictation", cat("Product"), dd.children)}
        ${col("Count Guard — current product", cat("Product"), cg.children.filter((p) => p.lifecycle === "Current" && p.category !== "Demo").flatMap((p) => p.children ? [p, ...p.children] : [p]))}
        ${col("Count Guard — demo, POC & archive", plain("Not the product"), cg.children.filter((p) => p.lifecycle === "Legacy" || p.lifecycle === "Archived" || p.category === "Demo"))}
      </div>
      <h2>Full hierarchy</h2><div class="card">${treeHTML(D.products)}</div>`;
    $("#map").querySelectorAll("[data-pid]").forEach((el) => el.addEventListener("click", (e) => {
      if (e.target.classList.contains("tw")) { el.parentElement.classList.toggle("collapsed"); e.target.textContent = el.parentElement.classList.contains("collapsed") ? "▸" : "▾"; return; }
      openDrawer(productDetail(flatProducts.find((p) => p.id === el.dataset.pid)));
    }));
  }

  /* ---------- 3. Feature catalogue ---------- */
  const fstate = { q: "", product: "", module: "", status: "", lifecycle: "", demo: "" };
  function renderCatalogue() {
    const opts = (key, label) => `<select data-k="${key}"><option value="">${label}: all</option>${[...new Set(D.features.map((f) => f[key]))].map((v) => `<option>${esc(v)}</option>`).join("")}</select>`;
    $("#catalogue").innerHTML = `<h1>Feature Catalogue</h1>
      <p class="lead">${D.features.length} user-visible capabilities. Status is judged from code (persistence, auth, validation, tests, mocks, data), not from the existence of a screen. Click a row for evidence.</p>
      <div class="filters"><input id="fq" placeholder="Search name, value, entry point, file…">${opts("product", "Product")}${opts("module", "Module")}${opts("status", "Status")}${opts("lifecycle", "Lifecycle")}${opts("demo", "Demo")}<span class="count" id="fcount"></span></div>
      <div class="table-wrap"><table><thead><tr><th>ID</th><th>Feature</th><th>Product › Module</th><th>Status</th><th>Lifecycle</th><th>Demo</th><th>Entry point</th></tr></thead><tbody id="ftbody"></tbody></table></div>`;
    $("#fq").addEventListener("input", (e) => { fstate.q = e.target.value.toLowerCase(); fillCatalogue(); });
    $("#catalogue").querySelectorAll("select").forEach((s) => s.addEventListener("change", () => { fstate[s.dataset.k] = s.value; fillCatalogue(); }));
    fillCatalogue();
  }
  function fillCatalogue() {
    const rows = D.features.filter((f) => ["product", "module", "status", "lifecycle", "demo"].every((k) => !fstate[k] || f[k] === fstate[k]) &&
      (!fstate.q || JSON.stringify(f).toLowerCase().includes(fstate.q)));
    $("#fcount").textContent = `${rows.length} shown`;
    $("#ftbody").innerHTML = rows.map((f) => `<tr class="clickable" data-fid="${f.id}"><td class="mono">${f.id}</td><td><b>${esc(f.name)}</b><div class="small muted">${esc(f.value)}</div></td>
      <td>${esc(f.product)}<div class="small muted">${esc(f.module)}</div></td><td>${badge(f.status)}</td><td>${plain(f.lifecycle)}</td><td>${demoBadge(f.demo)}</td><td class="small">${esc(f.entry)}</td></tr>`).join("");
    $("#ftbody").querySelectorAll("tr").forEach((tr) => tr.addEventListener("click", () => openDrawer(featureDetail(D.features.find((f) => f.id === tr.dataset.fid)))));
  }

  /* ---------- 4. Demo centre ---------- */
  let demoFilter = "All";
  function renderDemos() {
    const groups = ["All", "Ready now", "Needs setup", "Standalone", "End-to-end", "Cross-module", "Advanced technical", "Experimental"];
    $("#demos").innerHTML = `<h1>Demo Centre</h1>
      <p class="lead">${D.demos.length} scripted demos, all backed by existing code. ${D.demos.filter((d) => d.ready).length} run offline with no keys. With no key, Count Guard's tray, set-up and swab media must keep their generated names — those prepared results are matched by file name (photos are matched by content).</p>
      <h2>Recommended journeys by audience</h2>
      <div class="table-wrap"><table><thead><tr><th>Audience</th><th>Sequence</th><th>Time</th><th>Key message</th><th>Avoid</th></tr></thead><tbody>
      ${D.journeys.map((j) => `<tr><td><b>${esc(j.audience)}</b><div>${j.label === "Supported" ? '<span class="badge b-yes">Supported</span>' : '<span class="badge b-setup">Suggested</span>'}</div></td>
        <td>${j.demos.map((id) => `<a href="#" data-jump="${id}">${id}</a>`).join(" → ")}</td><td>${j.mins} min</td><td class="small">${esc(j.message)}</td><td class="small muted">${esc(j.avoid)}</td></tr>`).join("")}
      </tbody></table></div>
      <h2>Setup</h2>
      <div class="grid g2"><div class="card"><h3>Doctor Dictation (offline)</h3><pre class="mono small" style="white-space:pre-wrap;margin:0">${esc(D.demoSetup.dd.join("\n"))}</pre></div>
      <div class="card"><h3>Count Guard (offline)</h3><pre class="mono small" style="white-space:pre-wrap;margin:0">${esc(D.demoSetup.cg.join("\n"))}</pre></div></div>
      <h2>All demos</h2><div class="tabs" id="dtabs">${groups.map((g) => `<button class="chip ${g === demoFilter ? "on" : ""}" data-g="${g}">${g}</button>`).join("")}</div><div id="dlist"></div>`;
    $("#dtabs").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { demoFilter = b.dataset.g; renderDemos(); }));
    $("#demos").querySelectorAll("[data-jump]").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); showDemo(a.dataset.jump); }));
    const list = D.demos.filter((d) => demoFilter === "All" || (demoFilter === "Ready now" ? d.ready : demoFilter === "Needs setup" ? !d.ready : d.group === demoFilter));
    $("#dlist").innerHTML = list.map((d) => `<details class="demo" id="demo-${d.id}"><summary><span class="mono">${d.id}</span><span class="t">${esc(d.title)}</span>
      ${plain(d.product)} ${plain(d.group)} ${d.ready ? '<span class="badge b-yes">Ready, no keys</span>' : '<span class="badge b-setup">Needs setup</span>'} ${plain(d.cx + " · ~" + d.mins + " min")}</summary>
      <div class="body"><p><b>Why it matters:</b> ${esc(d.why)}</p>
      <p><b>Audience:</b> ${d.audience.map(plain).join(" ")} &nbsp; <b>Features:</b> ${d.features.map((id) => `<a href="#" onclick="event.preventDefault();window.__feature('${id}')">${id}</a>`).join(", ")}</p>
      <h3>Prerequisites</h3><ul class="clean">${d.prereq.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      <h3>Steps</h3><ol class="steps">${d.steps.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>
      <div class="callout"><b>Expected outcome:</b> ${esc(d.expected)}</div>
      <h3>What to say</h3><ul class="clean">${d.explain.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      <dl class="kv"><dt>APIs</dt><dd>${codeList(d.apis)}</dd><dt>Evidence</dt><dd>${codeList(d.evidence)}</dd></dl></div></details>`).join("");
  }
  function showDemo(id) { demoFilter = "All"; renderDemos(); const el = $("#demo-" + id); if (el) { el.open = true; el.scrollIntoView({ behavior: "smooth", block: "start" }); } }

  /* ---------- 5. Architecture ---------- */
  let diagram = D.diagrams[0].id;
  function renderArch() {
    const d = D.diagrams.find((x) => x.id === diagram);
    const kindBadge = (k) => k === "Implemented" ? '<span class="badge b-Implemented">Implemented</span>' : k === "Documented" ? '<span class="badge b-Partial">Documented, not all built</span>' : '<span class="badge b-Planned">Proposed</span>';
    $("#arch").innerHTML = `<h1>Architecture Explorer</h1>
      <p class="lead">Diagrams are labelled <b>Implemented</b> (read from code), <b>Documented</b> (described in docs; not all built) or <b>Proposed</b> (a recommendation). Diagrams render with Mermaid when online; offline you see the diagram source.</p>
      <div class="tabs">${D.diagrams.map((x) => `<button class="chip ${x.id === diagram ? "on" : ""}" data-d="${x.id}">${esc(x.title)}</button>`).join("")}</div>
      <div class="card"><h3>${esc(d.title)} ${kindBadge(d.kind)}</h3>${d.note ? `<p class="small muted">${esc(d.note)}</p>` : ""}
      <div class="diagram"><div class="mermaid" id="mm">${esc(d.src)}</div></div></div>`;
    $("#arch").querySelectorAll("[data-d]").forEach((b) => b.addEventListener("click", () => { diagram = b.dataset.d; renderArch(); }));
    drawMermaid(d);
  }
  let mermaidState = "loading";
  function drawMermaid(d) {
    const box = $("#mm"); if (!box) return;
    if (mermaidState === "failed" || !window.mermaid) { box.outerHTML = `<pre class="mermaid-src">${esc(d.src)}</pre>`; return; }
    const token = (drawMermaid.token = (drawMermaid.token || 0) + 1);  // ignore a slow render after the tab changed
    window.mermaid.render("m" + token, d.src)
      .then(({ svg }) => { if (token === drawMermaid.token && box.isConnected) box.innerHTML = svg; })
      .catch(() => { if (token === drawMermaid.token && box.isConnected) box.outerHTML = `<pre class="mermaid-src">${esc(d.src)}</pre>`; });
  }
  window.__mermaidReady = (ok) => {
    mermaidState = ok ? "ready" : "failed";
    if (ok) window.mermaid.initialize({ startOnLoad: false, theme: document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "default", securityLevel: "strict" });
    if ($("#arch").classList.contains("active")) renderArch();
  };

  /* ---------- 6. Repository explorer ---------- */
  function repoHTML(n) {
    return `<li><div class="node"><span class="tw">${n.children ? "▾" : "•"}</span><span class="nm mono">${esc(n.name)}</span> ${badge(n.status)} ${plain(n.product)}<span class="ds">${esc(n.purpose)}</span></div>
      ${n.children ? `<ul>${n.children.map(repoHTML).join("")}</ul>` : ""}</li>`;
  }
  function renderRepo() {
    $("#repo").innerHTML = `<h1>Repository Explorer</h1>
      <p class="lead">Important directories, what they do, and which product they belong to. Badges use the same status vocabulary as the catalogue. Click ▾ to fold.</p>
      <div class="card"><ul class="tree">${repoHTML(D.repo)}</ul></div>
      <div class="callout warn"><b>Folder names mislead here:</b> <code>count-guard/backend/app/morning/</code> has no routes any more but holds the event store and helpers the care app depends on; <code>core/</code>, <code>engine.py</code> and <code>report/</code> came from the old camera counter and are now libraries of the theatre camera. Only <code>count-guard/archive/</code> is truly retired.</div>`;
    $("#repo").querySelectorAll(".tw").forEach((t) => t.addEventListener("click", () => { const li = t.closest("li"); li.classList.toggle("collapsed"); t.textContent = li.classList.contains("collapsed") ? "▸" : "▾"; }));
  }

  /* ---------- 7. Classification ---------- */
  function renderClass() {
    $("#classify").innerHTML = `<h1>Product vs Demo vs POC</h1>
      <p class="lead">What a customer would actually get, versus what exists only to demonstrate or explore.</p>
      ${D.classification.map((c) => `<div class="card" style="margin:12px 0"><h3>${esc(c.bucket)} ${badge(c.status)}</h3>
        <div class="table-wrap" style="border:none"><table><thead><tr><th style="width:28%">Item</th><th>Why</th><th style="width:34%">Where</th></tr></thead><tbody>
        ${c.items.map(([n, w, p]) => `<tr><td><b>${esc(n)}</b></td><td class="small">${esc(w)}</td><td><code>${esc(p)}</code></td></tr>`).join("")}</tbody></table></div></div>`).join("")}`;
  }

  /* ---------- 8. Overlap ---------- */
  function renderOverlap() {
    const stB = (s) => `<span class="badge ${s === "Resolved" ? "b-Implemented" : s === "Partly resolved" ? "b-Partial" : "b-plain"}">${esc(s || "Open")}</span>`;
    const sevB = (s) => `<span class="badge ${s === "High" ? "b-Stub" : s === "Medium" ? "b-Partial" : "b-plain"}">${s}</span>`;
    $("#overlap").innerHTML = `<h1>Overlap & Consolidation</h1>
      <p class="lead">${D.overlaps.length} findings, first assessed at e40d8c7 and re-checked at ${esc(D.meta.commit)} after the 2 Nov consolidation: ${D.overlaps.filter((o) => o.state === "Resolved").length} resolved, ${D.overlaps.filter((o) => o.state === "Partly resolved").length} partly resolved, ${D.overlaps.filter((o) => o.state === "Open").length} open. This overview changed no code.</p>
      <div class="table-wrap"><table><thead><tr><th>#</th><th>Finding</th><th>Severity</th><th>Recommendation</th><th>State</th></tr></thead><tbody>
      ${D.overlaps.map((o) => `<tr class="clickable" data-o="${o.id}"><td class="mono">${o.id}</td><td><b>${esc(o.title)}</b></td><td>${sevB(o.sev)}</td><td>${plain(o.verdict)}</td><td>${stB(o.state)}</td></tr>`).join("")}</tbody></table></div>
      <h2>Details</h2>${D.overlaps.map((o) => `<details class="demo" id="ov-${o.id}"><summary><span class="mono">${o.id}</span><span class="t">${esc(o.title)}</span>${sevB(o.sev)} ${stB(o.state)}</summary>
      <div class="body"><dl class="kv"><dt>What is combined</dt><dd>${esc(o.combined)}</dd><dt>Where</dt><dd>${codeList(o.where)}</dd><dt>Why it confuses</dt><dd>${esc(o.why)}</dd>
      <dt>Logical separation</dt><dd>${esc(o.separation)}</dd><dt>Target shape</dt><dd><code>${esc(o.target)}</code></dd></dl></div></details>`).join("")}
      <div class="callout"><b>Recommended product boundaries:</b> (1) Doctor Dictation — OPD prescription product; (2) Count Guard Care — ward product incl. AI admin; (3) a small Care platform extracted from Count Guard (ledger, perception seam, verifier, ops runner); (4) a Showcase package (dock, seed, fixtures, demo-check); (5) an Archive for the camera counter, morning timeline and journey v1 — <b>done on 2 Nov</b> (<code>count-guard/archive/</code>). See the “Recommended module boundaries” diagram in Architecture (Proposed).</div>`;
    $("#overlap").querySelectorAll("[data-o]").forEach((tr) => tr.addEventListener("click", () => { const el = $("#ov-" + tr.dataset.o); el.open = true; el.scrollIntoView({ behavior: "smooth" }); }));
  }

  /* ---------- 9. Stack ---------- */
  function renderStack() {
    $("#stack").innerHTML = `<h1>Technical Stack</h1><p class="lead">From dependency manifests and imports: <code>count-guard/frontend/package.json</code>, <code>count-guard/backend/requirements.txt</code>, <code>doctor-dictation/doctor_dictation/requirements*.txt</code>, <code>doctor-dictation/pyproject.toml</code>.</p>
      <div class="grid g2">${D.stack.map((s) => `<div class="card"><h3>${esc(s.layer)}</h3><ul class="clean">${s.items.map(([n, w]) => `<li><b>${esc(n)}</b> <span class="muted small">— ${esc(w)}</span></li>`).join("")}</ul></div>`).join("")}</div>`;
  }

  /* ---------- 10. Gaps ---------- */
  function renderGaps() {
    const pB = (p) => `<span class="badge ${p === "P1" ? "b-Stub" : p === "P2" ? "b-Partial" : "b-plain"}">${p}</span>`;
    $("#gaps").innerHTML = `<h1>Gaps & Recommendations</h1>
      <p class="lead">P1 = blocks honest customer claims or safe exposure; P2 = should fix before a pilot; P3 = hygiene.</p>
      <div class="table-wrap"><table><thead><tr><th>Priority</th><th>Type</th><th>Gap</th><th>Evidence</th></tr></thead><tbody>
      ${D.gaps.map((g) => `<tr><td>${pB(g.p)}</td><td>${plain(g.kind)}</td><td>${esc(g.text)}</td><td><code>${esc(g.ev)}</code></td></tr>`).join("")}</tbody></table></div>
      <h2>Recommended next steps</h2>
      <ol class="steps">
        <li>Film the live swab camera on a real prop tray (video script, spec U14), or keep the “Prepared” label on screen and in the narration.</li>
        <li>Set <code>CG_SYNC_TOKEN</code> for every two-app run, and rewrite the Count Guard README submission notes from the 2 Nov live-check.</li>
        <li>Ship or remove DD safety claims: load reviewed dosing and investigations data, review the LASA pairs.</li>
        <li>Extract the ledger kernel and the camera/perception libraries from <code>morning/</code>, <code>core/</code> and <code>agent/</code> (O2, O10); the archive step (O1) is done.</li>
        <li>Move the ops agent off the request path (O3).</li>
        <li>Mark <code>docs/hackathon/01–06</code> superseded and link to this overview.</li>
      </ol>
      <h2>Areas requiring human validation</h2><ul class="clean">${D.validation.map((v) => `<li>${esc(v)}</li>`).join("")}</ul>`;
  }

  /* ---------- navigation ---------- */
  const PAGES = { overview: renderOverview, map: renderMap, catalogue: renderCatalogue, demos: renderDemos, arch: renderArch, repo: renderRepo, classify: renderClass, overlap: renderOverlap, stack: renderStack, gaps: renderGaps };
  const rendered = {};
  function go(page, demoId) {
    if (!PAGES[page]) page = "overview";
    document.querySelectorAll("section.page").forEach((s) => s.classList.toggle("active", s.id === page));
    document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("active", a.getAttribute("href") === "#" + page));
    if (!rendered[page] || page === "arch") { PAGES[page](); rendered[page] = true; }
    if (demoId) showDemo(demoId);
    closeDrawer(); $(".sidebar").classList.remove("open");
    if (!demoId) requestAnimationFrame(() => window.scrollTo(0, 0));  // after the browser's own jump to the #anchor
  }
  window.__go = (p, id) => { history.replaceState(null, "", "#" + p); go(p, id); };
  window.__closeDrawer = closeDrawer;
  window.__feature = (id) => openDrawer(featureDetail(D.features.find((f) => f.id === id)));
  window.addEventListener("hashchange", () => go(location.hash.slice(1)));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
  $("#scrim").addEventListener("click", closeDrawer);
  $("#menu").addEventListener("click", () => $(".sidebar").classList.toggle("open"));
  function setTheme(t) { try { localStorage.setItem("po-theme", t); } catch (e) { /* storage may be blocked */ } document.documentElement.dataset.theme = t; }
  $("#theme").addEventListener("click", () => {
    const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    setTheme(cur === "dark" ? "light" : "dark");
    if (window.mermaid && mermaidState === "ready") { window.__mermaidReady(true); }
  });
  try { const t = localStorage.getItem("po-theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* ignore */ }
  $("#foot").innerHTML = `Snapshot of <code>${esc(D.meta.branch)}</code> @ <code>${esc(D.meta.commit)}</code><br>Generated ${esc(D.meta.generated)}`;
  go(location.hash.slice(1) || "overview");
})();
