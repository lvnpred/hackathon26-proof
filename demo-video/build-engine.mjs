// Generates index.html for the ENGINE CUT from engine-beats.json + engine-crops.json.
// 32 scenes (E02/E11/E13/E14/E19/E22 split), LEFT-current seams stamped from ledger.json.
// Re-run when assets change: node build-engine.mjs
import fs from "node:fs";
import cp from "node:child_process";

const W = 1920, H = 1080, ACCENT = "#e8a33d", GROUND = "#14100c";
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const voDur = (f) => +cp.execSync(`ffprobe -v error -show_entries format=duration -of csv=p=0 assets/evo/${f}.wav`).toString().trim();

// Scenes: id, at, sec, kind, payload.
const S = [
  { id: "E01", at: 0, sec: 4, kind: "photo", crop: "E01", tag: "Swabs · before", cap: "Fifteen swabs in. Fifteen must come out." },
  { id: "E02a", at: 4, sec: 4, kind: "photo", crop: "E02", tag: "Strip · real label", cap: "The real strip: Doxofylline 400 mg." },
  { id: "E02b", at: 8, sec: 4, kind: "type", lines: ["amlodipine 10 mg", "Doxofylline 400 mg — as read"], strike: 0, accent: 1 },
  { id: "E04", at: 12, sec: 5, kind: "herodim", bg: "E04", role: "The Watcher", model: "SAM 3.1", power: "Counts every tool, every swab." },
  { id: "E05", at: 17, sec: 5, kind: "hero", role: "The Listener", model: "Muse Voice", power: "Hears every order, every drug." },
  { id: "E06", at: 22, sec: 5, kind: "herodim", bg: "E06", role: "The Reader", model: "Spark 1.3", power: "Checks every photo, every strip.", rule: "The AI never decides. A person confirms." },
  { id: "E03", at: 27, sec: 8, kind: "app", crop: "E03", tag: "Clinic · admit", cap: "Stomach pain. Admitted to Ward 4." },
  { id: "E07", at: 35, sec: 10, kind: "staged", offs: [0.3, 2.7, 4.0], lines: ["He speaks the visit.", "He spells the drug.", "He taps Use this."] },
  { id: "E08", at: 45, sec: 6, kind: "app", crop: "E08", tag: "Doctor · plan", cap: "The hernia repair, planned. Tray list sent." },
  { id: "E09", at: 51, sec: 10, kind: "app", crop: "E09", tag: "Listener · dictate 14.4s", cap: "He speaks. Spark drafts. He signs." },
  { id: "E10", at: 61, sec: 4, kind: "staged", offs: [0.3, 1.5], lines: ["Photos reviewed.", "Questions answered."] },
  { id: "E11a", at: 65, sec: 2, kind: "app", crop: "E11a", tag: "Checklist · empty", cap: "Four proofs. One tap each." },
  { id: "E11b", at: 67, sec: 3.5, kind: "app", crop: "E11b", tag: "Reader · 9.7s", cap: "Wristband. Photo matches." },
  { id: "E11c", at: 70.5, sec: 3.5, kind: "app", crop: "E11c", tag: "Reader · 8.2s", cap: "No known allergies. Matched." },
  { id: "E11d", at: 74, sec: 3.5, kind: "app", crop: "E11d", tag: "Reader · 5.9s", cap: "Vitals on screen. Matched." },
  { id: "E11e", at: 77.5, sec: 3.5, kind: "app", crop: "E11e", tag: "Reader · 6.4s", cap: "Signed consent. Matched." },
  { id: "E12", at: 81, sec: 8, kind: "staged", offs: [0.3, 1.8, 2.8], lines: ["Ward tasks by voice.", "Doses logged.", "Drugs confirmed."] },
  { id: "E13a", at: 89, sec: 4, kind: "app", crop: "E13a", tag: "Theatre · flagged", cap: "Not everything planned was seen. Surgery waits." },
  { id: "E13b", at: 93, sec: 6, kind: "app", crop: "E13b", tag: "Watcher · SAM 3.1", cap: "Needle holder: 0 of 3. The Watcher flags it." },
  { id: "E14a", at: 99, sec: 9, kind: "app", crop: "E14a", tag: "Watcher · 7.1s", cap: "Before: zero of fifteen seen." },
  { id: "E14b", at: 108, sec: 9, kind: "app", crop: "E14b", tag: "Reader · 8.2s", cap: "After: fifteen stained swabs match." },
  { id: "E15", at: 117, sec: 8, kind: "app", crop: "E15", tag: "Count · 15/15/0", cap: "Fifteen of fifteen. Zero missing." },
  { id: "E16", at: 125, sec: 7, kind: "staged", offs: [0.3, 1.2], lines: ["Vani checks in.", "Her day plan is ready."] },
  { id: "E17", at: 132, sec: 8, kind: "app", crop: "E17", tag: "Spark 1.3 · strips", cap: "Typed one name. Photo reads another." },
  { id: "E18", at: 140, sec: 8, kind: "app", crop: "E18", tag: "Ask · record", cap: "The record answers. The doctor answers next." },
  { id: "E19a", at: 148, sec: 4, kind: "photo", crop: "E19c", tag: "Matcher · refused", cap: "Blister strips — not a medicine bag. Refused." },
  { id: "E19b", at: 152, sec: 4, kind: "app", crop: "E19a", tag: "Split · pass/fail", cap: "Card passes. Medicines fail." },
  { id: "E19c", at: 156, sec: 4, kind: "app", crop: "E19b", tag: "Reader · 10.3s", cap: "Labeled bag. Matched." },
  { id: "E20", at: 160, sec: 8, kind: "staged", offs: [0.3, 1.3], lines: ["Captured. Returned.", "Used. Confirmed by a person."] },
  { id: "E21", at: 168, sec: 4, kind: "pills", pills: ["Spark 1.3 · 9.7s", "SAM 3.1 · tray", "Spark 1.3 · 8.2s", "Spark 1.3 · 14.4s"] },
  { id: "E22a", at: 172, sec: 2.25, kind: "app", crop: "E22b", tag: "Home · discharged", cap: "You are home. Discharge complete." },
  { id: "E22b", at: 174.25, sec: 5.75, kind: "enddim", bg: "E22d", brand: "LIGHTDAY", tagline: "The count can't be lost.", lines: ["No missed swabs. No wrong pills. No lost discharges.", "Built with Muse — SAM 3.1 · Muse Voice · Spark 1.3.", "The system formats. The doctor decides."] },
];
const beats = JSON.parse(fs.readFileSync("engine-beats.json", "utf8"));
const DISPW = 1500, DISPX = (W - DISPW) / 2;

