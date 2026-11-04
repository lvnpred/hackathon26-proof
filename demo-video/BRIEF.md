---
workflow: product-launch-video
flow: automation
storyboard: no
message: "One synthetic patient, two apps: the system formats, the doctor decides."
destination: YouTube
aspect: 16:9
language: en
audience: hackathon judges
length: 180
angle: follow-the-patient screen demo
voice: local Kokoro TTS (af_heart)
vo_mode: verbatim beats
---

# BRIEF: Count Guard + Doctor Dictation 3-minute demo video

Show-it-as-is app demo: 20 beats from `count-guard/frontend/scripts/demo/beats.mjs`, same order,
same seconds (180 total), each beat a full-screen app screenshot with slow pan,-scripted
`say` narration as voiceover, and the line burned as caption.

## Intent

Follow one synthetic patient (M. Fernandes, 52 F) from Doctor Dictation clinic visit through
Count Guard ward, theatre, discharge, close. Screens carry the story; narration describes.

## Assets

- `assets/<beat-id>.png` × 20 (beat ids: title, dd-open, dd-dictate, dd-admit, ward-arrival,
  ward-photo-ok, ward-photo-wrong, ward-retake, theatre-send, theatre-drug, theatre-card,
  theatre-camera, theatre-missing, theatre-hard-stop, theatre-reconcile, discharge-draft,
  discharge-sign, discharge-pdf, discharge-home, close). 1200 px wide PNG preferred.
- Until the user supplies them: `count-guard/demo-shots/*.png` stand-ins, same framing.
- `assets/vo/<beat-id>.wav` × 20, Kokoro af_heart, one file per beat, fitted to its seconds.

## Customizations

- MOVIE CUT (approved STORYBOARD.md): Problem 24s → Heroes 28s → Save the day 104s → Close 24s.
  Typographic acts + tight app crops with highlight pulses; plain roles in narration, model names only
  in Act II mapping + Act IV recap. Film beats live in `film-beats.json`, separate from demo-check.
- 1920×1080; captions burned; LEFT current, cut-the-curve seams, one iris reveal into the missing swab.
- Music: scored 180s arc (tense Acts I–II → steady Act III → warm resolve Act IV, crossfaded),
  plus a 3s riser swelling into the F14 hard stop; bed carved under the 19-voice group.
- Title: LIGHTDAY — "The count can't be lost." (already the shared identity in both apps:
  Doctor Dictation's "lightday · Clinic" header, Count Guard's "Lightday mark"). Ending names
  the fixes (counts add up / swabs can't go missing / records write themselves), then title+moral.
- No live capture (servers unrunnable in this session); crops derive from demo-shots until supplied.

## Notes (stated vs inferred)

- Stated: 3 minutes; user provides images to a project folder; Playwright/images + TTS; local Kokoro;
  YouTube 16:9; one finished video, no live board.
- Inferred: verbatim beat `say` lines (they are the offline-check narration; the 5 live-film doc variants
  don't apply to prepared screenshots); af_heart default voice; demo-shots as stand-ins until supplied;
  automation flow (direct creation request with asset handoff).
- Muse has no text-to-speech API (Voice Transcribe is STT-only) — disclosed, Kokoro chosen instead.
