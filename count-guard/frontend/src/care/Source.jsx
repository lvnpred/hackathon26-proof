import AiMark from "./AiMark.jsx";
import { sourceLine } from "./source.js";

// Staff source words, e.g. "Read by camera" (source.js), with " · Prepared" when a prepared result stands behind them.
// Renders nothing when there are no words and nothing prepared.
export default function Source({ words, prepared = false }) {
  const line = sourceLine(words, prepared);
  return line ? <span className="source"><AiMark /> {line}</span> : null;
}
