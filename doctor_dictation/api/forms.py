"""Multipart form limits for the upload routes.

FastAPI reads a form with Starlette's defaults (``request.form()``), which refuse any TEXT field over 1 MB with a
400. ``FormLimitRoute`` reads the form first with our limit; Starlette keeps the parsed form on the request, so
FastAPI's own read reuses it. Only routes that declare form or file parameters are touched, so a JSON route on the
same router keeps FastAPI's own errors. Files are not limited by this setting (MAX_AUDIO_BYTES, the template image
limit and Caddy's UPLOAD_LIMIT cover them).
"""
from fastapi import params
from fastapi.routing import APIRoute
from starlette.requests import Request

FORM_PART_LIMIT = 5 * 1024 * 1024   # bytes per text field (Starlette's max_part_size)


class FormLimitRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        if not any(isinstance(p.field_info, params.Form) for p in self.dependant.body_params):   # File is a Form
            return handler

        async def read_form_first(request: Request):
            if request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
                await request.form(max_part_size=FORM_PART_LIMIT)
            return await handler(request)

        return read_form_first
