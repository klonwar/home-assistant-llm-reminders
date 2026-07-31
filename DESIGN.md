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
