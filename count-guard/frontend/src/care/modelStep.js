import { isPrepared } from "./source.js";

// One model step (spec §4.1): recording, uploading, checking, done or failed, in one plain line.
// The copy here is exact (Global Constraints). Model names show only in the staff lens; the patient lens never names one.

export const SAM = "SAM 3.1";
export const SPARK = "Spark 1.3";
export const SPARK_OPEN = "Spark Open";
export const VOICE = "Muse Voice";

const MODEL = {
  tray: SAM, setup: SAM, swabs: SAM, camera: SAM,
  voice: VOICE, hear: VOICE, dictation: VOICE, audio: VOICE,
  photo: SPARK, verdict: SPARK, strips: SPARK, medicines: SPARK, monitor: SPARK, review: SPARK,
  wording: SPARK, card: SPARK, handover: SPARK, discharge: SPARK, orders: SPARK,
  reconciler: SPARK_OPEN,
};

// A capability -> the model's display name, or null when no model stands behind it.
export function modelOf(capability) {
  return MODEL[capability] || null;
}

// The source word the backend uses when a model could not be reached (switches.UNAVAILABLE).
const UNAVAILABLE = "unavailable";
export const MODEL_UNAVAILABLE = "model unavailable";

function unavailable(x) {
  if (x.source === UNAVAILABLE || x.heard_by === UNAVAILABLE) return true;
  return (x.calls || []).some((c) => c.source === UNAVAILABLE);
}

// A call's result -> "live", "prepared" (a fixture stood in) or "failed" (no result, or the model was unavailable).
export function modeFrom(result) {
  if (!result) return "failed";
  if (unavailable(result)) return "failed";
  return isPrepared(result) ? "prepared" : "live";
}

// Audio and video get longer than a photo before the step gives up.
const LONG = new Set(["recording", "video", "audio", "clip"]);
export function timeoutFor(what) {
  return LONG.has(what) ? 120000 : 60000;
}

