import { Fragment, useState } from "react";
import { PageLead } from "../App";
import { useCareWard } from "./CareShell";
import { findPatient } from "./Patients";
import StateHeader from "./StateHeader";
import { BotCard, DoctorCard, MedicinesCard, ReviewCard } from "./AskCards";

// The patient's own record only: questions, photos and answers for the patient picked in the header.
export default function Ask() {
  const ward = useCareWard();
  const patient = findPatient(ward.patients, ward.patientBed);
  const [toDoctor, setToDoctor] = useState({ id: "", text: "" });
  if (!patient) return <p className="empty">{ward.error || "Loading your questions…"}</p>;
  const props = {
    view: patient.view,
    busy: ward.busy,
    act: (path, body) => ward.act(patient.id, path, body),
    upload: (path, file, fields) => ward.upload(patient.id, path, file, fields),
  };
  // Keyed by patient so a typed question never carries over to the next patient.
  return (
    <Fragment key={patient.id}>
      <PageLead kicker={patient.name} title="Ask" body="Ask your record, ask the doctor, or send a photo. Answers come from your record or from Dr. Rao." />
      <StateHeader patient={patient} view={patient.view} />
      <BotCard {...props} onAskDoctor={(text) => setToDoctor({ id: `${Date.now()}`, text })} />
      <DoctorCard {...props} fill={toDoctor} />
      <ReviewCard {...props} />
      <MedicinesCard {...props} />
    </Fragment>
  );
}
