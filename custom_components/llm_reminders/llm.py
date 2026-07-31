from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)
_MODULE_PATH = Path(__file__).resolve()
_LOGGER.info("Loading LLM Reminders LLM platform module: file=%s", _MODULE_PATH)

try:
    import voluptuous as vol
    from homeassistant.core import HomeAssistant, callback
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import config_validation as cv
    from homeassistant.helpers.llm import LLMContext, ToolInput

    from .const import DOMAIN, PROMPT_DATA_KEY
    from .manager import ReminderManager
    from .prompt_loader import build_prompt
except Exception:
    _LOGGER.exception(
        "LLM Reminders LLM platform module dependency import failed: file=%s",
        _MODULE_PATH,
    )
    raise

try:
    from homeassistant.components import llm
except Exception:
    _LOGGER.exception(
        "Failed to import the Home Assistant LLM platform for LLM Reminders"
    )
    raise
else:
    _LOGGER.info(
        "Home Assistant LLM platform imported for LLM Reminders: "
        "module=%s llm_module=%s",
        _MODULE_PATH,
        getattr(llm, "__file__", None),
    )


def _log_loader_state(hass: HomeAssistant, phase: str) -> None:
    """Log state of the Home Assistant LLM platform loader."""
    config = getattr(hass, "config", None)
    components = getattr(config, "components", None)
    top_level_components = getattr(config, "top_level_components", None)
    loader_key = getattr(llm, "DATA_PLATFORMS", "llm_platforms")
    loader = hass.data.get(loader_key)
    processed = getattr(loader, "_processed", None)
    _LOGGER.info(
        "LLM Reminders LLM loader state: phase=%s loader_key=%s "
        "loader_type=%s loader_initialized=%s processed_domains=%s "
        "hass_data_keys=%s config_components=%s top_level_components=%s "
        "reminder_data_type=%s reminder_entry_ids=%s",
        phase,
        loader_key,
        type(loader).__name__ if loader is not None else None,
        loader is not None,
        sorted(str(domain) for domain in processed)
        if isinstance(processed, dict)
        else None,
        sorted(str(key) for key in hass.data),
        sorted(str(component) for component in components)
        if components is not None
        else None,
        sorted(str(component) for component in top_level_components)
        if top_level_components is not None
        else None,
        type(hass.data.get(DOMAIN)).__name__
        if DOMAIN in hass.data
        else None,
        list(hass.data[DOMAIN])
        if isinstance(hass.data.get(DOMAIN), dict)
        else None,
    )


def _manager(hass: HomeAssistant) -> ReminderManager | None:
    managers = hass.data.get(DOMAIN)
    if managers is None:
        _LOGGER.warning(
            "LLM Reminders manager lookup failed: hass.data[%s] is missing",
            DOMAIN,
        )
        return None

    if not isinstance(managers, dict):
        _LOGGER.error(
            "LLM Reminders manager lookup failed: hass.data[%s] has unexpected type %s",
            DOMAIN,
            type(managers).__name__,
        )
        return None

    if not managers:
        _LOGGER.warning(
            "LLM Reminders manager lookup failed: hass.data[%s] is empty",
            DOMAIN,
        )
        return None

    manager = next(iter(managers.values()), None)
    if manager is None:
        _LOGGER.warning(
            "LLM Reminders manager lookup failed: hass.data[%s] has no manager values; entry_ids=%s",
            DOMAIN,
            list(managers),
        )
        return None

    _LOGGER.debug(
        "LLM Reminders manager found: entry_ids=%s manager_type=%s",
        list(managers),
        type(manager).__name__,
    )
    return manager


class CreateReminderTool(llm.Tool):
    name = "create_reminder"
    description = "Create a one-time voice reminder with an absolute ISO-8601 due time."
    parameters = vol.Schema(
        {
            vol.Required("message"): cv.string,
            vol.Required("due_at"): cv.string,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: ToolInput,
        llm_context: LLMContext,
    ) -> dict[str, Any]:
        manager = _manager(hass)
        if manager is None:
            raise HomeAssistantError("The reminder integration is not configured.")
        return await manager.async_create(
            message=tool_input.tool_args["message"],
            due_at=tool_input.tool_args["due_at"],
            device_id=llm_context.device_id,
        )


class ListRemindersTool(llm.Tool):
    name = "list_reminders"
    description = "List active one-time voice reminders, optionally filtered by text."
    parameters = vol.Schema({vol.Optional("query", default=""): cv.string})

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: ToolInput,
        llm_context: LLMContext,
    ) -> dict[str, Any]:
        manager = _manager(hass)
        if manager is None:
            raise HomeAssistantError("The reminder integration is not configured.")
        return manager.list_reminders(tool_input.tool_args.get("query"))


