import { Fragment } from "react";
import { PageLead } from "../App";
import { useCareWard } from "./CareShell";
import { findPatient } from "./Patients";
import StateHeader from "./StateHeader";
import TodayPanel from "../screens/TodayPanel";

export default function Today() {
  const ward = useCareWard();
  const patient = findPatient(ward.patients, ward.patientBed);
  if (!patient) return <p className="empty">{ward.loadError || "Loading your day…"}</p>;
  return (
    <Fragment key={patient.id}>
      <PageLead kicker={patient.name} title="Today" body="What to do now, your medicines and your check-ins." />
      <StateHeader patient={patient} view={patient.view} you />
      {patient.view.state === "home" ? (
        <TodayPanel
          view={patient.view}
          busy={ward.busy}
          act={(path, body) => ward.act(patient.id, path, body)}
          upload={(path, file) => ward.upload(patient.id, path, file)}
          fault={ward.fault}
          episodeId={patient.id}
        />
      ) : (
        <p className="empty small">Check-ins and Need help open once you are home.</p>
      )}
    </Fragment>
  );
}
