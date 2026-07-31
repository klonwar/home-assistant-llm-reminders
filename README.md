# LLM Reminders for Home Assistant

An experimental, generic Home Assistant custom integration that contributes
natural-language reminder tools to Home Assistant's LLM API.

The integration is deliberately independent of any particular household. It
does not contain entity IDs, IP addresses, API keys, tokens, exported states,
or other instance-specific data.

## What it provides

The integration exposes four tools to an LLM conversation agent:

- `create_reminder` — create a one-time reminder from normalized text and an
  absolute ISO-8601 due time;
- `list_reminders` — list active reminders, optionally filtered by text;
- `cancel_reminder` — cancel a reminder by ID or a unique text query;
- `update_reminder` — change a reminder's text or due time.

The LLM is responsible for understanding the user's natural language. The
integration is responsible for validation, persistence, scheduling, delivery,
and returning the result of the operation. The internal storage and scheduler
are not exposed to the model.

## Installation

### HACS

This repository is structured as a HACS integration repository. Add the GitHub
repository as a custom HACS repository with type `Integration`, download it,
and restart Home Assistant. HACS custom repositories are documented at
<https://hacs.xyz/docs/faq/custom_repositories/>.

Before publishing this repository, replace the placeholder repository URLs in
`custom_components/llm_reminders/manifest.json`.

### Manual development install

Copy the integration directory into the Home Assistant configuration directory:

```text
config/
└── custom_components/
    └── llm_reminders/
```

Restart Home Assistant after copying the files.

## Configuration

Open `Settings → Devices & services → Add integration`, select **LLM
Reminders**, and configure an optional default Assist Satellite.

The default satellite is used only when the LLM request has no device context.
When the request includes a Home Assistant device ID, the integration first
looks for an `assist_satellite` entity belonging to that device. This makes the
same package usable with one or many satellites without hardcoding their names.

The OpenRouter conversation integration remains responsible for the model
connection. Configure it separately and enable Assist/home-control mode so its
conversation agent can receive Home Assistant LLM tools.

After setup, verify tool calls in the Assist Debug dialog. The tools are not
shown as ordinary entities; they are callable LLM tools.

## Recommended system-prompt rules

Keep the user's existing system prompt and add equivalent instructions for
reminders:

```text
Use reminder tools for one-time spoken reminders.
Ask concise follow-up questions when reminder text or time is missing or
ambiguous. Use the Home Assistant timezone. Use 09:00 for morning, 13:00 for
daytime, and 19:00 for evening unless the user specifies another time. For an
unqualified 12-hour time, choose the nearest future occurrence. Do not claim
success if a tool reports an error. If several reminders match a cancellation
or update request, ask the user to clarify.
```

The integration does not replace the conversation agent, speech-to-text, or
text-to-speech provider. It also does not modify native Home Assistant/LVA
timer intents.

## Example tool flow

User:

```text
Напомни сегодня вечером купить хлеб
```

The LLM calls:

```json
{
  "message": "купить хлеб",
  "due_at": "2026-08-01T19:00:00+03:00"
}
```

The integration stores the reminder and later announces it through the Assist
Satellite associated with the request device, or the configured default
satellite.

If the user gives only a time, the conversation agent should ask what to
remember. If the user gives only a reminder text, it should ask when to
deliver it. For an ambiguous phrase such as `сегодня в 8`, interpret the hour
as the nearest future 08:00 or 20:00 on that date. If neither occurrence is
still possible today, ask the user to clarify instead of silently moving the
reminder to tomorrow.

## Persistence and delivery

Reminders are persisted in Home Assistant's private `.storage` area. The
public repository contains no reminder data. Pending reminders are scheduled
again after Home Assistant restarts. If a target satellite is unavailable or
busy, delivery is retried rather than redirected to another device.

## Current limitations

- The first version intentionally does not persist idempotency keys. A rare
  provider timeout followed by a repeated tool call may create a duplicate.
- Reminder records are one-time events; native HA/LVA timers remain separate.
- The integration does not provide a calendar UI.
- The exact 15-second continued-conversation listening timeout is controlled by
  the Assist satellite/conversation pipeline, not by the LLM tool API. This
  package does not confuse it with the overall Assist pipeline timeout. A
  future satellite-specific adapter can start the timeout when the satellite
  enters `listening`.

## Development

The package is intentionally self-contained and suitable for a separate public
repository. Run static checks before publishing:

```bash
python -m compileall custom_components/llm_reminders
python -m pytest tests
```

No secrets or Home Assistant instance exports belong in this repository.
