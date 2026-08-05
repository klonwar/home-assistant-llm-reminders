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
- Include diagnostic logging in the audit; credentials and instance-specific
  secrets must remain out of logs.
- Keep native Home Assistant timer tools, persistent idempotency, recurring
  reminders, and unrelated refactors out of scope.

### Assumptions

- The deployment is a typical single-household Home Assistant instance with at
  most dozens of pending reminders and no multi-process coordination need.
- Home Assistant Core 2026.8.0 or newer remains the compatibility target.
- Existing retry timing and at-least-once delivery semantics remain unchanged.
- At the time of this historical audit, executable integration changes were
  expected to increment the manifest patch version manually. The later
  Release Please policy supersedes that process for published versions.

### Decision log

1. Audit the complete integration rather than only the reported line in
   `manager.py`.
2. Preserve existing reliability guarantees: restart persistence, retry for a
   busy or unavailable satellite, cancellation, and removal after success.
3. Include a diagnostic logging/redaction review. Reminder text and `due_at`
   are included in operation logs by explicit user request; credentials and
   instance-specific secrets remain excluded.
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
cancellation, unload, and diagnostic logging expectations. The historical
change updated the manifest patch version and its package-layout assertion;
current published versions are managed by Release Please. Validation consists
of `python -m pytest tests` and
`python -m compileall -q custom_components\\llm_reminders`, followed by the
required independent implementation review.

## Timezone-aware LLM due_at handling (2026-08-05)

### Understanding summary

- The LLM currently retries because it can send a valid-looking ISO timestamp
  without a timezone offset, while the integration deliberately rejects naive
  datetimes.
- The desired outcome is a successful first tool call for valid reminder times,
  without changing the meaning of an explicitly timezone-aware value.
- The prompt and the server-side validation must both enforce the timestamp
  contract for `create_reminder` and `update_reminder`.
- A value without an offset is interpreted as local time in Home Assistant's
  configured timezone, including daylight-saving rules where applicable.
- A value with an explicit offset keeps that offset and its represented instant;
  it is not reinterpreted as a Home Assistant wall-clock time.
- Native timers, public tool names, persistence format, satellite routing, and
  delivery retry behavior remain outside this change.

### Assumptions

- The Home Assistant compatibility target remains Core 2026.8.0 or newer.
- Invalid or impossible date strings remain validation errors.
- Dates in the past continue to be rejected.
- Existing stored records are expected to contain offsets and remain parsed in
  strict mode.
- A typical installation has at most dozens of pending reminders; timezone
  normalization must be negligible compared with an LLM request.
- Operation logs include reminder text and `due_at` by explicit user request;
  credentials and instance-specific secrets are not logged.

### Decision log

1. Use a two-layer contract: prompt requirements plus defensive server-side
   normalization. This avoids an unnecessary retry when the model omits an
   offset while still guiding future calls to the correct format.
2. Apply identical handling to creation and update operations because both
   accept `due_at` and both schedule a future reminder.
3. Require the prompt to request absolute ISO-8601/RFC3339 values with an
   offset, but do not hardcode a numeric offset or include examples.
4. For a naive value, attach `hass.config.time_zone`; for an aware value,
   preserve the explicitly supplied offset and instant.
5. Reject nonexistent or ambiguous local times caused by timezone transitions
   instead of silently shifting the reminder; ask the user for clarification.
6. Keep strict parsing for loaded records and all internal scheduling paths.

### Final design

The base prompt will state that `due_at` is mandatory, absolute, ISO-8601/
RFC3339, and must include a timezone offset. Relative or natural-language
times are resolved before the tool call using Home Assistant's timezone. The
same requirement is stated for both create and update; the prompt contains no
fixed offset or illustrative payload. Missing or ambiguous user input still
requires a concise clarification question.

The shared datetime parser will support an explicit local-timezone context for
the two LLM write paths. It will keep an existing offset unchanged, normalize a
naive value with the configured Home Assistant timezone, and return a
timezone-aware datetime for future-time validation, storage, and scheduling.
Already persisted reminders continue through strict parsing. Invalid,
nonexistent, or ambiguous values raise a concise `HomeAssistantError` rather
than being silently shifted.

