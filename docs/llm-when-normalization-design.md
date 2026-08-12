# LLM reminder time normalization design

## Understanding summary

- The LLM sometimes confuses relative intervals and calendar times, for
  example sending `relative` with `local_time`, then retrying after calling a
  date/time tool.
- A reminder such as “at 14:50” means 14:50 today when that time is still in
  the future, otherwise the same local time tomorrow.
- The LLM must not call `GetDateTime`, calculate a date, or generate an
  absolute timestamp to create a reminder.
- The LLM's job is limited to extracting obvious components from the user's
  phrase into a small structured payload.
- The server is responsible for deciding whether the payload is relative or
  calendar-based, selecting the nearest future occurrence, and applying the
  Home Assistant timezone.
- The same contract applies to `create_reminder` and to the `when` value of
  `update_reminder`.

## Assumptions and non-goals

- Breaking compatibility for existing LLM payloads is acceptable. Persisted
  reminder records remain compatible because they store resolved `due_at`.
- The nearest future occurrence is always sufficient; “next Monday” and
  “nearest Monday” do not need separate semantics.
- The existing duration representation remains an array of `{value, unit}`
  components, including `target_time` for whole-day/week intervals.
- Canonical weekday names are English; natural-language extraction remains the
  provider's responsibility.
- The expected scale is a normal Home Assistant household with at most dozens
  of pending reminders. No additional performance architecture is required.
- Reminder text and schedule data follow the existing privacy and logging
  rules; no new external service or clock dependency is introduced.
- Recurring reminders, native Home Assistant timers, and natural-language
  parsing inside the integration remain out of scope.

## Canonical LLM payload

The LLM-facing `when` object has no `kind`, `date_ref`, `occurrence`,
`month_ref`, or `year_ref` fields. The model sends only extracted components.

Relative interval:

```json
{"duration":[{"value":"5","unit":"minute"}]}
```

Calendar time with no stated date:

```json
{"local_time":"14:50"}
```

Calendar examples with stated dates:

```json
{"date":"tomorrow","local_time":"14:50"}
{"weekday":"monday","local_time":"14:50"}
{"day_of_month":"15","local_time":"13:00"}
{"date":"2026-08-15","local_time":"10:00"}
```

The supported calendar fields are `date`, `weekday`, `day_of_month`, `month`,
`local_time`, `day_period`, `hour`, and `meridiem`. `date` accepts
`today`, `tomorrow`, `day_after_tomorrow`, or an ISO date. `duration` and
`target_time` retain their current meaning.

## Server normalization

Add one explicit normalization step before the existing deterministic time
resolver. It derives an internal `kind` and calendar reference from the
payload; those values are not part of the public LLM contract.

1. A payload with `duration` and no calendar fields becomes `relative`.
2. A payload with calendar fields and no `duration` becomes `calendar`.
3. A payload containing both groups is rejected as a conflict.
4. Calendar reference is derived as follows:
   - `date=today`, `tomorrow`, or `day_after_tomorrow` selects that day;
   - an ISO `date` selects an explicit date;
   - `weekday` selects the nearest future weekday;
   - `day_of_month` selects the nearest future occurrence, optionally using
     `month` when both are supplied;
   - no date field selects `nearest_future`.
5. Exactly one time form (`local_time`, `day_period`, or `hour` with optional
   `meridiem` according to existing rules) is required for calendar values.
6. Missing time, incomplete month/day combinations, conflicting date fields,
   and invalid values produce concise `HomeAssistantError` messages suitable
   for a single clarification or corrected tool call.

The resolver remains responsible for timezone-aware arithmetic, future-time
checks, DST validation, and final `due_at` computation. The manager and
scheduling behavior do not change.

## Prompt and schema guidance

The runtime policy tells the model to extract fields only:

- use `duration` for “через N …” intervals;
- use `local_time` for a clock time;
- add `date`/`weekday`/`day_of_month` only when the user stated one;
- omit the date when it was not stated because the server chooses the nearest
  future occurrence;
- never send `kind`, `date_ref`, `due_at`, timestamps, or timezone offsets;
- do not call date/time tools to resolve a reminder.

Tool descriptions include the short JSON examples above. The schema is strict
and rejects the removed fields, so the model receives immediate feedback if it
tries to use the old contract.

## Verification plan

- Add unit tests for the normalizer covering relative, time-only, semantic
  dates, weekdays, day/month combinations, explicit ISO dates, conflicts, and
  missing fields.
- Update schema tests to accept the minimal payloads and reject `kind` and
  `date_ref`.
- Update manager tests so create and update resolve payloads without internal
  enum fields.
- Update prompt-loader tests for the extraction rules, nearest-future default,
  and prohibition on date/time tool calls.
- Preserve the existing resolver tests for timezone, future selection, DST,
  ambiguity, and invalid values.
- Run `python -m pytest tests` and
  `python -m compileall -q custom_components\\llm_reminders` after
  implementation.

## Decision log

1. **Move `relative`/`calendar` classification to the server.** The observed
   provider errors show that an enum discriminator is an unnecessary failure
   point for the model.
2. **Remove `date_ref` from the LLM contract.** Date references are derived
   from literal extracted fields; a time without a date defaults to the
   nearest future occurrence.
3. **Use a field-first calendar shape.** `date`, `weekday`, `day_of_month`,
   and `month` mirror what the user actually said and avoid semantic wrapper
   fields.
4. **Drop legacy input compatibility.** The user explicitly accepts a clean,
   breaking contract, so compatibility fields are not exposed or accepted.
5. **Keep the existing deterministic resolver.** It already owns timezone,
   DST, future-time, and `due_at` correctness; only an input normalizer is
   added before it.
6. **Add focused examples to the runtime tool descriptions.** The provider
   failure justifies examples even though the previous prompt strategy aimed
   to minimize runtime text.
7. **Keep the change one-time and provider-independent.** No `GetDateTime`,
   absolute timestamp, native timer, or recurring-reminder dependency is
   introduced.

## Open risks

- Providers may serialize field descriptions differently; Assist traces should
  verify the actual schema after implementation.
- A provider may still emit incompatible field combinations; normalization and
  concise errors remain the defensive boundary.
- Removing the old contract requires updating all local agents or automations
  that call these tools directly.
