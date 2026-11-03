import AiMark from "./AiMark.jsx";
import { IconPerson } from "./icons.jsx";
import { provClass, provenanceOf, provenanceText } from "./provenance.js";
import "./provenance.css";

// The one AI proposed / person accepted mark (spec §4.3). item and events go to provenanceOf (provenance.js).
// With children it frames them: dashed while proposed, solid once a person acted. item.ai false (rules or a failed
// model call made it) shows no "Proposed by AI".
export default function Provenance({ item, events, children = null }) {
  const p = provenanceOf(item, events);
  if (p.kind === "proposed" && item?.ai === false) return children; // no model made it: no AI mark, no draft frame
  const mark = (
    <span className={children ? "prov-mark" : provClass(p.kind)} data-prov={p.kind}>
      {p.kind === "proposed" ? <AiMark /> : <IconPerson />} {provenanceText(p)}
    </span>
  );
  if (!children) return mark;
  return <div className={`prov-box ${provClass(p.kind)}`} data-prov={p.kind}>{mark}{children}</div>;
}
