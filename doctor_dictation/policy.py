"""The one place permission rules live. Admins only: managing the clinic's medicine list and its team (create, disable,
enable, reset a password). Everything else: every signed-in user of a clinic, except editing a colleague's prescription.
Later role rules go inside ``can`` with no route changes."""
from __future__ import annotations

import os

ACTIONS = frozenset({"document.view", "document.reprint", "document.edit", "user.view", "user.create", "user.disable",
                     "user.reset_password", "letterhead.manage", "formulary.manage"})

ADMIN_ONLY = frozenset({"formulary.manage", "user.create", "user.disable", "user.reset_password"})   # "enable" uses user.disable


def _author_id(resource):
    if isinstance(resource, dict):
        return resource.get("author_id")
    return getattr(resource, "author_id", None)


def can(user, action: str, resource=None) -> bool:
    if action not in ACTIONS:
        return False                                  # unknown action: deny
    if action == "document.edit":
        if resource is None:
            return False                              # an edit always names the document
        author = _author_id(resource)
        return author is None or author == user.user_id   # a pre-authorship document (no author) stays editable
    if action in ADMIN_ONLY:
        return getattr(user, "role", "") == "admin"          # the clinic's medicine list and the team: admins only
    if action == "letterhead.manage" and resource is not None:
        owner = resource.get("owner_user_id") if isinstance(resource, dict) else getattr(resource, "owner_user_id", None)
        return owner is None or owner == user.user_id      # a doctor's own letterhead is theirs alone
    return True


def is_owner(user) -> bool:
    """The app owner reviews the shipped lists. ``OWNER_USERNAMES`` (comma-separated, case-insensitive) is read at call time."""
    if user is None:
        return False
    names = {n.strip().casefold() for n in os.environ.get("OWNER_USERNAMES", "").split(",") if n.strip()}
    return str(getattr(user, "username", "") or "").casefold() in names