class CancelReminderTool(llm.Tool):
    name = "cancel_reminder"
    description = "Cancel one active reminder by its id or by a unique text query."
    parameters = vol.Schema(
        {
            vol.Optional("reminder_id"): cv.string,
            vol.Optional("query"): cv.string,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: ToolInput,
        llm_context: LLMContext,
    ) -> dict[str, Any]:
        manager = _manager(hass)
        if manager is None:
            raise HomeAssistantError("The reminder integration is not configured.")
        return await manager.async_cancel(
            reminder_id=tool_input.tool_args.get("reminder_id"),
            query=tool_input.tool_args.get("query"),
        )


class UpdateReminderTool(llm.Tool):
    name = "update_reminder"
    description = "Change the text or absolute due time of one reminder by id."
    parameters = vol.Schema(
        {
            vol.Required("reminder_id"): cv.string,
            vol.Optional("message"): cv.string,
            vol.Optional("due_at"): cv.string,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: ToolInput,
        llm_context: LLMContext,
    ) -> dict[str, Any]:
        manager = _manager(hass)
        if manager is None:
            raise HomeAssistantError("The reminder integration is not configured.")
        return await manager.async_update(
            reminder_id=tool_input.tool_args["reminder_id"],
            message=tool_input.tool_args.get("message"),
            due_at=tool_input.tool_args.get("due_at"),
        )


@callback
def async_get_tools(
    hass: HomeAssistant,
    llm_context: LLMContext,
    api_id: str,
) -> llm.LLMTools | None:
    """Return reminder tools for the selected Home Assistant LLM API."""
    _LOGGER.info(
        "async_get_tools called for LLM Reminders: api_id=%s "
        "context_platform=%s context_assistant=%s context_language=%s "
        "context_device_id=%s",
        api_id,
        getattr(llm_context, "platform", None),
        getattr(llm_context, "assistant", None),
        getattr(llm_context, "language", None),
        getattr(llm_context, "device_id", None),
    )
    _log_loader_state(hass, "async_get_tools before manager lookup")
    manager = _manager(hass)
    if manager is None:
        _LOGGER.warning(
            "async_get_tools returning None: no LLM Reminders manager for api_id=%s",
            api_id,
        )
        return None

    timezone = hass.config.time_zone or "Home Assistant timezone"
    prompt_catalog = hass.data.get(PROMPT_DATA_KEY)
    if prompt_catalog is None:
        _LOGGER.error(
            "LLM Reminders prompt catalog is not loaded; returning tools without "
            "the integration prompt: api_id=%s",
            api_id,
        )
        prompt = None
    else:
        prompt = build_prompt(prompt_catalog, llm_context.language)
        _LOGGER.info(
            "LLM Reminders prompt selected: api_id=%s language=%s prompt_length=%d",
            api_id,
            llm_context.language,
            len(prompt),
        )
    _LOGGER.info(
        "async_get_tools building tools: api_id=%s manager_type=%s timezone=%s",
        api_id,
        type(manager).__name__,
        timezone,
    )
    tools = [
        CreateReminderTool(),
        ListRemindersTool(),
        CancelReminderTool(),
        UpdateReminderTool(),
    ]
    try:
        result = llm.LLMTools(
            tools=tools,
            prompt=prompt,
        )
    except Exception:
        _LOGGER.exception(
            "async_get_tools failed while constructing LLMTools: api_id=%s "
            "tool_names=%s",
            api_id,
            [tool.name for tool in tools],
        )
        raise
    _LOGGER.info(
        "async_get_tools returning LLM Reminders tools: api_id=%s tool_names=%s",
        api_id,
        [tool.name for tool in tools],
    )
    return result


_LOGGER.info(
    "LLM Reminders LLM platform module loaded successfully: file=%s "
    "available_tools=%s",
    _MODULE_PATH,
    [
        CreateReminderTool.name,
        ListRemindersTool.name,
        CancelReminderTool.name,
        UpdateReminderTool.name,
    ],
)
