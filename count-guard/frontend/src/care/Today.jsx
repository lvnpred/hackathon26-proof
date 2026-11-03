import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { DoctorChip, useCareWard } from "./CareShell";
import { findPatient } from "./Patients";
import { answerByLine, doctorQuestions } from "./askText";
import { greeting, todayFolds, whereWords } from "./today.js";
import NextUp from "./NextUp.jsx";
import { displayName } from "./names";
import { checkinStatusLine, readOpened, unreadLine } from "./thread.js";
import { CheckIn, MyCard, NeedHelp } from "./legacy/PatientCard";
import { Nudges, Reminders, Strips } from "./legacy/TodayPanel";
import DayPlan from "./DayPlan.jsx";
import { dayPlanMoment } from "./moments.js";

function Answered({ view }) {
  const answered = doctorQuestions(view).filter((q) => q.answer);
  return (
    <div className="stack">
      {answered.map((q) => (
        <div className="stack" key={q.id}>
          <p><b>{q.text}</b></p>
          <p>{q.answer.text}</p>
          <p className="small muted">{answerByLine(q.answer)}</p>
        </div>
      ))}
      <Link to="/ask">Ask a question →</Link>
    </div>
  );
}

export default function Today() {
  const ward = useCareWard();
  const patient = findPatient(ward.patients, ward.patientBed);
  if (!patient) return <p className="empty">{ward.loadError || "Loading your day…"}</p>;
  // Keyed by patient so the check-in and help panels start closed after a patient switch.
  return <TodayBody key={patient.id} ward={ward} patient={patient} />;
}

function TodayBody({ ward, patient }) {
  const [checkingIn, setCheckingIn] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const navigate = useNavigate();
  const { view } = patient;
  const read = (view.ask?.medicines || []).at(-1);
  const common = {
    view,
    busy: ward.busy,
    act: (path, body) => ward.act(patient.id, path, body),
    fault: ward.fault,
    episodeId: patient.id,
  };
  const unread = unreadLine(view, readOpened(patient.id));
  // The check-in form unmounts on save, so its own confirmation goes with it; this line comes from the record (PF-2).
  const sent = checkinStatusLine(view, ward.nowMs);
  const upload = (path, file) => ward.upload(patient.id, path, file);
  const folds = {
    card: <MyCard card={view.card} episodeId={patient.id} />,
    medicines: (
      <>
        <DayPlan
          plan={view.day_plan} moment={dayPlanMoment(view)} episodeId={patient.id} regions={read?.regions || []} onAsk={(ask) => navigate("/ask", { state: { ask } })}
          photoUrl={view.day_plan?.photo_id ? `/journey/episodes/${patient.id}/photos/${view.day_plan.photo_id}` : ""}
        />
        <Reminders {...common} />
      </>
    ),
    strips: <Strips {...common} upload={upload} />,
    ask: <Answered view={view} />,
  };
  return (
    <>
      <div className="row between greeting-row">
        <h1>{greeting(patient.name)}</h1>
        <DoctorChip status={ward.doctorStatus} />
      </div>
      <NextUp view={view} nowMs={ward.nowMs} />
      <section className="card" aria-label="Your status">
        <p className="next-text">{whereWords(view.state, ward.nowMs)}</p>
        <p>{displayName(view.now_next?.you_now)}</p>
        {unread && <p className="note">{unread}</p>}
        {sent && <p className="note" role="status">{sent}</p>}
      </section>
      <Nudges {...common} />
      {/* Check-in, the folds and Need help show in every state (clarity §4.4); the server takes them in any state. */}
      {checkingIn ? (
        <CheckIn card={view.card} {...common} onDone={() => setCheckingIn(false)} />
      ) : (
        <button onClick={() => setCheckingIn(true)}>Open check-in</button>
      )}
      {todayFolds(view).map(({ key, title }) => (
        <details className="card fold" key={key}>
          <summary>{title}</summary>
          {folds[key]}
        </details>
      ))}
      <div className="help-bar" role="region" aria-label="Need help">
        <span>Feeling worse?</span>
        <button aria-expanded={helpOpen} onClick={() => setHelpOpen(!helpOpen)}>Need help now</button>
      </div>
      {helpOpen && (
        <section className="card help-sheet" aria-label="Need help sheet">
          <NeedHelp {...common} />
        </section>
      )}
    </>
  );
}
