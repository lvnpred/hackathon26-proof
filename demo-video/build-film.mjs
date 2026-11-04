// Generates index.html for the MOVIE CUT from film-beats.json + film-crops.json.
// 21 scenes (F07/F14 split in two), LEFT-current seams stamped later from ledger.json.
// Re-run when assets change: node build-film.mjs
import fs from "node:fs";
import cp from "node:child_process";

const W = 1920, H = 1080, ACCENT = "#e8a33d", GROUND = "#14100c";
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const voDur = (f) => +cp.execSync(`ffprobe -v error -show_entries format=duration -of csv=p=0 assets/fvo/${f}.wav`).toString().trim();

// Scenes: id, start, seconds, kind, payload. F07/F14 split; captions split to match.
const S = [
  { id: "F01", at: 0, sec: 8, kind: "type", lines: ["The most dangerous moment", "in surgery isn't the incision.", "It's the count."], accent: 2, ghost: "14 / 15" },
  { id: "F02", at: 8, sec: 8, kind: "type", lines: ["Tired eyes.", "A tray that must add up.", "At the end of a long operation."] },
  { id: "F03", at: 16, sec: 8, kind: "type", lines: ["When the count is wrong,", "a patient goes back under —", "for something left behind."] },
  { id: "F04", at: 24, sec: 8, kind: "hero", role: "The Watcher", model: "SAM 3.1", power: "It never blinks: every swab, tray to bucket." },
  { id: "F05", at: 32, sec: 8, kind: "hero", role: "The Listener", model: "Muse Voice", power: "It hears every count and drug, to the second." },
  { id: "F06", at: 40, sec: 12, kind: "hero", role: "The Reader", model: "Spark 1.3", power: "Photos, strips, monitors, read in seconds.", rule: "One rule binds them: the AI never decides. A person confirms." },
  { id: "F07a", at: 52, sec: 4, kind: "app", crop: "F07a", tag: "Clinic · admit", cap: "The visit becomes an admission with one press." },
  { id: "F07b", at: 56, sec: 4, kind: "app", crop: "F07b", tag: "Ward · arrived", cap: "Diagnosis, prescription, patient — the ward already knows her." },
  { id: "F08", at: 60, sec: 10, kind: "app", crop: "F08", tag: "The Reader · matched", cap: "The Reader checks the wristband: name, face, bed. Photo matches." },
  { id: "F09", at: 70, sec: 8, kind: "app", crop: "F09", tag: "The Reader · refused", cap: "A bed-rail photo for the consent form? The Reader refuses it." },
  { id: "F10", at: 78, sec: 12, kind: "app", crop: "F10", tag: "The Listener · heard", cap: "The Listener drafts the line — dose, strength, time. The nurse confirms." },
  { id: "F11", at: 90, sec: 12, kind: "app", crop: "F11", tag: "Context, not alarms", cap: "Pressure falling — context, not noise. The strip tells the story." },
  { id: "F12", at: 102, sec: 10, kind: "app", crop: "F12", tag: "The Watcher · watching", cap: "The Watcher follows every swab, tray to bucket — the whole operation through." },
  { id: "F13", at: 112, sec: 12, kind: "app", crop: "F13", tag: "The Watcher · proof", cap: "One sponge never came back. The Watcher rewinds — and shows it as proof.", iris: true },
  { id: "F14a", at: 124, sec: 5, kind: "app", crop: "F14a", tag: "Fourteen of fifteen", cap: "Fourteen of fifteen. One is missing.", early: 0.5 },
  { id: "F14b", at: 129, sec: 5, kind: "app", crop: "F14b", tag: "The gate holds", cap: "Surgery cannot end — not until a person saves the count." },
  { id: "F15", at: 134, sec: 8, kind: "app", crop: "F15", tag: "The person decides", cap: "Found under the drape. Fifteen of fifteen. Surgery ends." },
  { id: "F16", at: 142, sec: 14, kind: "app", crop: "F16", tag: "The draft writes itself", cap: "One press. Mic to theatre to home — on one page, ready to sign." },
  { id: "F17", at: 156, sec: 10, kind: "dimtype", bg: "ward-arrival", lines: ["Counts that add up.", "Swabs that can't go missing.", "Records that write themselves."] },
  { id: "F18", at: 166, sec: 7, kind: "type", lines: ["The Watcher. The Listener. The Reader.", "Three Muse models, one timeline."], accent: 1 },
  { id: "F19", at: 173, sec: 7, kind: "endcard", brand: "LIGHTDAY", tagline: "The count can't be lost.", lines: ["The system formats.", "The doctor decides."], accent: 1 },
];
const crops = Object.fromEntries(JSON.parse(fs.readFileSync("film-crops.json", "utf8")).map((c) => [c.frame, c]));
const beats = JSON.parse(fs.readFileSync("film-beats.json", "utf8"));
const DISPW = 1500, DISPX = (W - DISPW) / 2;

