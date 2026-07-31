"""Tool implementations exposed through the Home Assistant LLM API."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import llm
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.llm import LLMContext, ToolInput

from .const import DOMAIN
from .manager import ReminderManager

_LOGGER = logging.getLogger(__name__)


def get_manager(hass: HomeAssistant) -> ReminderManager | None:
    """Return the configured reminder manager, if one is available."""
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
    """Create a one-time reminder."""

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
        manager = get_manager(hass)
        if manager is None:
            raise HomeAssistantError("The reminder integration is not configured.")
        return await manager.async_create(
            message=tool_input.tool_args["message"],
            due_at=tool_input.tool_args["due_at"],
            device_id=llm_context.device_id,
        )


class ListRemindersTool(llm.Tool):
    """List active one-time reminders."""

    name = "list_reminders"
    description = "List active one-time voice reminders, optionally filtered by text."
    parameters = vol.Schema({vol.Optional("query", default=""): cv.string})

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: ToolInput,
        llm_context: LLMContext,
    ) -> dict[str, Any]:
        manager = get_manager(hass)
        if manager is None:
            raise HomeAssistantError("The reminder integration is not configured.")
        return manager.list_reminders(tool_input.tool_args.get("query"))


class CancelReminderTool(llm.Tool):
    """Cancel one active reminder."""

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
        manager = get_manager(hass)
        if manager is None:
            raise HomeAssistantError("The reminder integration is not configured.")
        return await manager.async_cancel(
            reminder_id=tool_input.tool_args.get("reminder_id"),
            query=tool_input.tool_args.get("query"),
        )


class UpdateReminderTool(llm.Tool):
    """Update one reminder."""

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
        manager = get_manager(hass)
        if manager is None:
            raise HomeAssistantError("The reminder integration is not configured.")
        return await manager.async_update(
            reminder_id=tool_input.tool_args["reminder_id"],
            message=tool_input.tool_args.get("message"),
            due_at=tool_input.tool_args.get("due_at"),
        )


TOOL_CLASSES = (
    CreateReminderTool,
    ListRemindersTool,
    CancelReminderTool,
    UpdateReminderTool,
)


def build_tools() -> list[llm.Tool]:
    """Create a fresh set of reminder tools for an LLM API request."""
    return [tool_class() for tool_class in TOOL_CLASSES]
