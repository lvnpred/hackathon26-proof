import AiMark from "./AiMark.jsx";

// Staff source words, e.g. "Read by camera" (source.js). Renders nothing when there are no words.
export default function Source({ words }) {
  return words ? <span className="source"><AiMark /> {words}</span> : null;
}