function typeScene(s) {
  const lines = s.lines.map((l, i) => `          <span id="${s.id}-l${i}" class="tline${i === s.accent ? " acc" : ""}">${esc(l)}</span>`).join("\n");
  const ghost = s.ghost ? `\n        <div id="ghost-${s.id}" class="ghost">${esc(s.ghost)}</div>` : "";
  return `      <div id="el-${s.id}" class="scene">${ghost}
        <div class="lines">
${lines}
        </div>
      </div>`;
}
function heroScene(s) {
  const rule = s.rule ? `\n          <span id="${s.id}-rule" class="tline rule">${esc(s.rule)}</span>` : "";
  return `      <div id="el-${s.id}" class="scene">
        <div class="lines">
          <span id="${s.id}-role" class="role">${esc(s.role)}</span>
          <span id="${s.id}-model" class="model">${esc(s.model)}</span>
          <span id="${s.id}-power" class="tline">${esc(s.power)}</span>${rule}
        </div>
      </div>`;
}
function appScene(s) {
  const c = crops[s.crop];
  const dh = Math.round((c.h * DISPW) / c.w);
  const top = Math.round((H - dh) / 2 - 30);
  return `      <div id="el-${s.id}" class="scene">
        <div id="shot-${s.id}" class="shot" style="left:${DISPX}px;top:${top}px;width:${DISPW}px;">
          <img id="img-${s.id}" src="assets/crops/${s.crop}.png" width="${DISPW}" alt="" />
          <div id="br-${s.id}" class="brackets"><i class="c tl"></i><i class="c tr"></i><i class="c bl"></i><i class="c br"></i></div>
          <div id="tag-${s.id}" class="tag">${esc(s.tag)}</div>
        </div>
        <p id="cap-${s.id}" class="cap">${esc(s.cap)}</p>
      </div>`;
}
function dimScene(s) {
  const lines = s.lines.map((l, i) => `          <span id="${s.id}-l${i}" class="tline">${esc(l)}</span>`).join("\n");
  return `      <div id="el-${s.id}" class="scene">
        <div id="dim-${s.id}" class="dim"><img src="assets/${s.bg}.png" alt="" /><div class="shade"></div></div>
        <div class="lines">
${lines}
        </div>
      </div>`;
}
function endScene(s) {
  const lines = s.lines.map((l, i) => `          <span id="${s.id}-l${i}" class="tline${i === s.accent ? " acc" : ""}">${esc(l)}</span>`).join("\n");
  return `      <div id="el-${s.id}" class="scene">
        <div class="lines">
          <span id="${s.id}-brand" class="brand">${esc(s.brand)}</span>
          <span id="${s.id}-tagline" class="tagline">${esc(s.tagline)}</span>
${lines}
        </div>
      </div>`;
}
const markup = S.map((s) => s.kind === "type" ? typeScene(s) : s.kind === "hero" ? heroScene(s) : s.kind === "app" ? appScene(s) : s.kind === "endcard" ? endScene(s) : dimScene(s)).join("\n");

