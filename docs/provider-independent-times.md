# Provider-independent natural-language reminder times (2026-08-12)

## Understanding summary

- Users can create one-time persistent reminders with relative times (for
  example, “через пять минут”) and calendar times (for example, “завтра в
  15:00”).
- Speech-to-text may produce words rather than digits, so the tool contract
  uses text values and does not require numeric seconds/minutes fields.
- LLM providers may not expose the current date, current time, or user's
  timezone. The provider must not calculate an absolute timestamp.
- The LLM performs semantic extraction and normalization only: duration values,
  units, calendar references, and local clock values.
- Home Assistant is the sole authority for current time and timezone
  (`hass.config.time_zone`). It resolves `when` into timezone-aware `due_at`.
- Native Home Assistant timers are out of scope; supported one-time expressions
  use this integration's persistent reminder tool.
- Backward compatibility for the old LLM `due_at` input is not required.

## Assumptions and non-goals

- Reminders remain one-time events; recurring phrases such as “каждый день”
  are rejected.
- The user's timezone is the single configured Home Assistant timezone.
- Russian and English natural-language extraction is performed by the model;
  the server consumes only canonical values.
- Existing persisted records may continue to store resolved `due_at`; this is
  an internal storage format, not an old tool API to preserve.
- Arbitrary natural-language parsing inside the integration is not a goal.
  Unsupported or ambiguous expressions produce an error or clarification.
- A single concise English base prompt is preferred; language-specific additions
  are added only if focused tests show that they are necessary.

## Decision log

1. **Use a structured `when` object instead of a raw time string.** A raw
   parser in the integration would need to reproduce multilingual natural
   language. A structured object lets the LLM perform extraction while keeping
   date arithmetic deterministic.
2. **Keep normalized values as strings.** STT frequently produces number words,
   and the LLM can normalize “пять” to `"5"` without requiring a numeric JSON
   value. The resolver validates and converts these strings.
3. **Separate relative and calendar expressions with `when.kind`.** This makes
   valid fields and missing information explicit.
4. **Remove `due_at` from the LLM tool schema.** Accepting a model-generated
   timestamp would reintroduce provider clock errors. Resolved `due_at` remains
   an internal storage and scheduler value.
5. **Resolve nearest-future references on the server.** Day-of-month, weekday,
   month-without-year, and time-without-date depend on actual local time.
6. **Reject ambiguity and unsupported recurrence.** Silent guesses are worse
   than a concise clarification for missing time, unresolved meridiem, DST
   ambiguity, or recurring-language requests.

## Tool contract

`create_reminder` requires `message` and exactly one `when` object:

```json
{
  "message": "позвонить",
  "when": {
    "kind": "relative",
    "duration": [{"value": "5", "unit": "minute"}]
  }
}
```

```json
{
  "message": "позвонить",
  "when": {
    "kind": "calendar",
    "date_ref": "tomorrow",
    "local_time": "15:00"
  }
}
```

Relative values use canonical units `second`, `minute`, `hour`, `day`, or
`week`, and a positive string number. Multiple duration components are
allowed. `target_time="HH:MM"` supports “через неделю в 15:00”.

Calendar references are `today`, `tomorrow`, `day_after_tomorrow`, `weekday`,
`next_weekday`, `day_of_month`, `month_day`, `explicit`, and `nearest_future`.
Supporting fields are canonical weekday names, string month/day numbers,
`date_value="YYYY-MM-DD"`, `local_time`, `day_period` (`morning`, `day`,
`evening`), `hour`, and `meridiem` (`am`, `pm`, `unspecified`).

Examples:

```json
{"kind":"relative","duration":[{"value":"90","unit":"minute"}]}
```

```json
{"kind":"calendar","date_ref":"day_of_month","day_of_month":"15","month_ref":"nearest_future","local_time":"13:00"}
```

```json
{"kind":"calendar","date_ref":"explicit","date_value":"2026-08-15","local_time":"10:00"}
```

`update_reminder` accepts `reminder_id` and optionally `message` and/or `when`;
at least one update field is required. The old `due_at` argument is removed
from both tool schemas.

## Resolution and validation

The manager passes `when` to a pure resolver with `dt_util.now()` and the
configured Home Assistant timezone. Relative durations are added to the
current instant. Calendar references are resolved to a local date and then
combined with a local clock value. `day_period` defaults are `09:00`, `13:00`,
and `19:00` for morning, day, and evening. A day of month without a month uses
the nearest future occurrence; a month without a year uses the nearest future
occurrence in the current or next year. A time without a date uses today if
still future, otherwise tomorrow.

The resolver rejects non-positive durations, invalid dates/times, past explicit
references, missing time, unsupported recurrence, nonexistent local times, and
unresolved ambiguous local times. It returns a timezone-aware datetime, which
the manager stores as `due_at` and schedules for delivery.

## Prompt strategy

Use the API-first split described in
[prompt-api-contract.md](prompt-api-contract.md): schema and tool descriptions
carry the machine-readable contract, while `base.txt` contains only a short
policy. The base prompt tells the model to use reminder tools, pass `message`
and structured `when`, never send or calculate `due_at`, leave date arithmetic
to Home Assistant, clarify incomplete or ambiguous time, and reply in the
user's language. It does not repeat the field catalogue or JSON examples.

Keep one English base prompt by default. Canonical enum values remain English;
natural-language examples belong in tests and documentation rather than the
runtime system prompt. Language additions are justified only by a focused,
repeatable provider/model failure.

## Verification plan

Pure resolver tests cover composed durations, all calendar references,
nearest-future behavior, day periods, ambiguous hours, invalid/past values,
DST, and the configured timezone. Tool-schema tests prove `due_at` is rejected
and `when` is required. Manager tests cover tool input, resolution,
persistence, scheduling, and stale retry cleanup. Prompt tests verify that the
generated prompt contains the short policy, forbids timestamp calculation and
native timers, and does not duplicate the full `when` schema. Assist traces
verify the actual serialized tool contract for every provider adapter used in
production.
