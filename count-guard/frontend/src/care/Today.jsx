import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { DoctorChip, useCareWard } from "./CareShell";
import { findPatient } from "./Patients";
import { answerByLine, doctorQuestions } from "./askText";
import { greeting, nextWords, todayFolds, whereWords } from "./today.js";
import { displayName } from "./names";
import { CheckIn, MyCard, NeedHelp } from "../screens/PatientCard";
import { Medicines, Nudges, Reminders, Strips } from "../screens/TodayPanel";

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
  const [checkingIn, setCheckingIn] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const patient = findPatient(ward.patients, ward.patientBed);
  if (!patient) return <p className="empty">{ward.loadError || "Loading your day…"}</p>;
  const { view } = patient;
  const home = view.state === "home";
  const common = {
    view,
    busy: ward.busy,
    act: (path, body) => ward.act(patient.id, path, body),
    fault: ward.fault,
    episodeId: patient.id,
  };
  const upload = (path, file) => ward.upload(patient.id, path, file);
  const folds = {
    card: <MyCard card={view.card} />,
    medicines: (
      <>
        <Medicines schedule={view.schedule || []} />
        <Reminders {...common} />
      </>
    ),
    strips: <Strips {...common} upload={upload} />,
    ask: <Answered view={view} />,
  };
  return (
    <Fragment key={patient.id}>
      <div className="row between greeting-row">
        <h1>{greeting(patient.name)}</h1>
        <DoctorChip status={ward.doctorStatus} />
      </div>
      <section className="card" aria-label="Your status">
        <p className="next-text">{whereWords(view.state, ward.nowMs)}</p>
        <p>{displayName(view.now_next?.you_now)}</p>
        <p className="small">{nextWords(view)}</p>
      </section>
      <Nudges {...common} />
      {home ? (
        <>
          {checkingIn ? (
            <CheckIn card={view.card} {...common} />
          ) : (
            <button className="primary" onClick={() => setCheckingIn(true)}>Open check-in</button>
          )}
          {todayFolds(view).map(({ key, title }) => (
            <details className="card fold" key={key}>
              <summary>{title}</summary>
              {folds[key]}
            </details>
          ))}
          <div className="help-bar" role="region" aria-label="Need help">
            <span>Feeling worse?</span>
            <button className="primary" aria-expanded={helpOpen} onClick={() => setHelpOpen(!helpOpen)}>Need help now</button>
          </div>
          {helpOpen && (
            <section className="card help-sheet" aria-label="Need help sheet">
              <NeedHelp {...common} />
            </section>
          )}
        </>
      ) : (
        <p className="empty small">Check-ins and Need help open once you are home.</p>
      )}
    </Fragment>
  );
}
