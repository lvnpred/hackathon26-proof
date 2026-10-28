# AppBar

The top bar of every Lightday app: the mark, "lightday · <app>", one status pill and up to two actions.

**Consumer provides:** `appName` (one or two plain words for the job), an optional `subtitle` (who or where, e.g. "Dr. [Doctor name]"), an optional `status` `{tone, label}`, and `actions` (at most two `Button`s, primary first).

- Use one per screen, full width, at the top.
- The status pill reflects the app's live state (Ready, Recording, Synced), not notifications.
- Do not add navigation tabs to it; the apps are small enough not to need them.
- It wraps on a phone: the actions drop under the name.
