import { useState } from "react";
import { PageLead } from "../App";
import { useCareWard } from "./CareShell";
import { findPatient } from "./Patients";
import StateHeader from "./StateHeader";
import { BotCard, DoctorCard, MedicinesCard, ReviewCard } from "./AskCards";

// All drafts live here, so keying this component by patient resets every one of them (P4-R7).
function AskBody({ ward, patient }) {
  const [toDoctor, setToDoctor] = useState({ id: "", text: "" });
  const props = {
    view: patient.view,
    busy: ward.busy,
    act: (path, body, scope) => ward.act(patient.id, path, body, scope),
    upload: (path, file, fields, scope) => ward.upload(patient.id, path, file, fields, scope),
    fault: ward.fault,
    episodeId: patient.id,
  };
  return (
    <>
      <PageLead kicker={patient.name} title="Ask" body="Ask your record, ask the doctor, or send a photo. Answers come from your record or from Dr. Rao." />
      <StateHeader patient={patient} view={patient.view} />
      <BotCard {...props} onAskDoctor={(text) => setToDoctor({ id: `${Date.now()}`, text })} />
      <DoctorCard {...props} fill={toDoctor} />
      <ReviewCard {...props} />
      <MedicinesCard {...props} />
    </>
  );
}

// The patient's own record only: questions, photos and answers for the patient picked in the header.
export default function Ask() {
  const ward = useCareWard();
  const patient = findPatient(ward.patients, ward.patientBed);
  if (!patient) return <p className="empty">{ward.loadError || "Loading your questions…"}</p>;
  return <AskBody key={patient.id} ward={ward} patient={patient} />;
}
