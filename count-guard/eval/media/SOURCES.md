# Sample media sources

Every file under `eval/media/` has one row. Downloaded files come from Wikimedia Commons (the file's page is the source URL). Files marked "recorded for this project" were made by `eval/make_media.py` and carry no third-party rights. Forms and cards say "SAMPLE — synthetic" and use the made-up patient "M. Fernandes, 52 F (synthetic)". No faces, no real patients.

Role: `demo` = the file the demo and the model checks use; `stand-in` = a downloaded real photo kept for variety, too weak for a model to judge (reason given).

CC BY-SA files must be credited and shared alike when redistributed.

| Path | What it shows | Source URL | Licence | Author / credit | Changes | Role |
|---|---|---|---|---|---|---|
| wristband/wristband-synthetic.png | Patient wristband, synthetic patient | recorded for this project | recorded for this project | Count Guard project | drawn with Pillow | demo |
| wrong-photo/wrong-photo-tray.jpg | Steel tray with IV bag, chart, cuff (no wristband) | https://commons.wikimedia.org/wiki/File:Medical_tray_on_a_trolley.jpg | CC BY-SA 4.0 | Ibrahim Achiri | resized to 1600 px, re-encoded JPEG | stand-in: busy scene, sideways tray; a model cannot judge it cleanly |
| consent/consent-form.png | Consent form, synthetic | recorded for this project | recorded for this project | Count Guard project | drawn with Pillow | demo |
| monitor/monitor.jpg | Patient monitor screen (ECG, SpO2, BP) | https://commons.wikimedia.org/wiki/File:Vital_signs_monitor_display.jpg | Public domain (US Navy) | Petty Officer 1st Class James Stenberg, US Navy | resized to 1600 px, re-encoded JPEG | demo |
| medicine-bag/medicine-bag.jpg | Pharmacy paper bag | https://commons.wikimedia.org/wiki/File:Service_Apotheek_paper_bag,_Oude_Pekela_(2019).jpg | CC BY-SA 4.0 | Donald Trung Quoc Don | resized to 1600 px, re-encoded JPEG | stand-in: crumpled bag, no readable medicine list |
| discharge/discharge-card.png | Discharge card, synthetic | recorded for this project | recorded for this project | Count Guard project | drawn with Pillow | demo |
| saline-setup/iv-bag.jpg | Hanging 1000 ml IV fluid bag | https://commons.wikimedia.org/wiki/File:Intravenous_therapy_oxcytocin.jpg | CC BY-SA 4.0 | Eliran t | resized to 1600 px, re-encoded JPEG | stand-in: oxytocin label, not 0.9% sodium chloride |
| swab-tray/swab-tray.jpg | Instrument tray on green cloth with gauze swabs | https://commons.wikimedia.org/wiki/File:Surgical_Instruments_01.jpg | CC0 | Armin (آرمین) | resized to 1600 px, re-encoded JPEG | stand-in: instrument tray, swabs not countable |
| swab-count/swab-leaving-field.mp4 | 10 s clip: six swabs on a tray, one carried out of view at 5-7 s | recorded for this project | recorded for this project | Count Guard project | drawn with Pillow, encoded with ffmpeg | demo |
| drug-phrases/drug-lignocaine.wav | Spoken "lignocaine two percent, five ml, local infiltration" | recorded for this project | recorded for this project | macOS `say` | converted to 16 kHz mono WAV with ffmpeg | demo |
| drug-phrases/swabs-opening-twenty.wav | Spoken "opening twenty swabs" | recorded for this project | recorded for this project | macOS `say` | converted to 16 kHz mono WAV with ffmpeg | demo |
| home-medicines/strips-valaciclovir.jpg | Valaciclovir blister packs | https://commons.wikimedia.org/wiki/File:Valaciclovir_Blister_packs.jpg | CC0 | Hanabishi | re-encoded JPEG at quality 85 (already under 1600 px, so not resized) | stand-in: valaciclovir, not metoprolol or amlodipine |
| home-medicines/strips-blister.jpg | Three blister strips of tablets | https://commons.wikimedia.org/wiki/File:Blister_of_tablets.jpg | CC BY-SA 4.0 | Tarasna0922 | resized to 1600 px, re-encoded JPEG | stand-in: no readable drug name |
| wrong-photo/wrong-photo-bed-rail-synthetic.png | Bed rail and bare wrist area, no wristband (wrong subject) | recorded for this project | recorded for this project | Count Guard project | drawn with Pillow | demo |
| medicine-bag/medicine-bag-synthetic.png | Pharmacy bag with label: M. Fernandes, paracetamol 500 mg, amlodipine 5 mg, metoprolol 25 mg | recorded for this project | recorded for this project | Count Guard project | drawn with Pillow | demo |
| saline-setup/saline-setup-synthetic.png | 0.9% Sodium Chloride 1000 ml bag, giving set, drip chamber, roller clamp | recorded for this project | recorded for this project | Count Guard project | drawn with Pillow | demo |
| swab-tray/swab-tray-synthetic.png | Tray with exactly 20 separated swabs, labelled pack of 20 | recorded for this project | recorded for this project | Count Guard project | drawn with Pillow | demo |
| home-medicines/strips-metoprolol-amlodipine-synthetic.png | Two strips labelled Metoprolol 25 mg and Amlodipine 5 mg | recorded for this project | recorded for this project | Count Guard project | drawn with Pillow | demo |
