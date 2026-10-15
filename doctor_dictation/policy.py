"""The one place permission rules live. No roles are enforced yet: every signed-in user of a clinic may do
everything except edit a colleague's prescription. Later role rules go inside ``can`` with no route changes."""
from __future__ import annotations

ACTIONS = frozenset({"document.view", "document.reprint", "document.edit", "user.view", "user.create", "user.disable",
                     "user.reset_password", "letterhead.manage"})


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
    if action == "letterhead.manage" and resource is not None:
        owner = resource.get("owner_user_id") if isinstance(resource, dict) else getattr(resource, "owner_user_id", None)
        return owner is None or owner == user.user_id      # a doctor's own letterhead is theirs alone
    return True