import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const cropDims = {};
for (const f of fs.readdirSync("assets/engine-crops")) {
  if (!f.endsWith(".png")) continue;
  const d = cp.execSync(`ffprobe -v error -show_entries stream=width,height -of csv=p=0 assets/engine-crops/${f}`).toString().trim().split(",");
  cropDims[f.replace(/\.png$/, "")] = { w: +d[0], h: +d[1] };
}

function typeScene(s) {
  const lines = s.lines.map((l, i) => `          <span id="${s.id}-l${i}" class="tline${i === s.accent ? " acc" : ""}${i === s.strike ? " strike" : ""}">${esc(l)}</span>`).join("\n");
  return `      <div id="el-${s.id}" class="scene">\n        <div class="lines">\n${lines}\n        </div>\n      </div>`;
}
function heroScene(s) {
  const rule = s.rule ? `\n          <span id="${s.id}-rule" class="tline rule">${esc(s.rule)}</span>` : "";
  const bg = s.bg ? `\n        <div id="dim-${s.id}" class="dim"><img src="assets/engine-crops/${s.bg}.png" alt="" /><div class="shade strong"></div></div>` : "";
  return `      <div id="el-${s.id}" class="scene">${bg}
        <div class="lines">
          <span id="${s.id}-role" class="role">${esc(s.role)}</span>
          <span id="${s.id}-model" class="model">${esc(s.model)}</span>
          <span id="${s.id}-power" class="tline">${esc(s.power)}</span>${rule}
        </div>
      </div>`;
}
function shotScene(s) {
  const c = cropDims[s.crop];
  const dw = Math.min(DISPW, Math.round((880 * c.w) / c.h));
  const dh = Math.round((c.h * dw) / c.w);
  const left = Math.round((W - dw) / 2);
  const top = Math.round((H - dh) / 2 - 30);
  return `      <div id="el-${s.id}" class="scene">
        <div id="shot-${s.id}" class="shot" style="left:${left}px;top:${top}px;width:${dw}px;">
          <img id="img-${s.id}" src="assets/engine-crops/${s.crop}.png" width="${dw}" alt="" />
          <div id="br-${s.id}" class="brackets"><i class="c tl"></i><i class="c tr"></i><i class="c bl"></i><i class="c br"></i></div>
          <div id="tag-${s.id}" class="tag">${esc(s.tag)}</div>
        </div>
        <p id="cap-${s.id}" class="cap">${esc(s.cap)}</p>
      </div>`;
}
function stagedScene(s) {
  const lines = s.lines.map((l, i) => `          <span id="${s.id}-l${i}" class="tline">${esc(l)}</span>`).join("\n");
  return `      <div id="el-${s.id}" class="scene">\n        <div class="lines">\n${lines}\n        </div>\n      </div>`;
}
function pillsScene(s) {
  const pills = s.pills.map((p, i) => `          <span id="${s.id}-p${i}" class="pill">${esc(p)}</span>`).join("\n");
  return `      <div id="el-${s.id}" class="scene">\n        <div class="lines">\n${pills}\n        </div>\n      </div>`;
}
function enddimScene(s) {
  const lines = s.lines.map((l, i) => `          <span id="${s.id}-m${i}" class="tline small">${esc(l)}</span>`).join("\n");
  return `      <div id="el-${s.id}" class="scene">
        <div id="dim-${s.id}" class="dim"><img src="assets/engine-crops/${s.bg}.png" alt="" /><div class="shade max"></div></div>
        <div class="lines">
          <span id="${s.id}-brand" class="brand">${esc(s.brand)}</span>
          <span id="${s.id}-tagline" class="tagline">${esc(s.tagline)}</span>
${lines}
        </div>
      </div>`;
}
const markup = S.map((s) => s.kind === "type" ? typeScene(s) : (s.kind === "hero" || s.kind === "herodim") ? heroScene(s) : (s.kind === "app" || s.kind === "photo") ? shotScene(s) : s.kind === "pills" ? pillsScene(s) : s.kind === "enddim" ? enddimScene(s) : stagedScene(s)).join("\n");

