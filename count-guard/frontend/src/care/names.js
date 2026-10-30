// Display-only name helpers: the data keeps the " (synthetic)" tag, the screen never shows it.
export const displayName = (label) => (label == null ? "" : String(label).replaceAll(" (synthetic)", "").trim());

export const shortName = (label) => displayName(label).split(",")[0].trim();

// Deep copy with displayName applied to every string; numbers, booleans and null pass through.
export function displayView(value) {
  if (typeof value === "string") return displayName(value);
  if (Array.isArray(value)) return value.map(displayView);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, displayView(v)]));
  return value;
}
