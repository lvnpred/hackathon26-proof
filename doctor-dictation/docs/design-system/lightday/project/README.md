Lightday is a family of ready-made apps and workflows that take jobs off your day. Each one works the first time you open it: nothing to configure, nothing to build, no stack of ten subscriptions. You pay small amounts for what you use. The first app is the clinic dictation app — a doctor speaks, Lightday writes the prescription, the PDF and the calendar follow-ups.

Every screen should feel like that promise: calm, obvious, already set up.

## What Lightday believes

| Belief | What it means on screen |
| --- | --- |
| **Ready on day one** | No setup wizard, no empty settings page. Decide the defaults; let people change them later from Profile. Show real work (today's list) on first open, never an onboarding carousel. |
| **Pay for the use, not the month** | Show cost per use in plain numbers ("₹[price] per prescription"). No trial countdowns, no upgrade nags, no locked features behind a plan wall. |
| **Speak, don't configure** | Voice is the first way in. A spoken command is the button label's twin: say "Diagnosis" or tap Diagnosis. Typing is always offered as "Type instead". |
| **One place, many jobs** | Every app uses the same bar, the same mic, the same sheet. Learn one, know them all. |
| **Paper is the output** | The thing you keep — a prescription, a letter, a summary — is a white sheet that prints exactly as it shows. |

## Voice and copy

- Write plain English in short sentences. One idea per sentence.
- Sentence case everywhere: "Save prescription", not "Save Prescription". Labels set in `label` are written in sentence case and shown in capitals by CSS.
- Buttons start with a verb and name the thing: "Save prescription", "New patient", "Type instead". Never "OK", "Submit" or "Click here".
- Tell people what to do next, not what went wrong in the system: "Name the patient first." beats "Patient ID required".
- Empty states say what will appear and how: "Not dictated yet".
- Status words are single and plain: Ready, Recording, Listening, Saved, Open, Synced.
- No exclamation marks. No emoji. No "Oops".
- Money in rupees with the symbol and no decimals when whole: "₹[price] per use", never "₹[price].00". Dates as "27 Oct 2026". Times as "10:20 am".
- Speak to the user as "you" and refer to Lightday by name or not at all — never "we".
- English and Tamil from day one; Telugu next. Keep strings short so they survive translation; never bake words into images.

Real copy from the clinic app, as the model:

> **Tap to dictate** — Name the patient first.
> **Rx (Medications)** — Tab Dolo 650, 1-0-1, after food, 5 days
> Not dictated yet · Save prescription · Say it (spell) · Type instead

## Colour

Two themes: **Day** (the default, first) and **Dusk** (dark). Use tokens, never raw hex.

- Ground is `paper`. Cards and panels are `surface`. Inputs and wells are `surface-sunk`.
- Text is `ink`; secondary text is `ink-muted`. Both read on `paper`, `surface`, `surface-sunk` and `sun-soft` in both themes.
- `sun` is the brand. Spend it on the mic button, the mark and the one thing being worked on right now (with `sun-soft` as the tint). In Day it is a light amber, so a `sun` fill always carries an `on-sun` glyph or label. When amber must be text, use `sun-text`.
- The primary button is `action` (an alias of `ink`) with `on-action` text — one per view. The sun is kept for the voice moment, so the mic and the primary button never compete.
- `sky` is links, information and the focus ring. `record` means recording or destructive. `leaf` means done or saved. Each status colour sits on its `-soft` tint and **always comes with a word** — never colour alone.
- The document is `sheet` with `sheet-ink` — white in both themes, because that is what prints.
- Hairlines are `line`. A border that tells you "this is a control" is `line-control` (3:1 or better).

## Type

- Interface text is **Figtree** (`sans`), with Noto Sans Tamil and Noto Sans Telugu behind it for Indian scripts. Load it from Google Fonts at weights 400, 500, 600, 700, 800.
- The only serif is **Source Serif 4** (`serif`), and only on the sheet: `paper-title` and `paper-letterhead`. It says "this is the document".
- Steps: `display` 40, `title` 26, `heading` 19, `body` / `body-strong` 15, `body-sm` 14, `label` 13 caps, `caption` 12. Nothing below 12px.
- Running numbers (timers, OP numbers in tables) use `font-variant-numeric: tabular-nums`.
- Weight does the hierarchy: 800 for headings and labels, 700 for names and buttons, 400 for reading. Avoid 300.

## Space, shape and depth

- Spacing is a 4px base: `space-1` to `space-12`. Page gutter `space-5`; card padding `space-4`–`space-6`; sheet padding `space-9` at the sides.
- Corners: `radius-sm` 8 rows and tags, `radius-md` 10 controls, `radius-lg` 12 cards and the sheet, `radius-xl` 16 app tiles, `radius-full` pills and the mic. Soft, never bubbly.
- Separate with borders first. Shadows only for the sheet (`shadow-sheet`) and the mic halos (`halo-sun`, `halo-record`).
- Every tappable thing is at least `touch-min` (44px); buttons and inputs are `control-h` (46px); list rows are at least `row-h` (56px). People use this one-handed between patients.
- Keyboard focus is always visible: `focus-ring` (a paper gap, then a solid sky ring).

## Layout

- Phone first, then tablet, then desktop. On a phone the screen is one column: app bar, mic card, what-to-say guide, sheet, actions.
- On wider screens use three columns that wrap: a list panel (240–290px), the dictation column (330–400px), and the sheet (the rest).
- The sheet is never squeezed below a readable width; its wide tables scroll inside a box.
- Actions for the sheet sit directly under it, primary first: "Save prescription", then ghost "Print", "Save PDF", "Share".

## Motion

- Motion confirms, it never decorates. The mic halo may pulse slowly (1.6s) while recording; the active guide step slides its tint (150ms ease-out).
- Respect `prefers-reduced-motion`: no pulse, instant tint.

## Iconography

- Line icons on a 24px grid, 2px stroke, round caps and joins, drawn inline as `<svg>` so they take `currentColor`. Lucide (ISC licence) matches this style and is the default source.
- Icons sit beside a word. An icon alone (previous / next day) gets an `aria-label`.
- No emoji, no filled or duotone icons, no illustrations of people.

## The mark

- The mark is a half sun resting just above a horizon line — the day starting. Files are under Logos: `lightday-mark.svg` (sun + ink horizon, for light grounds), `lightday-mark-reverse.svg` (sun + light horizon, for dark grounds), `lightday-app-icon.svg` (the app icon tile).
- The wordmark is the word "lightday" in lowercase, Figtree 800, letter-spacing -0.02em, in `ink`, set beside the mark with `space-2` between. There is no wordmark image: set it as live text.
- An app's name follows the wordmark after a middle dot: "lightday · Clinic". Name an app for the job, in one or two plain words.
- Keep clear space of half the mark's height on every side. Never recolour the sun, outline it or put it on a gradient.

## Components

Components are React 18 function components in `components/bundle.js`, exported on `window.Lightday`. Load `components/bundle.css` after the tokens; it also pulls Figtree and Source Serif 4 from Google Fonts.

| Component | Use it for |
| --- | --- |
| `AppBar` | The top bar of every Lightday app: mark, app name, a status pill and up to two actions. |
| `Button` | Actions. `primary` once per view; `ghost` for the rest; `quiet` for low-stakes text actions. |
| `MicButton` | Starting and stopping voice capture. One per screen. |
| `StatusPill` | One word of state with a dot: Ready, Recording, Saved, Open. |
| `Field` | A labelled text or search input. |
| `Card` | A bordered surface that groups one job on the screen. |
| `ListRow` | One item in a day's list — a patient, a task — with metadata and a tag. |
| `SpokenGuide` | The numbered "What to say" list that shows the spoken commands and highlights the one being dictated. |
| `PaperSheet` | The document: letterhead, fields, and sections that fill as you speak. |
| `AppTile` | One app in the Lightday suite launcher, with its job and per-use cost. |
