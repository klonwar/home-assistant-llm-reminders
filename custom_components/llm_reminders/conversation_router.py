"""Route reminder phrases to the active external conversation agent."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
import re
from typing import Any

from homeassistant.components import conversation
from homeassistant.components.conversation.agent_manager import get_agent_manager
from homeassistant.components.conversation.models import ConversationInput
from homeassistant.core import HomeAssistant, callback

_LOGGER = logging.getLogger(__name__)

ROUTER_DATA_KEY = "llm_reminders.conversation_router"

# Home Assistant's conversation default agent promotes undeclared trigger-list
# references to wildcard lists when it rebuilds sentence triggers. Prefix/suffix
# variants let the same trigger match a reminder word at any position in the
# utterance without registering a trigger for every full sentence a user might
# say.
_REMINDER_FORMS = (
    "напомни",
    "напомните",
    "напомнить",
    "напомню",
    "напомнишь",
    "напомнит",
    "напомним",
    "напомнил",
    "напомнила",
    "напомнили",
    "напоминание",
    "напоминания",
    "напоминаний",
    "напоминанию",
    "напоминанием",
    "напоминать",
    "напоминай",
    "напоминайте",
    "напоминает",
    "напоминают",
    "напоминал",
    "напоминала",
    "напоминали",
    "remind",
    "reminds",
    "reminded",
    "reminding",
    "reminder",
    "reminders",
)
_REMINDER_ALTERNATIVE = f"({' | '.join(_REMINDER_FORMS)})"
ROUTER_SENTENCES = (
    _REMINDER_ALTERNATIVE,
    f"{{prefix}} {_REMINDER_ALTERNATIVE}",
    f"{_REMINDER_ALTERNATIVE} {{suffix}}",
    f"{{prefix}} {_REMINDER_ALTERNATIVE} {{suffix}}",
)
_REMINDER_WORD_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(map(re.escape, _REMINDER_FORMS)) + r")(?!\w)",
    re.IGNORECASE,
)

_NO_DEVICE_ERROR = {
    "ru": (
        "Не удалось определить устройство, с которого поступила команда. "
        "Повторите запрос с Assist Satellite."
    ),
    "en": (
        "I couldn't determine which Assist Satellite heard that command. "
        "Please try again from an Assist Satellite."
    ),
}
_ROUTING_ERROR = {
    "ru": "Не удалось обработать напоминание через LLM. Повторите запрос позже.",
    "en": "I couldn't process the reminder through the LLM. Please try again later.",
}


def contains_reminder_form(text: str) -> bool:
    """Return whether text contains a supported reminder word."""
    return _REMINDER_WORD_RE.search(text) is not None


def _language_key(language: str | None) -> str:
    """Return a base language key for router responses."""
    if not language:
        return "en"
    return language.replace("_", "-").casefold().split("-", 1)[0]


def _localized_message(messages: dict[str, str], language: str | None) -> str:
    """Return a localized router message with an English fallback."""
    return messages.get(_language_key(language), messages["en"])


def _speech_from_result(result: Any) -> str:
    """Extract plain speech from a conversation result."""
    response = getattr(result, "response", None)
    speech = getattr(response, "speech", None)
    if not isinstance(speech, dict):
        return ""
    plain_speech = speech.get("plain", {})
    if not isinstance(plain_speech, dict):
        return ""
    value = plain_speech.get("speech", "")
    return value.strip() if isinstance(value, str) else ""


def _build_trigger_callback(
    hass: HomeAssistant,
) -> Callable[[ConversationInput, Any], Awaitable[str]]:
    """Build a callback that routes one matched phrase to its agent."""

    async def _handle_trigger(user_input: ConversationInput, _result: Any) -> str:
        """Route a matched reminder phrase and always return speech."""
        language = getattr(user_input, "language", None)
        if not contains_reminder_form(user_input.text):
            # This should be unreachable when Hassil matches ROUTER_SENTENCES,
            # but returning an error keeps the trigger fail-closed if a future
            # sentence template is accidentally broadened.
            _LOGGER.error(
                "Reminder router trigger matched text without a reminder form: "
                "agent_id=%s device_id=%s satellite_id=%s",
                getattr(user_input, "agent_id", None),
                getattr(user_input, "device_id", None),
                getattr(user_input, "satellite_id", None),
            )
            return _localized_message(_ROUTING_ERROR, language)

        if not user_input.device_id or not user_input.satellite_id:
            _LOGGER.warning(
                "Reminder router rejected request without device/satellite context: "
                "agent_id=%s device_id=%s satellite_id=%s",
                getattr(user_input, "agent_id", None),
                getattr(user_input, "device_id", None),
                getattr(user_input, "satellite_id", None),
            )
            return _localized_message(_NO_DEVICE_ERROR, language)

        try:
            result = await conversation.async_converse(
                hass=hass,
                text=user_input.text,
                conversation_id=user_input.conversation_id,
                context=user_input.context,
                language=user_input.language,
                agent_id=user_input.agent_id,
                device_id=user_input.device_id,
                satellite_id=user_input.satellite_id,
                extra_system_prompt=user_input.extra_system_prompt,
            )
        except Exception:
            _LOGGER.exception(
                "Reminder router conversation failed: agent_id=%s "
                "device_id=%s satellite_id=%s",
                getattr(user_input, "agent_id", None),
                getattr(user_input, "device_id", None),
                getattr(user_input, "satellite_id", None),
            )
            return _localized_message(_ROUTING_ERROR, language)

        if speech := _speech_from_result(result):
            return speech

        _LOGGER.error(
            "Reminder router received an empty conversation response: "
            "agent_id=%s device_id=%s satellite_id=%s",
            getattr(user_input, "agent_id", None),
            getattr(user_input, "device_id", None),
            getattr(user_input, "satellite_id", None),
        )
        return _localized_message(_ROUTING_ERROR, language)

    return _handle_trigger


@callback
def register_conversation_router(hass: HomeAssistant) -> Callable[[], None]:
    """Register reminder sentence triggers and return an unregister callback."""
    router_data = hass.data.get(ROUTER_DATA_KEY)
    if isinstance(router_data, dict) and (
        unregister := router_data.get("unregister")
    ) is not None:
        return unregister

    unregister = get_agent_manager(hass).register_trigger(
        sentences=list(ROUTER_SENTENCES),
        trigger_callback=_build_trigger_callback(hass),
    )
    hass.data[ROUTER_DATA_KEY] = {"unregister": unregister}
    return unregister


@callback
def unregister_conversation_router(hass: HomeAssistant) -> None:
    """Unregister reminder sentence triggers if they are currently active."""
    router_data = hass.data.pop(ROUTER_DATA_KEY, None)
    if not isinstance(router_data, dict):
        return
    unregister = router_data.pop("unregister", None)
    if unregister is not None:
        unregister()
