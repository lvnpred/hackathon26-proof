import { useEffect, useRef, useState } from "react";
import { call, getJourney, getWard, postClock, postJourney, uploadJourney } from "../journey";
import { afterRun } from "./clock";
import { CLOCK, STATUS, makeFault } from "./faults";
import { displayName, displayView } from "./names";
import { rosterFrom, wardPollIntervalMs } from "./roster";
import { statusBody, statusQuery } from "./status";

// The roster and the clock live on the server (GET /journey/ward). Only the screen's own choices stay here.
const ROLE = "cg-role";
const PATIENT = "cg-patient";

// sessionStorage can throw (private window, blocked site data); the ward still works without it.
function read(key) {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    // keep going without storage
  }
}

// What the screen shows: names and every view string lose " (synthetic)". The record on the server keeps it.
const shown = (p) => ({ ...p, name: displayName(p.name), view: displayView(p.view) });

async function withViews(roster) {
  const views = await Promise.all(roster.patients.map((p) => getJourney(p.id)));
  return { ...roster, patients: roster.patients.map((p, i) => ({ ...p, view: views[i] })) };
}

async function readWard() {
  return withViews(rosterFrom(await getWard()));
}

// A seed is a fresh ward: the server clears the beds and the clock, then registers three patients.
async function seed() {
  await call("/journey/demo/seed", { method: "POST" });
  return readWard();
}

// StrictMode runs effects twice in dev, and two screens can mount at once.
// Share one load so a tab never seeds the ward twice.
let pending = null;

export function loadWard() {
  if (!pending) pending = fetchWard().finally(() => { pending = null; });
  return pending;
}

// An empty server (first start) is seeded once; otherwise every tab shows the same ward.
async function fetchWard() {
  const ward = await readWard();
  return ward.patients.length || ward.board ? ward : seed();
}

const visible = () => typeof document === "undefined" || document.visibilityState !== "hidden";

