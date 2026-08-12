# Thread-safety audit and remediation design (2026-08-05)

## Understanding summary

- Audit every integration module for Home Assistant thread-safety hazards,
  prompted by timer callbacks calling `hass.async_create_task` from an
  executor thread.
- Preserve one-time reminder creation, persistence, satellite selection,
  delivery, retry, cancellation, update, and restart behavior.
- Require both runtime-safe delivery/retry behavior and regression coverage;
  removing the warning alone is not sufficient.
- Include diagnostic logging in the audit; credentials and instance-specific
  secrets must remain out of logs.
- Keep native Home Assistant timer tools, persistent idempotency, recurring
  reminders, and unrelated refactors out of scope.

## Assumptions

- The deployment is a typical single-household Home Assistant instance with at
  most dozens of pending reminders and no multi-process coordination need.
- Home Assistant Core 2026.8.0 or newer remains the compatibility target.
- Existing retry timing and at-least-once delivery semantics remain unchanged.
- At the time of this historical audit, executable integration changes were
  expected to increment the manifest patch version manually. The later
  Release Please policy supersedes that process for published versions.

## Decision log

1. Audit the complete integration rather than only the reported line in
   `manager.py`.
2. Preserve existing reliability guarantees: restart persistence, retry for a
   busy or unavailable satellite, cancellation, and removal after success.
3. Include a diagnostic logging/redaction review. Reminder text and resolved
   `due_at` are included in operation logs by explicit user request; credentials
   and instance-specific secrets remain excluded.
4. Use Home Assistant's explicit `@callback` contract for timer callbacks.
5. Add focused manager tests for due and retry callback scheduling and retain
   the repository's full deterministic checks.
6. Do not add persistent idempotency, recurring reminders, or public API
   changes.

## Final design

`ReminderManager._async_deliver` remains the single asynchronous delivery path.
The callbacks supplied to `async_track_point_in_time` and `async_call_later`
are explicit, non-blocking `@callback` closures that capture the reminder ID
and only enqueue `_async_deliver` with `hass.async_create_task`. Home Assistant
therefore executes the callbacks on the event-loop thread instead of its
executor. The already-due path keeps its direct task creation because `_schedule`
is entered from async manager operations on the event loop.

Callbacks do not inspect state, access storage, remove schedules, or call
services. Those operations remain in `_async_deliver`, preserving `_in_flight`
duplicate suppression, retry scheduling, successful-delivery persistence,
unload cancellation, and harmless no-ops after cancellation. Storage format,
tool schemas, satellite resolution, and retry interval remain unchanged.

Focused tests capture due-time and retry callbacks, verify Home Assistant
callback metadata, invoke each callback, and assert that delivery is enqueued
without an unawaited coroutine. Tests also preserve delivery, retry,
cancellation, unload, and diagnostic logging expectations.

Validation consists of `python -m pytest tests` and
`python -m compileall -q custom_components\\llm_reminders`, followed by the
required independent implementation review.
