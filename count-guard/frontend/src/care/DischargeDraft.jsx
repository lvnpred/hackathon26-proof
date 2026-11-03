import Provenance from "./Provenance.jsx";
import { madeByModel } from "./provenance.js";
import Source from "./Source.jsx";
import { dischargeLinks, draftSections, FROM_TIMELINE } from "./dischargeDraft.js";

// The discharge draft written from the record: five sections, the wording's source, and the PDF and calendar links.
export default function DischargeDraft({ draft, episodeId, acts = [] }) {
  if (!draft?.timeline) return null;
  const links = dischargeLinks(episodeId);
  return (
    <section className="card" aria-label="Discharge draft">
      <p className="label">Discharge draft</p>
      <p className="small"><Source words={FROM_TIMELINE} prepared={draft.summary_source === "prepared"} /></p>
      <Provenance item={{ id: draft.id, ai: madeByModel(draft) }} events={acts}>
      {draftSections(draft.timeline).map((section) => (
        <div key={section.title}>
          <p className="small"><b>{section.title}</b></p>
          <ul className="small" style={{ margin: 0, paddingLeft: 20 }}>
            {section.lines.map((line, index) => <li key={index}>{line}</li>)}
          </ul>
        </div>
      ))}
      </Provenance>
      <p className="row small">
        <a href={links.pdf} target="_blank" rel="noreferrer">Discharge PDF</a>
        <a href={links.ics} download="follow-up.ics">Follow-up in calendar</a>
      </p>
    </section>
  );
}
