// Doctor Dictation for the demo check (spec §11 A8): its own port, a temp database, stub speech and language
// results, and no key. Pure, so the tests can load it; server.mjs starts the process.
export const DD_PORT = 8300;
// The ports the demo check never uses: the owner's DD, CG API and CG web servers.
export const FORBIDDEN_PORTS = [8000, 8100, 5173];
export const DD_PYTHON = "../doctor-dictation/.venv/bin/python"; // relative to count-guard/
export const DD_ARGS = ["-m", "uvicorn", "doctor_dictation.main:app", "--host", "127.0.0.1", "--port", String(DD_PORT)];

// The video patient (spec §12). Every row is verified, so the save gate passes without a person's tick.
export const PATIENT = "M. Fernandes (synthetic)";
export const STUB_FORM = {
  patientName: PATIENT,
  ageSex: "52 F",
  opNo: "",
  diagnosis: ["Right inguinal hernia"],
  complaints: ["Groin pain for 2 weeks"],
  investigations: [],
  rx: [{ form: "Tab.", name: "Paracetamol", strength: "500 mg", dose: "1-1-1", timing: "After food", duration: "5 days", instructions: "", status: "verified" }],
  advice: ["Admit for hernia repair"],
  review: "",
};
export const STUB_TRANSCRIPT = "M. Fernandes, 52 year old woman, synthetic patient. Right inguinal hernia, painful for two weeks. "
  + "Tablet paracetamol 500 mg three times a day after food for five days. Admit for hernia repair.";

// Every secret DD resolves. Present and empty, so neither the shared .env nor a secrets file can fill one in.
const DD_SECRETS = ["OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GROQ_API_KEY", "ASSEMBLYAI_API_KEY", "META_API_KEY", "MODEL_API_KEY", "BASETEN_API_KEY"];
const DD_DROPPED = ["MAKEFLAGS", "MAKELEVEL", "MFLAGS", "DATA_DIR", "DD_PORT", "SECRETS_FILE", "PORT"];

export const urls = (apiPort) => ({ countGuard: `http://127.0.0.1:${apiPort}`, dd: `http://127.0.0.1:${DD_PORT}` });

// env for the DD child: single clinic, temp DB, stub providers, pushing to the demo check's own Count Guard.
export function ddEnv(parent, { dbPath, apiPort, token }) {
  const env = { ...parent };
  for (const k of DD_DROPPED) delete env[k];
  for (const k of DD_SECRETS) env[k] = "";
  return {
    ...env,
    MULTI_CLINIC: "",
    DB_PATH: dbPath,
    ALLOW_STUB_PROVIDERS: "1",
    STT_ENGINE: "stub",
    STT_CHAIN: "stub",
    LLM_PROVIDER: "stub",
    STUB_TRANSCRIPT,
    STUB_LLM_JSON: JSON.stringify(STUB_FORM),
    COUNT_GUARD_URL: urls(apiPort).countGuard,
    CG_SYNC_TOKEN: token,
    DEMO_BANNER: "1",
  };
}

// DD's /health must report stub speech and language models and no Meta or OpenAI key before any click.
export function assertDdOffline(health) {
  const stubs = health?.llm_provider === "stub" && health?.stt_engine_requested === "stub" && health?.stt_engine_active === "stub";
  if (!stubs || health?.meta_configured !== false || health?.openai_configured !== false) {
    throw new Error("Doctor Dictation is not on its stub providers. Stopped before any click; nothing was spent.");
  }
}

// Throws when a port the demo check would use is one of the owner's.
export function refuseOwnerPorts(ports) {
  const bad = ports.filter((p) => FORBIDDEN_PORTS.includes(p));
  if (bad.length) throw new Error(`Port ${bad[0]} belongs to the owner's servers; demo-check uses 8200, 5273 and 8300 only.`);
}