// --- tweens (inner elements only; wrappers belong to the stamped seams) ---
const T = [];
function cascade(ids, at) {
  let t = at;
  ids.forEach(([sel, y, d], i) => {
    T.push(`tl.set("${sel}", { opacity: 1 }, ${t.toFixed(2)});`);
    T.push(`tl.fromTo("${sel}", { y: ${y} }, { y: 0, duration: ${d}, ease: "power4.out" }, ${t.toFixed(2)});`);
    t += i === 0 ? 0.14 : 0.10;
  });
}
for (const s of S) {
  if (s.kind === "type") {
    cascade(s.lines.map((l, i) => [`#${s.id}-l${i}`, 50, 0.4]), s.at + 0.15);
  } else if (s.kind === "hero" || s.kind === "herodim") {
    if (s.bg) T.push(`tl.fromTo("#dim-${s.id}", { scale: 1 }, { scale: 1.08, duration: ${s.sec}, ease: "none" }, ${s.at});`);
    cascade([[`#${s.id}-role`, 70, 0.5], [`#${s.id}-model`, 40, 0.35], [`#${s.id}-power`, 50, 0.4]], s.at + 0.15);
    if (s.rule) {
      T.push(`tl.set("#${s.id}-rule", { opacity: 1 }, ${(s.at + 2.6).toFixed(2)});`);
      T.push(`tl.fromTo("#${s.id}-rule", { y: 50 }, { y: 0, duration: 0.4, ease: "power4.out" }, ${(s.at + 2.6).toFixed(2)});`);
    }
  } else if (s.kind === "staged") {
    const gap = Math.min(3.2, (s.sec - 1.2) / s.lines.length);
    s.lines.forEach((l, i) => {
      const t = s.at + (s.offs ? s.offs[i] : 0.3 + i * gap);
      T.push(`tl.set("#${s.id}-l${i}", { opacity: 1 }, ${t.toFixed(2)});`);
      T.push(`tl.fromTo("#${s.id}-l${i}", { y: 50 }, { y: 0, duration: 0.4, ease: "power4.out" }, ${t.toFixed(2)});`);
    });
  } else if (s.kind === "pills") {
    s.pills.forEach((p, i) => {
      const t = s.at + 0.2 + i * 0.9;
      T.push(`tl.set("#${s.id}-p${i}", { opacity: 1 }, ${t.toFixed(2)});`);
      T.push(`tl.fromTo("#${s.id}-p${i}", { scale: 0.7 }, { scale: 1, duration: 0.3, ease: "back.out(1.6)" }, ${t.toFixed(2)});`);
    });
  } else if (s.kind === "enddim") {
    T.push(`tl.fromTo("#dim-${s.id}", { scale: 1 }, { scale: 1.06, duration: ${s.sec}, ease: "none" }, ${s.at});`);
    T.push(`tl.fromTo("#${s.id}-brand", { opacity: 0 }, { opacity: 1, duration: 0.5, ease: "power1.out" }, ${(s.at + 0.2).toFixed(2)});`);
    T.push(`tl.fromTo("#${s.id}-tagline", { opacity: 0 }, { opacity: 1, duration: 0.5, ease: "power1.out" }, ${(s.at + 0.6).toFixed(2)});`);
    cascade(s.lines.map((l, i) => [`#${s.id}-m${i}`, 50, 0.4]), s.at + 1.4);
  } else {
    T.push(`tl.fromTo("#shot-${s.id}", { scale: 1 }, { scale: 1.04, duration: ${s.sec}, ease: "none" }, ${s.at});`);
    T.push(`tl.fromTo("#br-${s.id} .c", { scale: 0 }, { scale: 1, duration: 0.25, ease: "power2.out", stagger: 0.06 }, ${(s.at + 0.4).toFixed(2)});`);
    // explain first (caption with the voice), verdict tag after the explanation lands
    const tagIn = s.at + Math.min(1.5, s.sec * 0.4);
    T.push(`tl.fromTo("#tag-${s.id}", { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.3, ease: "power1.out" }, ${tagIn.toFixed(2)});`);
    const capOut = s.sec > 1 ? s.at + s.sec - 0.4 : s.at + s.sec - 0.1;
    T.push(`tl.fromTo("#cap-${s.id}", { opacity: 0 }, { opacity: 1, duration: 0.3, ease: "power1.out" }, ${(s.at + 0.35).toFixed(2)});`);
    if (s.sec > 0.8) T.push(`tl.fromTo("#cap-${s.id}", { opacity: 1 }, { opacity: 0, duration: 0.3, ease: "power1.in", immediateRender: false }, ${capOut.toFixed(2)});`);
  }
}

