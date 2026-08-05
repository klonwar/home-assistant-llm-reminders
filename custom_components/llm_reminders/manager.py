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

_LOGGER = logging.getLogger(__name__)
_UNAVAILABLE_STATES = {"unknown", "unavailable"}


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
        due_at: str,
        device_id: str | None,
    ) -> dict[str, Any]:
        try:
            clean_message = normalize_message(message, MAX_MESSAGE_LENGTH)
            due = parse_iso_datetime(
                due_at,
                local_timezone=dt_util.get_time_zone(self.hass.config.time_zone),
            )
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

        if due <= dt_util.now():
            raise HomeAssistantError("The reminder time must be in the future.")

        satellite = self._resolve_satellite(device_id)
        if satellite is None:
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

        return {"reminder": reminder}

    def list_reminders(self, query: str | None = None) -> dict[str, Any]:
        clean_query = (query or "").strip().casefold()
        reminders = [
            reminder
            for reminder in self._reminders.values()
            if not clean_query
            or clean_query in reminder["message"].casefold()
        ]
        reminders.sort(key=lambda item: item["due_at"])
        return {"reminders": reminders}

    async def async_cancel(
        self,
        reminder_id: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        matches = self._find_matches(reminder_id, query)
        if not matches:
            raise HomeAssistantError("No matching reminder was found.")
        if len(matches) > 1:
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
        self._reminders.pop(reminder["id"], None)
        await self._async_save()
        return {"cancelled": reminder}

    async def async_update(
        self,
        reminder_id: str,
        message: str | None = None,
        due_at: str | None = None,
    ) -> dict[str, Any]:
        reminder = self._reminders.get(reminder_id)
        if reminder is None:
            raise HomeAssistantError("The reminder was not found.")
        if message is None and due_at is None:
            raise HomeAssistantError("Provide a new message or a new time.")

        new_message = reminder["message"]
        new_due_at = reminder["due_at"]

        if message is not None:
            try:
                new_message = normalize_message(message, MAX_MESSAGE_LENGTH)
            except ValueError as err:
                raise HomeAssistantError(str(err)) from err

        if due_at is not None:
            try:
                due = parse_iso_datetime(
                    due_at,
                    local_timezone=dt_util.get_time_zone(self.hass.config.time_zone),
                )
            except ValueError as err:
                raise HomeAssistantError(str(err)) from err
            if due <= dt_util.now():
                raise HomeAssistantError("The reminder time must be in the future.")
            new_due_at = due.isoformat()

        reminder["message"] = new_message
        reminder["due_at"] = new_due_at

        self._remove_schedule(reminder_id)
        await self._async_save()
        self._schedule(reminder)
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
            return
        reminder = self._reminders.get(reminder_id)
        if reminder is None:
            return

        self._remove_schedule(reminder_id)
        self._remove_retry(reminder_id)
        self._in_flight.add(reminder_id)
        try:
            state = self.hass.states.get(reminder["satellite"])
            if state is None or state.state in _UNAVAILABLE_STATES or state.state != "idle":
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
                _LOGGER.exception("Unable to deliver reminder %s", reminder_id)
                self._schedule_retry(reminder_id)
                return

            self._reminders.pop(reminder_id, None)
            await self._async_save()
        finally:
            self._in_flight.discard(reminder_id)

    @staticmethod
    def _announcement_message(reminder: dict[str, Any]) -> str:
        due = parse_iso_datetime(reminder["due_at"])
        local_due = dt_util.as_local(due)
        return (
            f"Напоминание: {reminder['message']}. "
            f"Запланировано на {local_due.strftime('%d.%m.%Y в %H:%M')}."
        )

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
