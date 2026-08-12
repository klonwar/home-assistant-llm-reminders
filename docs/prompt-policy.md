# Minimal runtime prompt policy

## Purpose

`base.txt` is an optional prompt fragment returned through Home Assistant's
`LLMTools.prompt`. It is inserted into an already substantial system prompt,
so it must contain policy and the smallest extraction rules needed to avoid
provider mistakes.

## Runtime policy

The agreed base prompt is:

```text
Use reminder tools for one-time persistent reminders.

Call create_reminder with message and structured when. Extract fields only:
use duration for intervals, local_time for clock times, and date or weekday
only when the user states a date. If no date is stated, omit date; the server
chooses the nearest future occurrence. For update_reminder, send the reminder
id and changed fields only.

Never calculate or send due_at, kind, date_ref, timestamps, timezone offsets,
or native timers. Never call date/time tools to resolve a reminder. Home
Assistant resolves when using current time and timezone.

Ask one concise clarification ending with `?` if time is missing, ambiguous,
or an update/cancellation has multiple matches. On tool error, report it and
never claim success. After success, briefly confirm without a question. Reply
in the user's language.
```

The exact wording may be edited for clarity, but it must preserve these
behaviors:

- use the reminder tools for persistent one-time reminders;
- pass a structured `when` object when creating or changing a reminder time;
- extract only duration and literal calendar fields; do not choose `kind` or
  `date_ref`;
- require both message and `when` for creation, but only changed fields for an
  update;
- omit a date when the user gave only a time so the server can choose the
  nearest future occurrence;
- never generate `due_at` or another absolute timestamp;
- leave date arithmetic and timezone handling to Home Assistant;
- clarify incomplete or ambiguous time expressions with a response ending in
  `?`;
- clarify multiple matches for update or cancellation;
- report tool errors without claiming success;
- confirm successful operations briefly without asking another question;
- answer in the language used by the user.

## What does not belong here

Do not repeat the complete field catalogue, provider-specific syntax, current
date/time, timezone data, device data, or reminder history. The tool schema and
description carry the full field definitions and examples. Native Home
Assistant timers are also outside this prompt's scope.

## Language strategy

Use one concise English base prompt. Canonical field names and enum values are
English and stable across user languages. The instruction to reply in the
user's language covers Russian and other supported languages. Add a language
file only after focused provider/model tests demonstrate a repeatable parsing
problem that cannot be solved by the schema or resolver error message.

## Decision log

1. **Keep policy separate from the full API contract.** The base prompt carries
   the extraction rules; schema and descriptions carry field definitions and
   examples.
2. **Do not provide current time to the model as a dependency.** Home
   Assistant's resolver is the authority for the current instant and timezone.
3. **Use one language-neutral base.** Duplicated language additions would
   increase the system prompt without improving the contract by default.
4. **Treat the prompt as guidance, not validation.** Semantic validation and
   timestamp calculation remain in the integration.