Regression coverage will verify aware-offset preservation, naive localization,
`Z` handling, create/update parity, invalid and past dates, strict loading, and
the prompt's offset requirement. Deterministic validation remains
`python -m pytest tests` and
`python -m compileall -q custom_components\\llm_reminders`.

## HACS validation and Release Please automation (2026-08-05)

### Understanding summary

- Prepare this Home Assistant integration repository for HACS publishing
  recommendations.
- Add `.github/workflows/validate.yml` with the official HACS Action for the
  `integration` category and the official Hassfest action.
- Run validation on pushes, pull requests, a daily schedule, and manual
  dispatch.
- Add a separate Release Please workflow triggered by pushes to `main`.
- Use the standard Release PR lifecycle: Release Please opens or updates a PR;
  merging it creates a GitHub Release, a `vX.Y.Z` tag, and `CHANGELOG.md`.
- Keep `custom_components/llm_reminders/manifest.json` synchronized from the
  current `0.1.8` version through the Release PR.
- Store the fine-grained PAT in the repository Actions secret
  `RELEASE_PLEASE_TOKEN`; contributors use Conventional Commits.

### Assumptions and non-goals

- `main` is the default branch and Release PRs are merged manually.
- HACS default-repository submission is a later process, not part of this
  change.
- Integration runtime behavior, dependencies, and public APIs remain
  unchanged.
- HACS and Hassfest action references follow their official examples:
  `hacs/action@main` and `home-assistant/actions/hassfest@master`.
- The PAT is restricted to this repository with `contents`, `issues`, and
  `pull requests` write permissions and an explicit expiration.
- Risks accepted and documented: PAT rotation is required; the first Release
  PR may include accumulated Conventional Commits; official mutable action
  refs require ongoing upstream trust.

### Decision log

1. Use two independent workflows rather than combining validation and release
   permissions in one workflow.
2. Run both HACS validation and Hassfest because HACS recommends both for
   integration repositories.
3. Use Release Please's manifest-driven configuration for the single root
   package (`"."`) and omit a component prefix from tags.
4. Track the initial version in `.release-please-manifest.json` as `0.1.8`.
5. Configure a JSON `extra-files` updater for
   `custom_components/llm_reminders/manifest.json` at `$.version`.
6. Let Release Please own published version bumps; ordinary feature/fix PRs
   must not manually change the manifest version.
7. Replace the hard-coded version assertion in
   `tests/test_package_structure.py` with a SemVer-format assertion.
8. Use a fine-grained `RELEASE_PLEASE_TOKEN` so Release PRs trigger HACS and
   Hassfest workflows; serialize Release Please runs with a concurrency group.

### Final design

`validate.yml` will be read-only. It will trigger on `push`, `pull_request`,
the official midnight schedule, and `workflow_dispatch`. Its HACS job will use
`hacs/action@main` with `category: integration`; its Hassfest job will check
out the repository and use `home-assistant/actions/hassfest@master`. Workflow
permissions default to `{}`; only the Hassfest job receives `contents: read`.

`release-please.yml` will trigger only on pushes to `main`, use
`googleapis/release-please-action@v4`, pass `secrets.RELEASE_PLEASE_TOKEN`, and
declare `contents: write`, `issues: write`, and `pull-requests: write`. A
single concurrency group prevents overlapping Release PR updates. The
workflow will not execute integration code or publish external packages.

`release-please-config.json` will define one root package with the simple
release strategy, root `CHANGELOG.md`, and the JSON `extra-files` updater.
`.release-please-manifest.json` will contain `{ ".": "0.1.8" }`. The action
will run in manifest mode, create ordinary `v<version>` tags, and generate the
GitHub Release when the Release PR is merged.

`AGENTS.md` will state that Release Please is the source of published version
bumps. The package-layout test will validate required manifest keys and a
SemVer version without assuming a particular release number. README will add
short maintainer guidance for Conventional Commits, Release PR review, and
PAT rotation.

Verification consists of `python -m pytest tests`,
`python -m compileall -q custom_components\\llm_reminders`, JSON parsing for
the Release Please files, and a GitHub acceptance check covering both
validation jobs, Release PR updates, and the resulting HACS-visible release.
