"""uvicorn entry point: `uvicorn doctor_dictation.main:app`."""
from doctor_dictation.api.app import create_app

app = create_app()
