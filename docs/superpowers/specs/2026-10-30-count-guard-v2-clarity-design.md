# Count Guard v2 clarity pass: design

Owner request (30 Oct): "go ahead with all of them, commit on a new branch". "Them" means the 11 findings from walking the 31 demo beats in a browser (screenshots at 1280 px). Branch: `count-guard-v2-clarity`, cut from `main` at 2af00f7.

Goal: a first-time viewer can tell, on every screen, **whose** it is, **what matters now**, and **what to press**. No new features. No backend model changes.

Binding constraints:
- `make demo-check` stays green with all 31 beats.
- Backend tests (345), care node tests (91) and demo tests (36) stay green. New behaviour gets new tests.
- The video script `docs/demo/count-guard-v2-video-script.md` matches what the screen says. Its doc test checks every beat's `say` line.
- The no-advice word scan still passes, and buttons keep "Begin".
- Files stay under 500 lines.
- Commits go on this branch only, with `git -c user.name=lvnpred -c user.email=lvnpred@gmail.com`. Never push.

## The 11 changes

C1. **Alerts name their patient.**
- Today the alert strip shows "Patient → This strip reads amlodipine 10 mg…" on Kumar's chart, though it belongs to Das. The first screen shows "Dr. A. Rao → See in clinic" twice with no name.
- Decision: on a patient's chart, the strip shows only that patient's alerts. On list screens (My queue, Patients, Today), each alert starts with the patient's short name, for example "Das · Patient → …".

C2. **An open alert is the top thing on the chart.**
- An open safety alert (BP past its limit, an open swab count, a flagged check) shows as a red banner right under the state header, with its answer form inside it.
- NOW reads "Waiting for <role>'s answer: <alert text>" while the alert is open.
- The same answer form must not appear a second time in the timeline. The timeline keeps a read-only line.

C3. **The doctor gets an action bar.**
- Under NOW/NEXT, the doctor sees large buttons for the actions this state allows:
  - Clinic: **Dictate orders**, **Reference photo**.
  - Ward: **Dictate orders**, **Wound photo**, **Dictate discharge**.
  - Theatre: none.
- Each button opens its panel in place. Panels for actions that weren't chosen stay closed.
- The prescription, strip check and visit buttons (Admit / Close visit / Send to theatre) stay visible as before. The photo control gets a labelled card, not a bare "Choose File".
- Builder's call: the exact markup. If panels can be open by default without hurting the demo, prefer the smaller change.

C4. **One task list.**
- "Orders and tasks" shows one line per task, with its status, who did it and its proof.
- The order header ("Signed by … · Acknowledged by …") stays.
- The duplicate list of the order's lines goes (`care/Chart.jsx:83-85`).
- An order item with no task shows once, without a status.

C5. **Repeating tasks read clearly to the patient.**
- No "To do" next to "Done by".
- A repeating task done at least once reads "Given 10:00 · next due 16:00" for a dose, and "Done 10:00 · next due 11:00" otherwise.
- A task never done reads "Due 10:00".
- A closed task reads "Finished".

C6. **The patient sees patient wording.**
- Theatre tray checks are hidden from the patient.
- Ward checks tied to a task (saline set-up) stay, with plain wording: "Checked from a video: everything planned was seen." or "…something planned was not seen; the nurse was told."
- Timeline lines in the patient view use plain wording, for example:
  - "You were admitted."
  - "You went to theatre."
  - "Your operation finished."
  - "You are back on the ward."
  - "You went home."
  - "The doctor signed 2 orders."
  - "Nurse Meena gave paracetamol."
- Staff lenses keep today's wording.

C7. **Theatre steps are numbered, in order, and shown once.**
- Order: ① Tray check → ② Surgery began → ③ Swab count → ④ Surgery ended → Back to ward. (Tray first: the server refuses a tray check after surgery begins, `video_api.py:56`, and a real tray check precedes incision.)
- The tray result shows once. Drop the repeated "Video checks" entry for a tray check on the theatre screen.

C8. **Ward tasks pause in theatre.**
- While the patient is in theatre, ward tasks show "paused (in theatre)", not "overdue", and raise no due nudges.
- They resume on return to the ward.

C9. **The timeline reads like a day.**
- Each recorded action moves the demo clock forward by 2 minutes, so entries no longer all share one time.
- Builder's call: where this happens (frontend clock or backend). It must keep `make demo-check` green, and it must update any beat text or doc lines that quote a time.

C10. **Small text errors.**
- Leave missing values out of observation lines: "BP 82/54, HR 112", not "SpO2 None, T None".
- Singular/plural: "1 order", "2 orders".
- In the queue table, left-align the Patient column.

C11. **The role switch stays in one place.**
- The Doctor / Nurse / Patient switch sits in the same spot for all three roles.
- The patient picker sits beside the switch, without moving it.

## Out of scope

- New model calls, new states, new data.
- The old `/journey` and `/steps` screens.
