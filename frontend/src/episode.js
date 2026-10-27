const KEY = "cg-morning-episode";

async function send(path, options) {
  const response = await fetch(path, options);
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const error = new Error(body?.detail || response.statusText);
    error.status = response.status;
    error.body = body;
    throw error;
  }
  return body;
}

export { send };

export async function loadEpisode() {
  const saved = sessionStorage.getItem(KEY);
  if (saved) {
    const response = await fetch(`/morning/episodes/${saved}`);
    if (response.ok) return response.json();
  }
  const created = await send("/morning/episodes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label: "Synthetic demo, R. Kumar" }),
  });
  sessionStorage.setItem(KEY, created.id);
  return send(`/morning/episodes/${created.id}`);
}

export function remember(id) {
  sessionStorage.setItem(KEY, id);
}

export function startPatient(label) {
  return send("/morning/episodes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  }).then((created) => {
    remember(created.id);
    return send(`/morning/episodes/${created.id}`);
  });
}

export function listPatients() {
  return send("/morning/episodes");
}
