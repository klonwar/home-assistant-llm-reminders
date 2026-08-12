from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import logging
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later, async_track_point_in_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DEFAULT_SATELLITE,
    DOMAIN,
    MAX_MESSAGE_LENGTH,
    RETRY_SECONDS,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .helpers import normalize_message, parse_iso_datetime
from .time_resolver import resolve_when

_LOGGER = logging.getLogger(__name__)
_UNAVAILABLE_STATES = {"unknown", "unavailable"}


def _log_reminder(event: str, reminder: dict[str, Any]) -> None:
    """Log reminder details for operation and delivery diagnostics."""
    _LOGGER.info(
        "LLM Reminders %s: reminder_id=%s message=%r due_at=%s satellite=%s",
        event,
        reminder["id"],
        reminder["message"],
        reminder["due_at"],
        reminder["satellite"],
    )


class ReminderManager:
    """Persistent reminder storage and Assist Satellite delivery."""

    def __init__(self, hass: HomeAssistant, options: dict[str, Any]) -> None:
        self.hass = hass
        self.default_satellite = options.get(CONF_DEFAULT_SATELLITE)
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._reminders: dict[str, dict[str, Any]] = {}
        self._scheduled: dict[str, Any] = {}
        self._retry_scheduled: dict[str, Any] = {}
        self._in_flight: set[str] = set()

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        if not stored:
            return

        for item in stored.get("reminders", []):
            if not isinstance(item, dict):
                continue
            reminder_id = item.get("id")
            due_at = item.get("due_at")
            message = item.get("message")
            satellite = item.get("satellite")
            if not all(
                isinstance(value, str) and value
                for value in (reminder_id, due_at, message, satellite)
            ):
                continue
            try:
                parse_iso_datetime(due_at)
            except ValueError:
                _LOGGER.warning("Ignoring reminder %s with invalid due_at", reminder_id)
                continue
            self._reminders[reminder_id] = {
                "id": reminder_id,
                "message": message,
                "due_at": due_at,
                "satellite": satellite,
                "created_at": item.get("created_at", due_at),
            }

    async def async_start(self) -> None:
        for reminder in self._reminders.values():
            self._schedule(reminder)

    async def async_stop(self) -> None:
        for unsubscribe in (*self._scheduled.values(), *self._retry_scheduled.values()):
            unsubscribe()
        self._scheduled.clear()
        self._retry_scheduled.clear()

    async def async_create(
        self,
        message: str,
        when: dict[str, Any],
        device_id: str | None,
    ) -> dict[str, Any]:
        _LOGGER.info(
            "LLM Reminders async_create called: message=%r when=%r device_id=%s",
            message,
            when,
            device_id,
        )
        try:
            clean_message = normalize_message(message, MAX_MESSAGE_LENGTH)
            due = resolve_when(
                when,
                dt_util.now(),
                dt_util.get_time_zone(self.hass.config.time_zone),
            )
        except ValueError as err:
            _LOGGER.warning(
                "LLM Reminders async_create rejected: message=%r when=%r error=%s",
                message,
                when,
                err,
            )
            raise HomeAssistantError(str(err)) from err

        if due <= dt_util.now():
            _LOGGER.warning(
                "LLM Reminders async_create rejected: message=%r due_at=%s "
                "error=The reminder time must be in the future",
                clean_message,
                due.isoformat(),
            )
            raise HomeAssistantError("The reminder time must be in the future.")

        satellite = self._resolve_satellite(device_id)
        if satellite is None:
            _LOGGER.warning(
                "LLM Reminders async_create rejected: message=%r due_at=%s "
                "error=No Assist Satellite is configured",
                clean_message,
                due.isoformat(),
            )
            raise HomeAssistantError(
                "No Assist Satellite is configured for this request."
            )

        reminder_id = f"reminder_{uuid4().hex}"
        reminder = {
            "id": reminder_id,
            "message": clean_message,
            "due_at": due.isoformat(),
            "satellite": satellite,
            "created_at": dt_util.now().isoformat(),
        }
        self._reminders[reminder_id] = reminder
        await self._async_save()
        self._schedule(reminder)

        _log_reminder("async_create result", reminder)
        return {"reminder": reminder}

    def list_reminders(self, query: str | None = None) -> dict[str, Any]:
        _LOGGER.info("LLM Reminders list_reminders called: query=%r", query)
        clean_query = (query or "").strip().casefold()
        reminders = [
            reminder
            for reminder in self._reminders.values()
            if not clean_query
            or clean_query in reminder["message"].casefold()
        ]
        reminders.sort(key=lambda item: item["due_at"])
        _LOGGER.info(
            "LLM Reminders list_reminders result: query=%r count=%d",
            query,
            len(reminders),
        )
        for reminder in reminders:
            _log_reminder("list_reminders item", reminder)
        return {"reminders": reminders}

    async def async_cancel(
        self,
        reminder_id: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        _LOGGER.info(
            "LLM Reminders async_cancel called: reminder_id=%r query=%r",
            reminder_id,
            query,
        )
        matches = self._find_matches(reminder_id, query)
        if not matches:
            _LOGGER.warning(
                "LLM Reminders async_cancel rejected: reminder_id=%r query=%r "
                "error=No matching reminder was found",
                reminder_id,
                query,
            )
            raise HomeAssistantError("No matching reminder was found.")
        if len(matches) > 1:
            _LOGGER.warning(
                "LLM Reminders async_cancel rejected: reminder_id=%r query=%r "
                "matches=%d",
                reminder_id,
                query,
                len(matches),
            )
            matching_text = "; ".join(
                f"{item['id']}: {item['message']} ({item['due_at']})"
                for item in matches
            )
            raise HomeAssistantError(
                "Several reminders match. Ask the user to clarify which one: "
                f"{matching_text}"
            )

        reminder = matches[0]
        self._remove_schedule(reminder["id"])
        self._remove_retry(reminder["id"])
        self._reminders.pop(reminder["id"], None)
        await self._async_save()
        _log_reminder("async_cancel result", reminder)
        return {"cancelled": reminder}

    async def async_update(
        self,
        reminder_id: str,
        message: str | None = None,
        when: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _LOGGER.info(
            "LLM Reminders async_update called: reminder_id=%s message=%r when=%r",
            reminder_id,
            message,
            when,
        )
        reminder = self._reminders.get(reminder_id)
        if reminder is None:
            _LOGGER.warning(
                "LLM Reminders async_update rejected: reminder_id=%s "
                "message=%r when=%r error=The reminder was not found",
                reminder_id,
                message,
                when,
            )
            raise HomeAssistantError("The reminder was not found.")
        if message is None and when is None:
            _LOGGER.warning(
                "LLM Reminders async_update rejected: reminder_id=%s "
                "error=No new message or time",
                reminder_id,
            )
            raise HomeAssistantError("Provide a new message or a new time.")

        new_message = reminder["message"]
        new_due_at = reminder["due_at"]

        if message is not None:
            try:
                new_message = normalize_message(message, MAX_MESSAGE_LENGTH)
            except ValueError as err:
                _LOGGER.warning(
                    "LLM Reminders async_update rejected: reminder_id=%s "
                    "message=%r when=%r error=%s",
                    reminder_id,
                    message,
                    when,
                    err,
                )
                raise HomeAssistantError(str(err)) from err

        if when is not None:
            try:
                due = resolve_when(
                    when,
                    dt_util.now(),
                    dt_util.get_time_zone(self.hass.config.time_zone),
                )
            except ValueError as err:
                _LOGGER.warning(
                    "LLM Reminders async_update rejected: reminder_id=%s "
                    "message=%r when=%r error=%s",
                    reminder_id,
                    message,
                    when,
                    err,
                )
                raise HomeAssistantError(str(err)) from err
            if due <= dt_util.now():
                _LOGGER.warning(
                    "LLM Reminders async_update rejected: reminder_id=%s "
                    "message=%r due_at=%s error=The reminder time must be in the future",
                    reminder_id,
                    new_message,
                    due.isoformat(),
                )
                raise HomeAssistantError("The reminder time must be in the future.")
            new_due_at = due.isoformat()

        reminder["message"] = new_message
        reminder["due_at"] = new_due_at

        self._remove_schedule(reminder_id)
        self._remove_retry(reminder_id)
        await self._async_save()
        self._schedule(reminder)
        _log_reminder("async_update result", reminder)
        return {"reminder": reminder}

    def _find_matches(
        self,
        reminder_id: str | None,
        query: str | None,
    ) -> list[dict[str, Any]]:
        if reminder_id:
            reminder = self._reminders.get(reminder_id)
            return [reminder] if reminder else []

        clean_query = (query or "").strip().casefold()
        if not clean_query:
            return []
        return [
            reminder
            for reminder in self._reminders.values()
            if clean_query in reminder["message"].casefold()
        ]

    def _resolve_satellite(self, device_id: str | None) -> str | None:
        if device_id:
            registry = er.async_get(self.hass)
            candidates = sorted(
                entity.entity_id
                for entity in registry.entities.values()
                if entity.domain == "assist_satellite" and entity.device_id == device_id
            )
            if candidates:
                return candidates[0]
            return None

        if self.default_satellite and self.default_satellite.startswith("assist_satellite."):
            return self.default_satellite
        return None

    def _schedule(self, reminder: dict[str, Any]) -> None:
        reminder_id = reminder["id"]
        self._remove_schedule(reminder_id)
        due = parse_iso_datetime(reminder["due_at"])
        if due <= dt_util.now():
            self.hass.async_create_task(self._async_deliver(reminder_id))
            return

        self._scheduled[reminder_id] = async_track_point_in_time(
            self.hass,
            self._delivery_callback(reminder_id),
            due,
        )

    def _schedule_retry(self, reminder_id: str) -> None:
        self._remove_schedule(reminder_id)
        self._remove_retry(reminder_id)
        self._retry_scheduled[reminder_id] = async_call_later(
            self.hass,
            RETRY_SECONDS,
            self._delivery_callback(reminder_id),
        )

    def _delivery_callback(self, reminder_id: str) -> Callable[[datetime], None]:
        """Return an event-loop callback that starts reminder delivery."""

        @callback
        def _handle_delivery(_now: datetime) -> None:
            self.hass.async_create_task(self._async_deliver(reminder_id))

        return _handle_delivery

    async def _async_deliver(self, reminder_id: str) -> None:
        if reminder_id in self._in_flight:
            _LOGGER.debug(
                "LLM Reminders delivery skipped: reminder_id=%s reason=in_flight",
                reminder_id,
            )
            return
        reminder = self._reminders.get(reminder_id)
        if reminder is None:
            _LOGGER.debug(
                "LLM Reminders delivery skipped: reminder_id=%s reason=not_found",
                reminder_id,
            )
            return

        _log_reminder("delivery started", reminder)
        self._remove_schedule(reminder_id)
        self._remove_retry(reminder_id)
        self._in_flight.add(reminder_id)
        try:
            state = self.hass.states.get(reminder["satellite"])
            if state is None or state.state in _UNAVAILABLE_STATES or state.state != "idle":
                _LOGGER.warning(
                    "LLM Reminders delivery retry scheduled: reminder_id=%s "
                    "message=%r due_at=%s satellite=%s state=%s",
                    reminder["id"],
                    reminder["message"],
                    reminder["due_at"],
                    reminder["satellite"],
                    state.state if state is not None else None,
                )
                self._schedule_retry(reminder_id)
                return

            try:
                await self.hass.services.async_call(
                    "assist_satellite",
                    "announce",
                    {
                        "entity_id": reminder["satellite"],
                        "message": self._announcement_message(reminder),
                        "preannounce": False,
                    },
                    blocking=True,
                )
            except HomeAssistantError:
                _LOGGER.exception(
                    "LLM Reminders delivery failed: reminder_id=%s message=%r "
                    "due_at=%s satellite=%s",
                    reminder["id"],
                    reminder["message"],
                    reminder["due_at"],
                    reminder["satellite"],
                )
                self._schedule_retry(reminder_id)
                return

            self._reminders.pop(reminder_id, None)
            await self._async_save()
            _log_reminder("delivery result", reminder)
        finally:
            self._in_flight.discard(reminder_id)

    @staticmethod
    def _announcement_message(reminder: dict[str, Any]) -> str:
        return f"Напоминание: {reminder['message']}."

    async def _async_save(self) -> None:
        await self._store.async_save({"reminders": list(self._reminders.values())})

    @callback
    def _remove_schedule(self, reminder_id: str) -> None:
        unsubscribe = self._scheduled.pop(reminder_id, None)
        if unsubscribe:
            unsubscribe()

    @callback
    def _remove_retry(self, reminder_id: str) -> None:
        unsubscribe = self._retry_scheduled.pop(reminder_id, None)
        if unsubscribe:
            unsubscribe()