// --- audio: per-scene VO (31 clips, aligned to scene starts) + bed + riser + beats ---
const voTags = S.map((s) => `      <audio id="evo-${s.id}" src="assets/evo/${s.id}.wav" data-audio-group="voiceover" data-start="${s.at}" data-duration="${voDur(s.id)}"></audio>`).join("\n");
const ticks = [67, 70.5, 74, 77.5].map((t, i) => `      <audio id="sfx-tick-${i + 1}" src="assets/sfx-tick.wav" data-audio-group="sfx" data-start="${t}" data-duration="0.06"></audio>`).join("\n");
const stings = [80.9, 120.8, 159.3].map((t, i) => `      <audio id="sfx-sting-${i + 1}" src="assets/sfx-sting.wav" data-audio-group="sfx" data-start="${t}" data-duration="0.4"></audio>`).join("\n");
const audio = voTags + ticks + stings
  + `\n      <audio id="sfx-pulse" src="assets/sfx-pulse.wav" data-audio-group="sfx" data-start="99" data-duration="9"></audio>`
  + `\n      <audio id="music-bed" src="assets/bed-180.wav" data-start="0" data-duration="180"></audio>`
  + `\n      <audio id="sfx-riser" src="assets/riser.wav" data-audio-group="sfx" data-start="86" data-duration="3"></audio>`;

