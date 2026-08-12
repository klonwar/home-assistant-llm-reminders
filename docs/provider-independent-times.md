# Provider-independent natural-language reminder times (2026-08-12)

## Understanding summary

- Users create one-time reminders from phrases such as “через пять минут” or
  “завтра в 15:00”.
- The LLM extracts literal duration, date, weekday, and clock-time components;
  it does not choose a relative/calendar discriminator.
- A clock time without a stated date means the nearest future occurrence:
  today if it has not passed, otherwise tomorrow.
- Home Assistant is the sole authority for current time and timezone and
  resolves the normalized value into timezone-aware `due_at`.
- The provider must not call a date/time tool, calculate a timestamp, or send
  `due_at`.
- Native Home Assistant timers and recurring reminders remain outside this
  integration.

## Assumptions and non-goals

- Breaking compatibility for the old LLM payload is acceptable. Persisted
  records continue to store the resolved `due_at` value.
- The nearest future occurrence is sufficient; “next Monday” does not need a
  separate occurrence mode.
- Russian and English natural-language extraction is performed by the model;
  the server consumes canonical values.
- Arbitrary natural-language parsing inside the integration is not a goal.
  Unsupported or ambiguous expressions produce an error or clarification.

## Tool contract

`create_reminder` requires `message` and one field-first `when` object. The
same `when` shape is used by `update_reminder` when its time changes.

Relative interval:

```json
{
  "duration": [{"value": "5", "unit": "minute"}]
}
```

Calendar time without a date:

```json
{"local_time": "14:50"}
```

Calendar time with an explicit date:

```json
{"date": "tomorrow", "local_time": "14:50"}
```

Other calendar fields are `weekday`, `day_of_month`, `month`, `day_period`,
`hour`, and `meridiem`. `date` accepts `today`, `tomorrow`,
`day_after_tomorrow`, or `YYYY-MM-DD`. `target_time="HH:MM"` remains valid
with a whole-day or whole-week `duration`.

The model must not send `kind`, `date_ref`, `occurrence`, `month_ref`,
`year_ref`, `date_value`, or absolute timestamps. These are not part of the
new schema.

## Resolution and validation

The server normalizes the field-first payload before calling the deterministic
resolver:

1. `duration` without calendar fields becomes a relative interval.
2. Calendar fields without `duration` become a calendar value.
3. Both groups together are rejected as a conflict.
4. `date` selects today, tomorrow, the day after tomorrow, or an explicit ISO
   date; `weekday` selects its nearest future occurrence; `day_of_month` and
   optional `month` select the nearest future matching date.
5. With no date field, the server uses the nearest future local date.
6. Calendar values require exactly one time form: `local_time`, `day_period`,
   or `hour` with an unambiguous `meridiem`.

The resolver remains responsible for duration arithmetic, timezone conversion,
future-time checks, DST validation, and final `due_at` computation. Missing or
ambiguous time, invalid dates, conflicting fields, unsupported recurrence, and
nonexistent local times become concise tool errors.

## Prompt strategy

The runtime prompt tells the model to extract fields only, omit `date` when it
was not spoken, avoid `kind`/`date_ref`, and never call date/time tools. Tool
descriptions include short JSON examples because provider traces showed that a
discriminator-based contract was easy to misuse.

The single English base prompt remains language-neutral. Canonical field names
and enum values are stable across user languages; the model replies in the
user's language.

## Verification plan

Unit tests cover normalization for intervals, time-only values, semantic dates,
weekdays, day/month combinations, explicit dates, conflicts, and missing
fields. Schema tests accept minimal payloads and reject removed internal fields.
Manager tests cover create/update resolution, while existing resolver tests
continue to cover timezone, future selection, DST, ambiguity, and invalid
values. Assist traces should verify the serialized schema for each provider
used in production.