const mss = (seconds) => {
  const s = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
const whole = (seconds) => Math.max(0, Math.floor(seconds || 0));
const tenths = (seconds) => (Math.round((seconds || 0) * 10) / 10).toFixed(1);
const AUDIO = new Set(["recording", "audio"]);

function patientChecking(step) {
  const listening = AUDIO.has(step.what) || step.model === VOICE;
  return listening ? "Listening to your recording…" : "Reading your photo…";
}

// stepText(step, { lens }) -> the one line the card shows. Idle is "".
export function stepText(step, { lens = "staff" } = {}) {
  const patient = lens === "patient";
  switch (step?.stage) {
    case "recording":
      return `Recording ${mss(step.seconds)} — tap the mic to finish`;
    case "uploading": {
      const what = step.what || "file";
      return Number.isFinite(step.percent) ? `Uploading ${what}… ${step.percent}%` : `Uploading ${what}…`;
    }
    case "checking":
      if (patient) return `${patientChecking(step)} ${whole(step.seconds)} s`;
      return step.model ? `Checking with ${step.model}… ${whole(step.seconds)} s` : `Checking… ${whole(step.seconds)} s`;
    case "done":
      if (step.mode === "prepared") return "Done · Prepared (no live model)";
      if (patient || !step.model) return "Done";
      return `Done · live (${step.model}, ${tenths(step.seconds)} s)`;
    case "failed":
      return `Didn't work: ${step.reason || "no answer"}`;
    default:
      return "";
  }
}

export const IDLE = Object.freeze({ stage: "idle" });

const realClock = {
  now: () => Date.now(),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (id) => clearTimeout(id),
  setInterval: (fn, ms) => setInterval(fn, ms),
  clearInterval: (id) => clearInterval(id),
};

// createStepRunner: the step's state machine without React, so it can be tested with a fake clock.
// `onChange(step)` hears every change; after dispose() it hears nothing more and any call in flight is aborted.
// `capability` is read once: a card whose capability changes gets a new runner (useModelStep does that).
export function createStepRunner({ capability, clock = realClock, onChange = () => {} } = {}) {
  const model = modelOf(capability);
  let step = IDLE;
  let gone = false;
  let ticker = null;
  let timer = null;
  let ctl = null;
  let token = 0;
  let last = null;

  const set = (next) => {
    if (gone) return;
    step = next;
    onChange(step);
  };
  const stopTimers = () => {
    if (ticker !== null) clock.clearInterval(ticker);
    if (timer !== null) clock.clearTimeout(timer);
    ticker = null;
    timer = null;
  };
  const tickFrom = (start, make) => {
    if (ticker !== null) clock.clearInterval(ticker);
    ticker = clock.setInterval(() => set(make((clock.now() - start) / 1000)), 1000);
  };
  const finish = () => {
    stopTimers();
    ctl = null;
  };

  // run(fn, { what, upload }): `what` names the thing sent ("photo", "recording") for the wording and the timeout.
  // `upload` (default: true when `what` is given) means fn reports upload progress, so the step starts at
  // "Uploading {what}… 0%"; pass `upload: false` for a JSON call that still names its `what`.
  async function run(fn, { what, upload = Boolean(what) } = {}) {
    last = { fn, what, upload };
    ctl?.abort();
    stopTimers();
    const mine = ++token;
    const here = new AbortController();
    ctl = here;
    const timeoutMs = timeoutFor(what);
    let checkedAt = clock.now();
    let timedOut = false;
    const check = () => {
      checkedAt = clock.now();
      set({ stage: "checking", what, model, seconds: 0 });
      tickFrom(checkedAt, (s) => ({ stage: "checking", what, model, seconds: s }));
    };
    const onProgress = (percent) => {
      if (mine !== token || step.stage === "checking") return;
      if (percent >= 100) check();
      else set({ stage: "uploading", what, model, percent });
    };
    let expire;
    const expired = new Promise((resolve) => { expire = resolve; });
    timer = clock.setTimeout(() => {
      timedOut = true;
      here.abort();
      expire();
    }, timeoutMs);
    if (upload) set({ stage: "uploading", what, model, percent: 0 });
    else check();
    try {
      const result = await Promise.race([fn({ onProgress, signal: here.signal, timeoutMs }), expired]);
      if (mine !== token || gone) return null;
      if (timedOut) throw new Error(`no answer in ${timeoutMs / 1000} s`);
      const mode = modeFrom(result);
      const seconds = (clock.now() - checkedAt) / 1000;
      if (mode === "failed") set({ stage: "failed", what, model, reason: result ? MODEL_UNAVAILABLE : "no answer" });
      else set({ stage: "done", what, model, mode, seconds });
      finish();
      return result;
    } catch (exc) {
      if (mine !== token || gone) return null;
      finish();
      if (exc?.name === "AbortError" && !timedOut) {
        set(IDLE); // stopped on purpose (unmount, reset): no fault
        return null;
      }
      const reason = timedOut ? `no answer in ${timeoutMs / 1000} s` : exc?.message || "no answer";
      set({ stage: "failed", what, model, reason });
      return null;
    }
  }

  return {
    get step() { return step; },
    get disposed() { return gone; },
    run,
    retry: () => (last ? run(last.fn, { what: last.what, upload: last.upload }) : Promise.resolve(null)),
    startRecording() {
      token += 1; // a call still in flight is dropped
      ctl?.abort();
      finish();
      const start = clock.now();
      set({ stage: "recording", model, seconds: 0 });
      tickFrom(start, (s) => ({ stage: "recording", model, seconds: s }));
    },
    stopRecording() {
      stopTimers();
      set(IDLE);
    },
    reset() {
      token += 1;
      ctl?.abort();
      finish();
      set(IDLE);
    },
    dispose() {
      token += 1;
      ctl?.abort();
      finish();
      gone = true;
    },
  };
}

// stepSlot(make): holds one runner across React StrictMode's mount -> cleanup -> mount. `mount()` returns the
// cleanup that disposes the runner it mounted; `get()` makes a fresh runner whenever the held one was disposed,
// so a remounted card never keeps a dead runner (whose run() would return null even on success).
export function stepSlot(make) {
  let held = null;
  const get = () => {
    if (!held || held.disposed) held = make();
    return held;
  };
  return {
    get,
    mount() {
      const own = get();
      return () => own.dispose();
    },
  };
}
