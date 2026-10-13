"""Letterhead templates (spec 7A): clean the image, recreate it with a vision LLM, review, accept."""


class TemplateError(Exception):
    """A rule failed. ``status`` is the HTTP status the route answers; str(e) is safe to show."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
