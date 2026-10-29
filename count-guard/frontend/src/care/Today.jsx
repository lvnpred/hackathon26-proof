import { PageLead } from "../App";
import { useCareWard } from "./CareShell";
import { findKumar } from "./Patients";
import TodayPanel from "../screens/TodayPanel";

export default function Today() {
  const ward = useCareWard();
  const patient = findKumar(ward.patients);
  if (!patient) return <p className="empty">{ward.error || "Loading your day…"}</p>;
  return (
    <>
      <PageLead kicker={patient.name} title="Today" body="What to do now, your medicines and your check-ins." />
      <TodayPanel
        view={patient.view}
        busy={ward.busy}
        act={(path, body) => ward.act(patient.id, path, body)}
        upload={(path, file) => ward.upload(patient.id, path, file)}
      />
    </>
  );
}
