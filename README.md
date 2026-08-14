# LLM Reminders for Home Assistant

Create and manage one-time spoken reminders through your Home Assistant
conversation agent and Assist Satellite.

## What you can say

English and Russian reminder instructions are included, and the assistant can
respond in the language you use.

- “Remind me tonight to buy bread.” / «Напомни мне сегодня вечером купить
  хлеб».
- “Move my bread reminder to tomorrow morning.” / «Перенеси напоминание купить
  хлеб на завтра утром».
- “Cancel the bread reminder.” / «Отмени напоминание о хлебе».
- “What reminders do I have?” / «Какие у меня есть напоминания».

The assistant asks a short follow-up question when the reminder text or time is
missing or ambiguous. After the reminder is created, Home Assistant announces
it through the Assist Satellite associated with the request, or through the
configured default satellite.

## Prerequisites

- Home Assistant Core **2026.8.0 or newer**.
- An Assist conversation agent connected to an LLM provider (for example,
  OpenRouter).
- A speech-to-text (STT) provider for voice input.
- A text-to-speech (TTS) provider and Assist Satellite for spoken announcements.

This integration provides reminder tools; it does not configure these services.

## How it works

1. You speak to an Assist pipeline that uses an external conversation agent.
2. Reminder phrases are intercepted before local intents and forwarded to the
   selected pipeline agent with the original Assist device context.
3. The agent calls a reminder tool to create, list, update, or cancel a
   reminder.
4. The integration validates the request, stores the reminder, schedules it,
   and delivers the announcement.

The four available LLM tools are `create_reminder`, `list_reminders`,
`update_reminder`, and `cancel_reminder`. They are callable tools, not ordinary
Home Assistant entities. Native Home Assistant timers remain available and are
managed separately.

## Installation

### HACS

This repository is structured as a HACS integration repository. In HACS, add
the GitHub repository as a custom repository with type **Integration**, download
it, and restart Home Assistant. See the [HACS custom repository
documentation](https://hacs.xyz/docs/faq/custom_repositories/) for details.

### Manual development install

Copy the integration directory into the Home Assistant configuration directory:

```text
config/
└── custom_components/
    └── llm_reminders/
```

Restart Home Assistant after copying the files.

## Requirements and compatibility

Use Home Assistant Core **2026.8.0 or newer**. This is the first version with
the LLM platform loader and `async_get_tools()` integration point used by the
reminder tools.

On Home Assistant Core 2026.7.x, the integration can load, but its four
reminder tools are not added to Assist because the newer platform loader is not
available. Native Home Assistant timer tools are unaffected.

After upgrading Home Assistant, restart the container. You do not need to
change `configuration.yaml`, local processing, or the native timer tools. See
the [Home Assistant LLM API documentation](https://developers.home-assistant.io/docs/core/llm/)
for platform details.

## Configuration

Open **Settings → Devices & services → Add integration**, select **LLM
Reminders**, and configure an optional default Assist Satellite.

For voice-routed reminder phrases, the request must include a Home Assistant
device ID. The integration resolves the Assist Satellite belonging to that
device and fails safely if the context is missing or no satellite is found; it
does not redirect a voice reminder to `default_satellite`. Configure one Assist
Satellite per Home Assistant device for deterministic delivery. The configured
default satellite remains available to existing non-voice tool requests that
do not carry device context.

Configure your conversation agent separately (for example, the OpenRouter
conversation integration) and enable Assist/home-control mode so it can receive
Home Assistant LLM tools. After setup, verify tool calls in the Assist Debug
dialog.

Reminder routing is guaranteed for external LLM conversation agents. A
pipeline that uses only the built-in Home Assistant conversation agent keeps
Home Assistant's native intent behavior because Assist Core does not run
external sentence triggers for that pipeline. The integration does not replace
your conversation agent, speech-to-text, or text-to-speech provider, and it
does not modify native Home Assistant/LVA timer intents.

## Language support

The integration adds one concise, language-neutral policy prompt from
`custom_components/llm_reminders/prompts/base.txt`. It asks the model to
respond in the user's language and to normalize natural-language time into the
structured `when` field. The model does not need access to the current date,
time, or timezone; Home Assistant resolves those values after the tool call.

## Recommended system-prompt rules

Keep your existing system prompt and add equivalent instructions for reminders:

```text
Use reminder tools for one-time spoken reminders.
Always send `message` and a structured `when` object; never send or calculate
`due_at`. Use `duration` for phrases such as “через пять минут”, or
`local_time` plus an optional `date` for phrases such as “завтра в 15:00”. If
the user gives only a time, omit `date`; the server selects the nearest future
occurrence. Do not send `kind` or `date_ref`, call date/time tools, or claim
success if a tool reports an error. If several reminders match a cancellation
or update request, ask the user to clarify.
```

## Time interpretation

Relative and calendar phrases are resolved by Home Assistant using its current
time and configured timezone. “Через пять минут” becomes a `duration` object;
“завтра в 15:00” becomes `date` plus `local_time`; “15-го числа в 13:00”
becomes `day_of_month` plus `local_time`. A time without a date uses the
nearest future local date. If the user gives no time or the hour remains
ambiguous, ask for clarification. Recurring phrases such as “каждый день” are
not supported by the one-time reminder contract.

## Persistence and delivery

Reminders are persisted in Home Assistant's private `.storage` area. Pending
reminders are scheduled again after Home Assistant restarts. If a target
satellite is unavailable or busy, delivery is retried rather than redirected
to another device.

## Current limitations

- The first version does not persist idempotency keys. A rare provider timeout
  followed by a repeated tool call may create a duplicate.
- Reminder records are one-time events; native Home Assistant/LVA timers remain
  separate.
- The integration does not provide a calendar UI.

## Development

Run these checks before publishing changes:

```bash
python -m compileall -q custom_components/llm_reminders
python -m pytest tests
```

### Release automation

Commits merged into `main` are processed by Release Please. Use Conventional
Commit prefixes such as `fix:` for patch releases, `feat:` for minor releases,
and a `!` suffix for breaking changes. Release Please opens or updates a
Release PR, updates `manifest.json` and `CHANGELOG.md`, and publishes the
GitHub Release after that PR is merged.

#### Beta releases

Beta releases use a separate `beta` branch and the
`release-please-config.beta.json` prerelease configuration. Create the branch
from `main`, merge the changes to test into it, and let the beta workflow create
or update the release PR. Merging that PR publishes a GitHub prerelease such as
`0.5.0-beta.0` and updates the integration manifest.

The beta workflow does not change the stable `main` release flow. When the
implementation is ready for a stable release, merge the implementation into
`main` without carrying over the beta-only version bump; the regular Release
Please workflow will then create the stable release PR. HACS users must enable
pre-release updates for this repository to receive beta versions.

Do not edit the integration version manually in ordinary feature or fix PRs.
Review the HACS and Hassfest checks before merging a Release PR.
