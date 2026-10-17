"""The visit day, in one place so tests can inject it (plan I2-b)."""
from datetime import date, datetime


def today() -> date:
    """The server-local calendar day: the day the PDF prints on Save (api/persistence.py) and the OP number uses
    (db/opno.py). A container with no TZ runs on UTC, so set TZ=Asia/Kolkata in the deployment (index Q7)."""
    return datetime.now().astimezone().date()
