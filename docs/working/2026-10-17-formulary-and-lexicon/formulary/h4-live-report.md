# I1-h4 live browser check (Team "Clinic medicines" tab)

Date 2026-10-17. Playwright against a multi-clinic instance on 127.0.0.1:8800 (temp DATA_DIR, stub LLM/STT, empty provider keys, DB_PATH unset). No code changed, no git writes. Clinics: alpha (adm.alpha = doctor role, admin.alpha = admin, doc.alpha = doctor), beta (adm.beta = doctor role, admin.beta = admin, doc.beta = doctor).

Served files equal the worktree (SHA-256 fetched in the signed-in page):
team.js 3657b999...f0770, team.css f9037ecf...d4978, index.html 7b47d37a...31e99.

## Result per step

1. PASS. Admin A: tab strip "People" (selected) and "Clinic medicines", both 44px high. People panel unchanged: 4 user rows, Disable/Reset buttons, Add-user form. Added user "temp.one": "Password ready" box shown with the temporary password, Copy and "Done, hide it".
2. PASS with deviations. A lists Zorbexin and Quorabex: "2 documents", last seen 17/10/2026 09:52:55, Added by "Dan Doctor". Null added_by and an unknown id (stubbed) show "Unknown"; null last_seen shows "Never". Empty (clinic B, real): "Nothing learned yet." Stubbed 503 JSON: "The server is busy. Try again in a moment." 503 plain text: same. 422 {"detail":[{msg}]}: "value is not a valid integer". 500 html: "Something went wrong (code 500). Try again." Never "[object Object]" or JSON. Deviations: no "generic" and no "first seen" column (table is Medicine, Confirmed on, Last seen, Added by, Actions; the API returns generic and first_seen_at); no loading state (see concerns).
3. PASS. Doctor A: `role=tab`/`tablist` count 0, no "Clinic medicines" text, no #teamMeds. GET /api/v1/formulary 200 (lists Quorabex); DELETE 403 {"error":"You are not allowed to do that"}. Single mode on 8801 not run.
4. PASS. Cancel: no DELETE sent, row kept, focus stays on the Remove button. Confirm (native dialog text: "Remove Zorbexin from your clinic's medicines? Doctors will be asked about it again, and it comes back only after two new documents confirm it."): while pending (DELETE delayed 6 s) every Remove button disabled, dialog aria-busy=true; afterwards row gone, live region (role=status) reads "Removed Zorbexin. It comes back only after two new documents confirm it.", focus on #teamTabMeds. Stale second tab, Remove again: red alert box "no such medicine", list reloaded (only Quorabex), focus on the tab button.
5. PASS. Clinic A doctor, check-row "Zorbexin": before removal verified / source clinic; after removal unknown-medicine / source lexicon. Clinic B doctor: unknown-medicine (source lexicon) before and after. B admin DELETE /api/v1/formulary/2 (A's Quorabex): 404 "no such medicine", A's list unchanged. After removal, two new saves revived the same row (id 1, count 2).
6. PASS. Learn rules rejected "Zorb<b>exin" (two saves, not listed), so XSS tested with a stubbed list containing `<img src=x onerror=window.__x=1>`: rendered as visible text, 0 img elements, window.__x undefined. Also not learned (correct): "Rahul Sharma" (person-like), "Pillai" (word of patient "Meena Pillai").
7. PASS with one defect. 1440x900, 1024x768, 390x844 with 19 stubbed names: no page horizontal scroll (scrollWidth == clientWidth), Remove 44px high x 84 wide, tab strip (margin 0 -24px) exactly dialog width, no clipping, .team-body scrolls (scrollHeight 1589 vs 752 at 1440; 1656 vs 700 at 390) and the last row ends inside the dialog. Defect D1 at 390px.
8. PASS. Tab order: Close, People, Clinic medicines, then row buttons. Focus ring on tabs 3px solid rgb(20, 86, 217). Enter and Space switch tabs (aria-selected updates). Escape closes the dialog; focus returns to the Team button (#teamOpenBtn). ArrowLeft/Right do nothing (known backlog, no roving tabindex).
9. PASS. team.css?v=2 and team.js?v=2 requested (200). All requests went to 127.0.0.1:8800 only. Console errors only: favicon 404, DELETE 404 (stale), DELETE 403 (doctor), DELETE 404 (cross-clinic).

## Defects

D1 (low-medium, layout). At 390px the Clinic medicines table box scrolls sideways inside the dialog (scrollWidth 517 vs clientWidth 304): "Last seen", "Added by" and the Remove button are off-screen until the user swipes the table, with no visible hint. Repro: admin A, viewport 390x844, Team > Clinic medicines. The People table has the same pattern (428 vs 304) so it matches the existing style, but for this tab the only action sits off-screen.

D2 (cosmetic). Stale-removal message is "no such medicine": lowercase, no period, says nothing about the list being out of date. Comes from the server's 404 body (h3), shown verbatim.

## Concerns

- No loading state: first open shows column headers only until the list arrives; on re-open with a previously empty list the old "Nothing learned yet." stays visible while the new request is in flight (seen with a 2.5 s delay), and old rows stay on screen when a reload fails (by design, but with the red box).
- Focus drops to BODY while a removal is pending (the clicked button is disabled), then lands on the tab button. Reasonable, but a screen-reader pass is still advisable.
- Dialog height jumps between the People and Clinic medicines tabs (content-sized dialog).
- A plain doctor opens Team (users list returns 200 for doctors) and sees Disable/Reset password buttons for other users. Pre-existing, outside h4; the server presumably rejects them, not tested.
- `create-clinic --first-user` makes a doctor-role user, so a new clinic has no admin until `create-user --role admin` is run; the Clinic medicines tab is therefore invisible to the clinic's first user. Setup note, not an h4 bug.
- check-row for an unknown name reports source "lexicon" with status unknown-medicine (both clinics); harmless but odd.
- Deviation from the brief: a first removal ran before I had tool-managed dialog handling working (my own page.once handler raced the MCP dialog handler). Zorbexin was removed, then re-learned with two fresh saves; the before-removal check-row (verified/clinic) and the 403 DELETE were captured before that.

## Cleanup

Server stopped, port 8800/8801 verified free with lsof, browser closed, .playwright-mcp removed from the worktree, temp DATA_DIR and scratch scripts removed (the pre-existing stray h2.py/ap.py in the session scratchpad are not mine and were left).
