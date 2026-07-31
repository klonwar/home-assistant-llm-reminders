from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import llm
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.llm import LLMContext, ToolInput

from .const import DOMAIN
from .manager import ReminderManager


def _manager(hass: HomeAssistant) -> ReminderManager | None:
    managers = hass.data.get(DOMAIN, {})
    return next(iter(managers.values()), None)


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
    if _manager(hass) is None:
        return None

    timezone = hass.config.time_zone or "Home Assistant timezone"
    return llm.LLMTools(
        tools=[
            CreateReminderTool(),
            ListRemindersTool(),
            CancelReminderTool(),
            UpdateReminderTool(),
        ],
        prompt=(
            "Use these tools for one-time spoken reminders. "
            "The user speaks Russian, but tool arguments must be normalized. "
            f"The Home Assistant timezone is {timezone}. "
            "create_reminder requires message and an absolute ISO-8601 due_at "
            "with timezone. Use the nearest future occurrence for ambiguous "
            "12-hour times. For a phrase such as 'сегодня в 8', interpret "
            "8 as the nearest future 08:00 or 20:00 during that day; if no "
            "matching time remains today, ask for clarification. Use 09:00 "
            "for morning, 13:00 for daytime, and 19:00 for evening unless "
            "the user specifies another time. If the reminder text or time "
            "is missing, ask one concise follow-up question. A completed "
            "tool call is successful; if the tool reports an error, explain "
            "it briefly instead of claiming success. "
            "If a cancellation or update matches multiple reminders, ask the "
            "user to clarify instead of choosing one. Keep responses concise "
            "and in Russian."
        ),
    )
