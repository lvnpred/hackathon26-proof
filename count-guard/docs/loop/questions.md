# Open questions

The loop stops on a question that changes the product. UC6 is already blocked and is not asked again.

## Closed

Covasant IP check: not applicable. Closed by you. It is not a blocker for this repo.

## Q1 — hackathon bot address

Asked: 28 Oct 2026. Blocks: the second notification channel only. Does not block UC1.

You named "hackathon bot" as the channel. No bot, webhook, token, or chat id was found in this workspace or under `~/.grok`.

Reply with one of these:

- A webhook URL the loop may POST a one-line status to.
- The bot's chat or channel id and how to send (Discord, Slack, Telegram).
- "Chat only", and this file will be closed.

Until then, questions are posted in the Grok chat.

## Q2 — what does the filed camera count carry once the demo has unannounced gauze?

**Closed 28 Oct 2026: (a).** File lap sponges only. Asked by the overnight loop; it blocked backlog B2.

B2 adds five unannounced gauze swabs to the `demo` camera scenario so the demo can show R4. Then UC3 fails. `backend/app/morning/camera_file.py:7-9` sums every item type, so the filed line reads "opened 10, returned 14, unaccounted 1".

Reply with one of these:

- (a) File lap sponges only. Change `camera_file.py`. Recommended: the numbers add up again, and UC3 stays as it is.
- (b) File every type, and change UC3 to expect returned 14.
- (c) Keep `demo` as it is, and add a separate R4 scenario to the demo button.

## Q3 — should a typed resolution reason be screened for advice words?

**Closed 28 Oct 2026: (a).** Leave a typed reason as written. The sheet names who wrote it.

The advice check (`backend/app/agent/verifier.py:7`) runs only on model sentences. A person's reason, such as "Took to X-ray" or "Surgeon says we should recount", goes onto the screen and the count sheet as typed.

Reply with one of these:

- (a) Leave it. A person wrote it, and the sheet names who. Recommended: the rule is "the system never advises", not "people may not write".
- (b) Reject such a reason with a 422 when it is recorded.
- (c) Keep the reason, and print it in quotes as "noted by X".
