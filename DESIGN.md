# Design notes

## Goal

Provide a generic Home Assistant LLM API for natural-language, one-time voice
reminders. The package must work with OpenRouter, local or other compatible
conversation agents and must route delivery to the Assist Satellite that
started the request when Home Assistant exposes its device context.

## Decisions

1. Use Home Assistant's official LLM API extension point instead of creating a
   second conversation agent or calling OpenRouter directly.
2. Expose four logical tools: create, list, cancel, and update.
3. Accept normalized absolute ISO-8601 timestamps from the LLM. Natural-language
   time interpretation remains in the conversation agent.
4. Keep the reminder storage and scheduler inside the integration. Do not rely
   on a user's YAML package, entity names, calendar helper, or speaker.
5. Resolve the target satellite from `LLMContext.device_id` and fall back to a
   user-configured default satellite.
6. Persist pending reminders with Home Assistant's private storage helper.
7. Retry delivery when the target satellite is unavailable or busy; never
   redirect the message to another satellite.
8. Do not implement persistent idempotency in the first iteration. This is a
   documented limitation and can be added without changing the public tool
   names.
9. Keep native Home Assistant/LVA timer intents outside this reminder API.
10. Treat the existing household-specific `voice_reminders.yaml` as a beta
    prototype, not a dependency of this package.

## Out of scope

- OpenRouter credentials or provider configuration;
- speech-to-text and text-to-speech;
- a calendar UI;
- recurring reminders;
- a universal conversation inactivity timeout;
- household-specific entity IDs, aliases, IP addresses, or exported state.

## Thread-safety audit and remediation design (2026-08-05)

### Understanding summary

- Audit every integration module for Home Assistant thread-safety hazards,
  prompted by timer callbacks calling `hass.async_create_task` from an
  executor thread.
- Preserve one-time reminder creation, persistence, satellite selection,
  delivery, retry, cancellation, update, and restart behavior.
- Require both runtime-safe delivery/retry behavior and regression coverage;
  removing the warning alone is not sufficient.
- Include diagnostic logging in the audit and keep reminder text, credentials,
  and other sensitive content out of logs.
- Keep native Home Assistant timer tools, persistent idempotency, recurring
  reminders, and unrelated refactors out of scope.

### Assumptions

- The deployment is a typical single-household Home Assistant instance with at
  most dozens of pending reminders and no multi-process coordination need.
- Home Assistant Core 2026.8.0 or newer remains the compatibility target.
- Existing retry timing and at-least-once delivery semantics remain unchanged.
- Any executable integration change increments the manifest patch version.

### Decision log

1. Audit the complete integration rather than only the reported line in
   `manager.py`.
2. Preserve existing reliability guarantees: restart persistence, retry for a
   busy or unavailable satellite, cancellation, and removal after success.
3. Include a diagnostic logging/redaction review without adding reminder text
   to logs.
4. Use Home Assistant's explicit `@callback` contract for timer callbacks.
5. Add focused manager tests for due and retry callback scheduling and retain
   the repository's full deterministic checks.
6. Do not add persistent idempotency, recurring reminders, or public API
   changes.

### Final design

`ReminderManager._async_deliver` remains the single asynchronous delivery
path. The callbacks supplied to `async_track_point_in_time` and
`async_call_later` will be explicit, non-blocking `@callback` closures that
capture the reminder ID and only enqueue `_async_deliver` with
`hass.async_create_task`. Home Assistant will therefore execute the callbacks
on the event-loop thread instead of its executor. The already-due path keeps
its direct task creation because `_schedule` is entered from async manager
operations on the event loop.

Callbacks will not inspect state, access storage, remove schedules, or call
services. Those operations remain in `_async_deliver`, preserving `_in_flight`
duplicate suppression, retry scheduling, successful-delivery persistence,
unload cancellation, and harmless no-ops after cancellation. Storage format,
tool schemas, satellite resolution, and retry interval remain unchanged.

Focused tests will capture due-time and retry callbacks, verify Home Assistant
callback metadata, invoke each callback, and assert that delivery is enqueued
without an unawaited coroutine. Tests will also preserve delivery, retry,
cancellation, unload, and diagnostic logging expectations. The manifest patch
version and its package-layout assertion will be updated. Validation consists
of `python -m pytest tests` and
`python -m compileall -q custom_components\\llm_reminders`, followed by the
required independent implementation review.
