# hackathon26

Two apps in one repo. Each keeps its own code, tests and README. They share one `.env` and run on separate ports.

| App | Folder | What it does | Port |
| --- | --- | --- | --- |
| Doctor Dictation | [`doctor-dictation/`](doctor-dictation/README.md) | Spoken visit → checked prescription → PDF | `DD_PORT` 8000 |
| Count Guard | [`count-guard/`](count-guard/README.md) | One patient's care timeline: strips, swab count, drug log, discharge | web `CG_WEB_PORT` 5173, API `CG_API_PORT` 8100 |

Cross-app plans live in [`docs/hackathon/`](docs/hackathon/README.md).

## Run

```bash
cp .env.example .env   # once; fill in keys only for live model calls
make setup             # both virtualenvs and the Count Guard frontend
make dev               # all three servers
make test              # both test suites
```

`make dd` or `make cg` runs one app. Change a port in `.env`, not in code.

## The shared .env

- **Shared:** the three ports, and `META_API_KEY`, the one Meta Model API key for the Muse models in both apps.
- **Doctor Dictation:** finds the root `.env` by walking up from its package. `doctor_dictation/secrets.json` still wins for secrets.
- **Count Guard:** reads `count-guard/.env` first, if there is one, then the root `.env`.
- A variable already set in the shell wins over both files.

Production deploys of Doctor Dictation still use `doctor-dictation/.env.production` (see `doctor-dictation/docs/deploy/`).