// One view per patient. act() and upload() swap in the returned view; jump() ticks everyone.
export function useWard() {
  const [patients, setPatients] = useState([]);
  const [nowMs, setNowMs] = useState(0);
  const [role, setRoleState] = useState(() => read(ROLE) || "nurse");
  const [board, setBoard] = useState("");
  const [patientBed, setPatientBedState] = useState(() => read(PATIENT) || "4");
  const [busy, setBusy] = useState(false);
  const [fault, setFault] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [doctorStatus, setDoctorStatus] = useState(null);
  const statusSeq = useRef(0); // a reply to a read that began before a newer one or a POST is dropped
  const wardSeq = useRef(0); // the same for the ward list: a write makes older reads stale
  const busyRef = useRef(false); // no poll while a write or the first load runs
  const lastWard = useRef("");

  // A poll that brings back the same ward changes nothing, so the screens and the status chip stay still.
  function apply(ward) {
    const text = JSON.stringify(ward);
    if (text === lastWard.current) return;
    lastWard.current = text;
    setPatients(ward.patients.map(shown));
    setNowMs(ward.nowMs);
    setBoard(ward.board);
  }

  // Read the ward again; the reply is dropped if a write began meanwhile.
  async function refresh(load = readWard) {
    const mine = ++wardSeq.current;
    const ward = await load();
    if (mine === wardSeq.current) apply(ward);
    return ward;
  }

  function startWrite() {
    wardSeq.current += 1;
    lastWard.current = ""; // the screen may now differ from the last read, so the next read always lands
    busyRef.current = true;
    setBusy(true);
  }

  function endWrite() {
    busyRef.current = false;
    setBusy(false);
  }

  useEffect(() => {
    busyRef.current = true; // no poll before the first load (it may be seeding the ward)
    refresh(loadWard)
      .catch((exc) => setLoadError(exc.message))
      .finally(() => { busyRef.current = false; });
    const timer = setInterval(() => {
      if (visible() && !busyRef.current) refresh().catch(() => {}); // a missed read waits for the next one
    }, wardPollIntervalMs());
    return () => clearInterval(timer);
  }, []);

  // The chip follows the ward: ask again whenever a record or the clock changes. An error keeps the last status.
  useEffect(() => {
    if (!board || !patients.length) return undefined;
    let live = true;
    const mine = ++statusSeq.current;
    call(statusQuery(board, patients.map((p) => p.id), nowMs))
      .then((status) => { if (live && mine === statusSeq.current) setDoctorStatus(status); })
      .catch(() => {});
    return () => { live = false; };
  }, [board, patients, nowMs]);

  const clearFault = () => setFault(null);

  async function chooseDoctorStatus(choice) {
    setFault(null);
    statusSeq.current += 1;
    try {
      const body = statusBody(choice, nowMs, board, patients.map((p) => p.id));
      const reply = await call("/journey/staff/doctor", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      statusSeq.current += 1; // reads that began before this reply must not overwrite it
      setDoctorStatus(reply);
    } catch (exc) {
      setFault(makeFault(null, STATUS, exc.message));
    }
  }

  function setRole(next) {
    write(ROLE, next);
    setRoleState(next);
  }

  function setPatientBed(bed) {
    write(PATIENT, bed);
    setPatientBedState(bed);
  }

  function swap(id, view) {
    setPatients((list) => list.map((p) => (p.id === id ? shown({ ...p, view }) : p)));
  }

  async function run(id, send, scope) {
    setFault(null);
    startWrite();
    try {
      const next = await send();
      swap(id, next);
      // Each recorded action takes a step of demo time; the server clock moves with it for every patient.
      const stepped = afterRun(nowMs, next);
      setNowMs(stepped);
      try {
        await postClock(stepped);
        await refresh();
      } catch (exc) {
        setFault(makeFault(null, CLOCK, `Saved, but the time did not move: ${exc.message}`));
      }
      return next;
    } catch (exc) {
      setFault(makeFault(id, scope, exc.message));
      return null;
    } finally {
      endWrite();
    }
  }

  const act = (id, path, body, scope = path) => run(id, () => postJourney(id, path, { ...body, at_ms: nowMs }), scope);
  const send = (id, path, file, fields) => uploadJourney(id, path, file, { ...fields, at_ms: nowMs });
  const upload = (id, path, file, fields, scope = path) => run(id, () => send(id, path, file, fields), scope);

  // A nurse's Seen is bookkeeping, not an action: it swaps the view and leaves the clock and busy flag alone.
  // A failure is dropped; the chart tries again the next time it opens.
  async function markSeen(id, checkinId, by) {
    try {
      swap(id, await postJourney(id, `/checkins/${checkinId}/seen`, { by, at_ms: nowMs }));
      return true;
    } catch {
      return false;
    }
  }

  // Like upload, but returns the JSON without swapping the view (a proposal is not a record).
  async function ask(id, path, file, fields, scope = path) {
    setFault(null);
    setBusy(true);
    try {
      return await send(id, path, file, fields);
    } catch (exc) {
      setFault(makeFault(id, scope, exc.message));
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function jump(ms) {
    if (ms <= nowMs || !patients.length) return;
    setNowMs(ms);
    setFault(null);
    startWrite();
    try {
      await postClock(ms);
      const results = await Promise.allSettled(patients.map((p) => postJourney(p.id, "/tick", { at_ms: ms })));
      const views = new Map();
      const failed = [];
      results.forEach((res, i) => {
        if (res.status === "fulfilled") views.set(patients[i].id, res.value);
        else failed.push(`${patients[i].name}: ${res.reason?.message || "failed"}`);
      });
      setPatients((list) => list.map((p) => (views.has(p.id) ? shown({ ...p, view: views.get(p.id) }) : p)));
      if (failed.length) setFault(makeFault(null, CLOCK, `The time moved, but ${failed.join("; ")}`));
    } catch (exc) {
      setFault(makeFault(null, CLOCK, exc.message));
    } finally {
      endWrite();
    }
  }

  // Reset reseeds the ward; the server puts its clock back to Day 0 09:00.
  async function reset() {
    setFault(null);
    startWrite();
    try {
      apply(await seed());
    } catch (exc) {
      setFault(makeFault(null, CLOCK, exc.message));
    } finally {
      endWrite();
    }
  }

  const find = (id) => patients.find((p) => p.id === id);

  return { patients, board, doctorStatus, setDoctorStatus: chooseDoctorStatus, nowMs, role, setRole, patientBed, setPatientBed, busy, fault, loadError, clearFault, act, upload, markSeen, ask, jump, reset, find };
}
