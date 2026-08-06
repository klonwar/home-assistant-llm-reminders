# LLM Reminders for Home Assistant

Create and manage one-time spoken reminders through your Home Assistant
conversation agent and Assist Satellite.

## What you can say

- “Remind me tonight to buy bread.”
- “Move my bread reminder to tomorrow morning.”
- “Cancel the bread reminder.”

The assistant asks a short follow-up question when the reminder text or time is
missing or ambiguous. After the reminder is created, Home Assistant announces
it through the Assist Satellite associated with the request, or through the
configured default satellite.

## How it works

1. You speak to your Home Assistant conversation agent.
2. The agent calls a reminder tool to create, list, update, or cancel a
   reminder.
3. The integration validates the request, stores the reminder, schedules it,
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

The default satellite is used when the LLM request has no device context. When
the request includes a Home Assistant device ID, the integration first looks
for an `assist_satellite` entity belonging to that device. This supports one or
many satellites without hardcoding their names.

Configure your conversation agent separately (for example, the OpenRouter
conversation integration) and enable Assist/home-control mode so it can receive
Home Assistant LLM tools. After setup, verify tool calls in the Assist Debug
dialog.

The integration does not replace your conversation agent, speech-to-text, or
text-to-speech provider, and it does not modify native Home Assistant/LVA timer
intents.

## Language support

The integration adds language-aware instructions to the LLM request. The base
instructions are stored in `custom_components/llm_reminders/prompts/base.txt`,
with optional additions in `prompts/languages/`:

- `en.txt` — English guidance;
- `ru.txt` — Russian guidance and Russian time expressions.

The matching file is selected from the Assist request language. Regional tags
such as `en-US` and `ru-RU` use their base language file. Languages without a
dedicated file use the neutral base instructions, and the model is asked to
respond in the user's language. Adding another language only requires a new
`<language>.txt` file; no code change is required.

## Recommended system-prompt rules

Keep your existing system prompt and add equivalent instructions for reminders:

```text
Use reminder tools for one-time spoken reminders.
Ask concise follow-up questions when reminder text or time is missing or
ambiguous. Use the Home Assistant timezone. Use 09:00 for morning, 13:00 for
daytime, and 19:00 for evening unless the user specifies another time. For an
unqualified 12-hour time, choose the nearest future occurrence. Always send an
absolute ISO-8601/RFC3339 due_at value with a timezone offset; never send a
timezone-less value. Do not claim success if a tool reports an error. If
several reminders match a cancellation or update request, ask the user to
clarify.
```

## Time interpretation

If the user gives only a time, the conversation agent should ask what to
remember. If the user gives only reminder text, it should ask when to deliver
it. For an ambiguous phrase such as `today at 8`, interpret the hour as the
nearest future 08:00 or 20:00 on that date. If neither occurrence is still
possible today, ask the user to clarify instead of silently moving the reminder
to tomorrow.

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

Do not edit the integration version manually in ordinary feature or fix PRs.
Review the HACS and Hassfest checks before merging a Release PR.
