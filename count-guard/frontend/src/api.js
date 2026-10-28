// FastAPI sends a 422 detail as a list of {loc, msg}; name the field, not "[object Object]".
export function detailMessage(detail) {
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = (item.loc || []).filter((part) => part !== "body").join(".");
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join("; ");
  }
  return detail?.message || detail;
}

async function send(path, options) {
  const response = await fetch(path, options);
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const error = new Error(detailMessage(body?.detail) || response.statusText);
    error.status = response.status;
    error.body = body;
    throw error;
  }
  return body;
}

export function createCase(label, itemTypes) {
  return send("/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label, item_types: itemTypes }),
  });
}

export function saveZones(caseId, zones) {
  return send(`/cases/${caseId}/zones`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zones }),
  });
}

export function uploadScenario(caseId, scenario) {
  return send(`/cases/${caseId}/upload?scenario=${encodeURIComponent(scenario)}`, { method: "POST" });
}

export function uploadFile(caseId, file) {
  const form = new FormData();
  form.append("file", file);
  return send(`/cases/${caseId}/upload`, { method: "POST", body: form });
}

export function ledger(caseId) {
  return send(`/cases/${caseId}/ledger`);
}

export function discrepancies(caseId) {
  return send(`/cases/${caseId}/discrepancies`);
}

export function resolveDiscrepancy(id, reason, by) {
  return send(`/discrepancies/${id}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason, by }),
  });
}

export function closeCase(caseId) {
  return send(`/cases/${caseId}/close`, { method: "POST" });
}

export function track(caseId, trackId) {
  return send(`/tracks/${encodeURIComponent(trackId)}?case_id=${encodeURIComponent(caseId)}`);
}

export function health() {
  return send("/health");
}

export const PROP_ZONES = [
  { name: "tray", polygon: [[0.02, 0.05], [0.40, 0.05], [0.40, 0.95], [0.02, 0.95]] },
  { name: "field", polygon: [[0.42, 0.05], [0.70, 0.05], [0.70, 0.95], [0.42, 0.95]] },
  { name: "bucket", polygon: [[0.72, 0.05], [0.98, 0.05], [0.98, 0.95], [0.72, 0.95]] },
];

// Plain titles for the rule kinds; screens keep the rule id and code visible underneath.
export const TITLES = {
  count_mismatch: "Count does not match",
  spoken_vs_camera: "Spoken count and camera differ",
  unaccounted_item: "An item is not accounted for",
  unannounced_add: "Items were added without being said",
  needs_human_look: "A person should look at this",
};

export const ITEM_TYPES =["lap sponge", "gauze swab", "surgical forceps", "scissors", "needle holder"];
