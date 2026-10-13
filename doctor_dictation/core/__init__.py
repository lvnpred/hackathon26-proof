"""Pure domain logic: no web framework, no network clients, no database.

`tests/test_core_purity.py` enforces that nothing in this package imports
fastapi, httpx, sqlite3, or doctor_dictation.{providers,db,api,pdf}.
"""
