import { faultText } from "./faults";

// An error next to the action that raised it. Renders nothing when the fault belongs elsewhere.
export default function Fault({ fault, episodeId, only, except }) {
  const text = faultText(fault, episodeId, { only, except });
  return text ? <p className="error small" role="alert">{text}</p> : null;
}
