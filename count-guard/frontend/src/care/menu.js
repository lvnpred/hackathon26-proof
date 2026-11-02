// The dock's extra links: one list, so a screen kept past the freeze cannot sneak into a menu (U11).
// The older screens (camera counter, morning, journey v1) are in count-guard/archive/ (spec §9, U2).
// A kept screen stays routed in App.jsx and is listed in KEPT; `scripts/archive_set.py --keep` leaves its file in place.
export const KEPT = [];

export const MENU = [["/guide", "Guide"]];