// --- tweens (inner elements only; wrappers belong to the stamped seams) ---
const T = [];
function cascade(ids, at, heavy) {
  // waterfall entry: binary set + Y from below, shrinking gaps
  let t = at;
  ids.forEach(([sel, y, d], i) => {
    T.push(`tl.set("${sel}", { opacity: 1 }, ${t.toFixed(2)});`);
    T.push(`tl.fromTo("${sel}", { y: ${y} }, { y: 0, duration: ${d}, ease: "power4.out" }, ${t.toFixed(2)});`);
    t += i === 0 ? 0.14 : 0.10;
  });
}
for (const s of S) {
  if (s.kind === "type") {
    const ids = s.lines.map((l, i) => [`#${s.id}-l${i}`, i === s.accent ? 70 : 50, i === s.accent ? 0.5 : 0.4]);
    cascade(ids, s.at + 0.15, true);
  } else if (s.kind === "hero") {
    cascade([[`#${s.id}-role`, 70, 0.5], [`#${s.id}-model`, 40, 0.35], [`#${s.id}-power`, 50, 0.4]], s.at + 0.15, true);
    if (s.rule) {
      T.push(`tl.set("#${s.id}-rule", { opacity: 1 }, ${(s.at + 5.2).toFixed(2)});`);
      T.push(`tl.fromTo("#${s.id}-rule", { y: 50 }, { y: 0, duration: 0.4, ease: "power4.out" }, ${(s.at + 5.2).toFixed(2)});`);
    }
  } else if (s.kind === "dimtype") {
    T.push(`tl.fromTo("#dim-${s.id}", { scale: 1 }, { scale: 1.08, duration: ${s.sec}, ease: "none" }, ${s.at});`);
    cascade(s.lines.map((l, i) => [`#${s.id}-l${i}`, 50, 0.4]), s.at + 0.3, true);
  } else if (s.kind === "endcard") {
    T.push(`tl.fromTo("#${s.id}-brand", { opacity: 0 }, { opacity: 1, duration: 0.5, ease: "power1.out" }, ${(s.at + 0.3).toFixed(2)});`);
    T.push(`tl.fromTo("#${s.id}-tagline", { opacity: 0 }, { opacity: 1, duration: 0.5, ease: "power1.out" }, ${(s.at + 0.8).toFixed(2)});`);
    cascade(s.lines.map((l, i) => [`#${s.id}-l${i}`, i === s.accent ? 70 : 50, i === s.accent ? 0.5 : 0.4]), s.at + 1.6, true);
  } else {
    const zoom = (s.early ? s.sec - s.early : s.sec).toFixed(2);
    if (s.iris) {
      T.push(`tl.fromTo("#shot-${s.id}", { clipPath: "circle(0% at 50% 50%)" }, { clipPath: "circle(75% at 50% 50%)", duration: 0.9, ease: "power2.out" }, ${s.at});`);
      T.push(`tl.fromTo("#shot-${s.id}", { scale: 1 }, { scale: 1.04, duration: ${s.sec}, ease: "none" }, ${s.at});`);
    } else {
      T.push(`tl.fromTo("#shot-${s.id}", { scale: 1 }, { scale: 1.04, duration: ${zoom}, ease: "none" }, ${s.at});`);
    }
    T.push(`tl.fromTo("#br-${s.id} .c", { scale: 0 }, { scale: 1, duration: 0.25, ease: "power2.out", stagger: 0.06 }, ${(s.at + 0.4).toFixed(2)});`);
    T.push(`tl.fromTo("#tag-${s.id}", { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.3, ease: "power1.out" }, ${(s.at + 0.7).toFixed(2)});`);
    T.push(`tl.fromTo("#cap-${s.id}", { opacity: 0 }, { opacity: 1, duration: 0.3, ease: "power1.out" }, ${(s.at + 0.1).toFixed(2)});`);
    T.push(`tl.fromTo("#cap-${s.id}", { opacity: 1 }, { opacity: 0, duration: 0.3, ease: "power1.in", immediateRender: false }, ${(s.at + s.sec - 0.4).toFixed(2)});`);
  }
}

// --- audio: 19 VO clips in the voiceover group + the bed (carve comes later) ---
const audio = beats.map((b) => `      <audio id="fvo-${b.frame}" src="assets/fvo/${b.frame}.wav" data-audio-group="voiceover" data-start="${b.start}" data-duration="${voDur(b.frame)}"></audio>`).join("\n")
  + `\n      <audio id="music-bed" src="assets/bed-180.wav" data-start="0" data-duration="180"></audio>`
  + `\n      <audio id="sfx-riser" src="assets/riser.wav" data-audio-group="sfx" data-start="121" data-duration="3"></audio>`;

const html = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=${W}, height=${H}" />
    <title>One patient, two apps — the movie cut</title>
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
      .brand { display: block; color: var(--accent); font-size: 46px; font-weight: 700; letter-spacing: 0.4em; text-indent: 0.4em; opacity: 0; }
      .tagline { display: block; color: #ffffff; opacity: 0; font-size: 32px; margin: 14px 0 46px; }
      .role { display: block; color: var(--accent); font-size: 120px; font-weight: 700; letter-spacing: -0.02em; opacity: 0; }
      .model { display: block; color: var(--ground); background: var(--ink); font-size: 40px; font-weight: 700; padding: 10px 34px; border-radius: 999px; margin: 26px 0 30px; opacity: 0; }
      .rule { color: var(--accent); font-size: 46px; margin-top: 44px; }
      .ghost { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 420px; font-weight: 700; color: #ffffff; opacity: 0.06; }
      .dim { position: absolute; inset: -60px; overflow: hidden; }
      .dim img { width: 100%; height: 100%; object-fit: cover; object-position: center top; }
      .shade { position: absolute; inset: 0; background: rgba(20, 16, 12, 0.5); }
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
console.log("film index.html written:", S.length, "scenes");
