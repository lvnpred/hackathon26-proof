import { displayName } from "./names.js";

// The brown bag: boxed strips coloured by how they match the prescription. Pure.
export function stripMatch(row) {
  if (!row) return "not_read";
  if (row.flag === "not_prescribed" || row.prescribed === false) return "not_prescribed";
  return row.flag === "strength_differs" ? "strength_differs" : "prescribed";
}

const TONE = { prescribed: "green", strength_differs: "amber", not_prescribed: "red", not_read: "grey" };
export const stripTone = (match) => TONE[match] || "grey";

export const TONE_COLOUR = { green: "#2e7d32", amber: "#b26a00", red: "#c62828", grey: "#757575" };

export function stripLabel(region, rows) {
  const row = region.row == null ? null : (rows || [])[region.row];
  if (!row) return "not read";
  const match = stripMatch(row);
  if (match === "strength_differs") return `${row.read} · prescribed ${row.rx_strength}`;
  if (match === "not_prescribed") return `${row.read} · not prescribed`;
  return `${row.read} ✓`;
}

const pos = (v, s) => (s >= 1 ? 0 : +((v / (1 - s)) * 100).toFixed(2));

// A background-image crop that shows only the box (normalised [x, y, w, h]) of the photo.
export function cropStyle(bbox, url) {
  if (!bbox) return null;
  const [x, y, w, h] = bbox;
  return { backgroundImage: `url("${url}")`, backgroundSize: `${100 / w}% ${100 / h}%`, backgroundPosition: `${pos(x, w)}% ${pos(y, h)}%` };
}

export const askAboutText = (read) => `About ${read} from my medicines photo: it is not on my prescription.`;

export const markLine = ({ mark, by }) => (mark === "noted" ? `Noted by ${displayName(by)}` : `Discuss with patient · ${displayName(by)}`);

// The region of a read row, for the crop: the first region that points at row `index`.
export const regionOfRow = (regions, index) => (regions || []).find((r) => r.row === index && r.bbox) || null;
