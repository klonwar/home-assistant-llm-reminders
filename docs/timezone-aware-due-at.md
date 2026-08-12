# Timezone-aware reminder time handling (historical design, 2026-08-05)

This document records the earlier absolute-timestamp design. The current tool
contract is documented in [provider-independent-times.md](provider-independent-times.md).

## Understanding summary

- The LLM could send a valid-looking ISO timestamp without a timezone offset,
  while the integration deliberately rejected naive datetimes.
- The desired outcome was a successful first tool call for valid reminder
  times, without changing the meaning of an explicitly timezone-aware value.
- The prompt and server-side validation both enforced the timestamp contract
  for `create_reminder` and `update_reminder`.
- A value without an offset was interpreted as local time in Home Assistant's
  configured timezone, including daylight-saving rules where applicable.
- A value with an explicit offset kept that offset and represented instant; it
  was not reinterpreted as a Home Assistant wall-clock time.
- Native timers, public tool names, persistence format, satellite routing, and
  delivery retry behavior remained outside that change.

## Assumptions

- The Home Assistant compatibility target remained Core 2026.8.0 or newer.
- Invalid or impossible date strings remained validation errors.
- Dates in the past continued to be rejected.
- Existing stored records were expected to contain offsets and remain parsed in
  strict mode.
- A typical installation had at most dozens of pending reminders; timezone
  normalization was negligible compared with an LLM request.

## Decision log

1. Use a two-layer contract: prompt requirements plus defensive server-side
   normalization.
2. Apply identical handling to creation and update operations.
3. Require the prompt to request absolute ISO-8601/RFC3339 values with an
   offset, without hardcoding a numeric offset or including examples.
4. For a naive value, attach `hass.config.time_zone`; for an aware value,
   preserve the explicitly supplied offset and instant.
5. Reject nonexistent or ambiguous local times caused by timezone transitions.
6. Keep strict parsing for loaded records and internal scheduling paths.

## Superseded final design

The old base prompt required an absolute ISO-8601/RFC3339 `due_at` with a
timezone offset. The shared datetime parser localized naive values with the
configured Home Assistant timezone and preserved explicit offsets. Invalid,
nonexistent, ambiguous, and past values raised `HomeAssistantError`.

The current design avoids provider clock errors by removing `due_at` from the
LLM tool API. Home Assistant now resolves structured `when` values directly.
