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

_DURATION_SCHEMA = vol.Schema(
    {
        vol.Required(
            "value",
            description="Positive duration number as a string.",
        ): cv.string,
        vol.Required(
            "unit",
            description="Canonical unit: second, minute, hour, day, or week.",
        ): vol.In(
            ("second", "minute", "hour", "day", "week")
        ),
    }
)
_WHEN_SCHEMA = vol.Schema(
    {
        vol.Required(
            "kind",
            description="Use relative for an interval or calendar for a date/time.",
        ): vol.In(("relative", "calendar")),
        vol.Optional(
            "duration",
            description="One or more relative duration components.",
        ): [_DURATION_SCHEMA],
        vol.Optional(
            "target_time",
            description="Local HH:MM after a whole-day or whole-week interval.",
        ): cv.string,
        vol.Optional(
            "date_ref",
            description="Semantic calendar reference for a calendar reminder.",
        ): vol.In(
            (
                "today",
                "tomorrow",
                "day_after_tomorrow",
                "weekday",
                "next_weekday",
                "day_of_month",
                "month_day",
                "explicit",
                "nearest_future",
            )
        ),
        vol.Optional(
            "occurrence",
            description="For weekdays, use next or nearest_future.",
        ): vol.In(("nearest_future", "next")),
        vol.Optional(
            "weekday", description="Canonical English weekday name."
        ): cv.string,
        vol.Optional(
            "month_ref",
            description="Use nearest_future for a day-of-month reference.",
        ): vol.In(("nearest_future",)),
        vol.Optional(
            "month", description="Month number from 1 to 12."
        ): cv.string,
        vol.Optional(
            "year_ref",
            description="Use nearest_future for a month/day reference.",
        ): vol.In(("nearest_future",)),
        vol.Optional(
            "day_of_month",
            description="Day number from 1 to 31.",
        ): cv.string,
        vol.Optional(
            "date_value",
            description="Explicit date in YYYY-MM-DD format.",
        ): cv.string,
        vol.Optional(
            "local_time", description="Local clock time in HH:MM."
        ): cv.string,
        vol.Optional(
            "day_period",
            description="Named local period: morning, day, or evening.",
        ): vol.In(("morning", "day", "evening")),
        vol.Optional(
            "hour",
            description="Hour number; use meridiem when 1-12 is ambiguous.",
        ): cv.string,
        vol.Optional(
            "meridiem",
            description="Use am, pm, or unspecified with hour.",
        ): vol.In(("am", "pm", "unspecified")),
    }
)


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
    description = (
        "Create a one-time reminder. Put the user's time intent in when as a "
        "relative interval or calendar expression. Do not calculate an "
        "absolute timestamp."
    )
    parameters = vol.Schema(
        {
            vol.Required("message", description="Reminder text."): cv.string,
            vol.Required(
                "when",
                description="Structured relative or calendar reminder time.",
            ): _WHEN_SCHEMA,
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
            when=tool_input.tool_args["when"],
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
    description = (
        "Change the text or structured time of one reminder by id. The when "
        "value uses the same relative or calendar contract as create_reminder."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                "reminder_id", description="Reminder identifier."
            ): cv.string,
            vol.Optional("message", description="New reminder text."): cv.string,
            vol.Optional(
                "when",
                description="New structured relative or calendar reminder time.",
            ): _WHEN_SCHEMA,
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
            when=tool_input.tool_args.get("when"),
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