const html = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=${W}, height=${H}" />
    <title>LIGHTDAY — the engine cut</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"><\/script>
    <style>
      :root { --ground: ${GROUND}; --ink: #ffffff; --accent: ${ACCENT}; }
      * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body { margin: 0; width: ${W}px; height: ${H}px; overflow: hidden; background: var(--ground); }
      #root { position: relative; width: 100%; height: 100%; overflow: hidden; background: var(--ground); font-family: sans-serif; }
      .clip { position: absolute; }
      .scene { position: absolute; inset: 0; overflow: hidden; }
      .lines { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 0 220px; }
      .tline { display: block; color: var(--ink); font-size: 64px; line-height: 1.3; font-weight: 600; opacity: 0; }
      .tline.acc { color: var(--accent); font-size: 84px; }
      .tline.small { font-size: 44px; margin-top: 18px; }
      .tline.strike { text-decoration: line-through; text-decoration-color: var(--accent); text-decoration-thickness: 6px; color: #8a8178; }
      .brand { display: block; color: var(--accent); font-size: 46px; font-weight: 700; letter-spacing: 0.4em; text-indent: 0.4em; opacity: 0; }
      .tagline { display: block; color: #ffffff; opacity: 0; font-size: 32px; margin: 14px 0 30px; }
      .role { display: block; color: var(--accent); font-size: 110px; font-weight: 700; letter-spacing: -0.02em; opacity: 0; }
      .model { display: block; color: var(--ground); background: var(--ink); font-size: 38px; font-weight: 700; padding: 10px 34px; border-radius: 999px; margin: 24px 0 26px; opacity: 0; }
      .rule { color: var(--accent); font-size: 44px; margin-top: 36px; }
      .pill { display: block; color: var(--ground); background: var(--accent); font-size: 52px; font-weight: 700; padding: 14px 44px; border-radius: 999px; margin: 12px 0; opacity: 0; }
      .dim { position: absolute; inset: -60px; overflow: hidden; }
      .dim img { width: 100%; height: 100%; object-fit: cover; object-position: center; }
      .shade { position: absolute; inset: 0; background: rgba(20, 16, 12, 0.5); }
      .shade.strong { background: rgba(20, 16, 12, 0.72); }
      .shade.max { background: rgba(20, 16, 12, 0.87); }
      .shot { position: absolute; }
      .shot img { display: block; width: 100%; border-radius: 18px; }
      .brackets { position: absolute; inset: -18px; pointer-events: none; }
      .brackets .c { position: absolute; width: 52px; height: 52px; border: 5px solid var(--accent); }
      .brackets .tl { left: 0; top: 0; border-right: 0; border-bottom: 0; border-radius: 12px 0 0 0; transform-origin: 100% 100%; }
      .brackets .tr { right: 0; top: 0; border-left: 0; border-bottom: 0; border-radius: 0 12px 0 0; transform-origin: 0% 100%; }
      .brackets .bl { left: 0; bottom: 0; border-right: 0; border-top: 0; border-radius: 0 0 0 12px; transform-origin: 100% 0%; }
      .brackets .br { right: 0; bottom: 0; border-left: 0; border-top: 0; border-radius: 0 0 12px 0; transform-origin: 0% 0%; }
      .tag { position: absolute; top: -76px; left: 0; background: var(--accent); color: ${GROUND}; font-size: 34px; font-weight: 700; padding: 10px 26px; border-radius: 999px; opacity: 0; white-space: nowrap; }
      .cap { position: absolute; left: 140px; right: 140px; bottom: 34px; background: rgba(10, 8, 6, 0.8); color: var(--ink); font-size: 38px; line-height: 1.35; text-align: center; padding: 16px 26px; border-radius: 14px; opacity: 0; }
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="180" data-width="${W}" data-height="${H}">
${markup}
${audio}
    </div>
    <script>
      const tl = gsap.timeline({ paused: true });
${T.join("\n")}
      window.__timelines["main"] = tl;
      // <seams:auto>
      // </seams:auto>
    </script>
  </body>
</html>
`;
fs.writeFileSync("index.html", html);

// --- engine ledger: one cut-the-curve LEFT row per boundary ---
const seams = S.slice(1).map((s, i) => ({
  id: `${S[i].id}-${s.id}`, cut: s.at, technique: "cut-the-curve LEFT",
  exit: { selector: `#el-${S[i].id}`, axis: "x", dir: -1, dur: 0.26 },
  entry: { selector: `#el-${s.id}`, axis: "x", dir: -1, dur: 0.3 },
}));
fs.writeFileSync("ledger.json", `{"fps": 30, "seams": [\n${seams.map((r) => "  " + JSON.stringify(r)).join(",\n")}\n]}\n`);
console.log("engine index.html written:", S.length, "scenes,", seams.length, "seams");
