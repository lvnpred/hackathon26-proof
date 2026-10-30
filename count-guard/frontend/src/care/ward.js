import { useEffect, useRef, useState } from "react";
import { call, getJourney, postJourney, uploadJourney } from "../journey";
import { afterRun } from "./clock";
import { CLOCK, STATUS, makeFault } from "./faults";
import { displayName, displayView } from "./names";
import { statusBody, statusQuery } from "./status";

const ROSTER = "cg-ward-roster";
const NOW = "cg-ward-now";
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

function savedRoster() {
  try {
    const roster = JSON.parse(read(ROSTER));
    // A roster saved before the staff board existed is dropped, so the ward reseeds once.
    return Array.isArray(roster?.patients) && typeof roster.board === "string" ? roster : null;
  } catch {
    return null;
  }
}

// What the screen shows: names and every view string lose " (synthetic)". The record on the server keeps it.
const shown = (p) => ({ ...p, name: displayName(p.name), view: displayView(p.view) });

async function withViews(roster) {
  const views = await Promise.all(roster.patients.map((p) => getJourney(p.id)));
  return roster.patients.map((p, i) => ({ ...p, view: views[i] }));
}

async function seed() {
  const roster = await call("/journey/demo/seed", { method: "POST" });
  write(ROSTER, JSON.stringify(roster));
  write(NOW, "0");
  return { patients: await withViews(roster), board: roster.board, nowMs: 0 };
}

// StrictMode runs effects twice in dev, and two screens can mount at once.
// Share one load so a tab never seeds the ward twice.
let pending = null;

export function loadWard() {
  if (!pending) pending = fetchWard().finally(() => { pending = null; });
  return pending;
}

async function fetchWard() {
  const roster = savedRoster();
  if (roster) {
    try {
      const nowMs = Number(read(NOW)) || 0;
      return { patients: await withViews(roster), board: roster.board, nowMs };
    } catch (exc) {
      if (exc.status !== 404) throw exc;
    }
  }
  return seed();
}

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

  useEffect(() => {
    loadWard()
      .then((ward) => {
        setPatients(ward.patients.map(shown));
        setNowMs(ward.nowMs);
        setBoard(ward.board);
      })
      .catch((exc) => setLoadError(exc.message));
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
    setBusy(true);
    try {
      const next = await send();
      swap(id, next);
      const stepped = afterRun(nowMs, next);
      setNowMs(stepped);
      write(NOW, String(stepped));
      return next;
    } catch (exc) {
      setFault(makeFault(id, scope, exc.message));
      return null;
    } finally {
      setBusy(false);
    }
  }

  const act = (id, path, body, scope = path) => run(id, () => postJourney(id, path, { ...body, at_ms: nowMs }), scope);
  const send = (id, path, file, fields) => uploadJourney(id, path, file, { ...fields, at_ms: nowMs });
  const upload = (id, path, file, fields, scope = path) => run(id, () => send(id, path, file, fields), scope);

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
    write(NOW, String(ms));
    setFault(null);
    setBusy(true);
    try {
      const results = await Promise.allSettled(patients.map((p) => postJourney(p.id, "/tick", { at_ms: ms })));
      const views = new Map();
      const failed = [];
      results.forEach((res, i) => {
        if (res.status === "fulfilled") views.set(patients[i].id, res.value);
        else failed.push(`${patients[i].name}: ${res.reason?.message || "failed"}`);
      });
      setPatients((list) => list.map((p) => (views.has(p.id) ? shown({ ...p, view: views.get(p.id) }) : p)));
      if (failed.length) setFault(makeFault(null, CLOCK, `The time moved, but ${failed.join("; ")}`));
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    setFault(null);
    setBusy(true);
    try {
      const ward = await seed();
      setPatients(ward.patients.map(shown));
      setNowMs(ward.nowMs);
      setBoard(ward.board);
    } catch (exc) {
      setFault(makeFault(null, CLOCK, exc.message));
    } finally {
      setBusy(false);
    }
  }

  const find = (id) => patients.find((p) => p.id === id);

  return { patients, board, doctorStatus, setDoctorStatus: chooseDoctorStatus, nowMs, role, setRole, patientBed, setPatientBed, busy, fault, loadError, clearFault, act, upload, ask, jump, reset, find };
}
