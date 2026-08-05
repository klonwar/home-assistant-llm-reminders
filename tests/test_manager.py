from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import importlib
import logging
from pathlib import Path
import sys
import types
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_DIR = ROOT / "custom_components" / "llm_reminders"


def _install_homeassistant_stubs() -> None:
    """Provide the small Home Assistant surface used by ReminderManager."""

    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    exceptions = types.ModuleType("homeassistant.exceptions")
    helpers = types.ModuleType("homeassistant.helpers")
    entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")
    event = types.ModuleType("homeassistant.helpers.event")
    storage = types.ModuleType("homeassistant.helpers.storage")
    util = types.ModuleType("homeassistant.util")
    dt = types.ModuleType("homeassistant.util.dt")

    class HomeAssistant:
        pass

    def callback(function: Any) -> Any:
        function.__callback = True
        return function

    class HomeAssistantError(Exception):
        pass

    class Store:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.saved: list[dict[str, Any]] = []

        async def async_load(self) -> dict[str, Any] | None:
            return None

        async def async_save(self, data: dict[str, Any]) -> None:
            self.saved.append(data)

    core.HomeAssistant = HomeAssistant
    core.callback = callback
    exceptions.HomeAssistantError = HomeAssistantError
    entity_registry.async_get = lambda _hass: None
    storage.Store = Store
    event.async_call_later = lambda *_args, **_kwargs: None
    event.async_track_point_in_time = lambda *_args, **_kwargs: None
    dt.now = lambda: datetime.now(timezone.utc)
    dt.as_local = lambda value: value.astimezone()
    dt.get_time_zone = lambda _name: timezone(timedelta(hours=3))

    helpers.entity_registry = entity_registry
    helpers.event = event
    helpers.storage = storage
    util.dt = dt
    homeassistant.core = core
    homeassistant.exceptions = exceptions
    homeassistant.helpers = helpers
    homeassistant.util = util

    sys.modules.update(
        {
            "homeassistant": homeassistant,
            "homeassistant.core": core,
            "homeassistant.exceptions": exceptions,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.entity_registry": entity_registry,
            "homeassistant.helpers.event": event,
            "homeassistant.helpers.storage": storage,
            "homeassistant.util": util,
            "homeassistant.util.dt": dt,
        }
    )


_install_homeassistant_stubs()
_PACKAGE_NAME = "llm_reminders_test_package"
_package = types.ModuleType(_PACKAGE_NAME)
_package.__path__ = [str(INTEGRATION_DIR)]
sys.modules[_PACKAGE_NAME] = _package
manager_module = importlib.import_module(f"{_PACKAGE_NAME}.manager")


class _FakeState:
    def __init__(self, state: str) -> None:
        self.state = state


class _FakeServices:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any], bool]] = []

    async def async_call(
        self,
        domain: str,
        service: str,
        data: dict[str, Any],
        *,
        blocking: bool,
    ) -> None:
        self.calls.append((domain, service, data, blocking))


class _FakeHass:
    def __init__(self, satellite_state: str = "idle") -> None:
        self.async_tasks: list[Any] = []
        self.config = types.SimpleNamespace(time_zone="Europe/Moscow")
        self.states = types.SimpleNamespace(
            get=lambda _entity_id: _FakeState(satellite_state)
        )
        self.services = _FakeServices()

    def async_create_task(self, coroutine: Any) -> None:
        self.async_tasks.append(coroutine)


def _reminder() -> dict[str, Any]:
    due_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    return {
        "id": "reminder_test",
        "message": "buy bread",
        "due_at": due_at,
        "satellite": "assist_satellite.kitchen",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _run_queued_tasks(hass: _FakeHass) -> None:
    while hass.async_tasks:
        asyncio.run(hass.async_tasks.pop(0))


def test_due_callback_is_event_loop_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def track_point_in_time(_hass: Any, action: Any, point_in_time: datetime) -> Any:
        captured["action"] = action
        captured["point_in_time"] = point_in_time
        return lambda: None

    monkeypatch.setattr(manager_module, "async_track_point_in_time", track_point_in_time)
    hass = _FakeHass()
    manager = manager_module.ReminderManager(hass, {})

    manager._async_deliver = _fake_delivery  # type: ignore[method-assign]
    manager._schedule(_reminder())

    callback = captured["action"]
    assert getattr(callback, "__callback", False) is True
    callback(datetime.now(timezone.utc))
    _run_queued_tasks(hass)

    assert _fake_delivery.called == ["reminder_test"]


def test_retry_callback_is_event_loop_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def call_later(_hass: Any, delay: int, action: Any) -> Any:
        captured["delay"] = delay
        captured["action"] = action
        return lambda: None

    monkeypatch.setattr(manager_module, "async_call_later", call_later)
    hass = _FakeHass()
    manager = manager_module.ReminderManager(hass, {})

    manager._async_deliver = _fake_delivery  # type: ignore[method-assign]
    manager._schedule_retry("reminder_test")

    callback = captured["action"]
    assert getattr(callback, "__callback", False) is True
    callback(datetime.now(timezone.utc))
    _run_queued_tasks(hass)

    assert captured["delay"] == manager_module.RETRY_SECONDS
    assert _fake_delivery.called == ["reminder_test"]


def test_delivery_announces_and_removes_reminder() -> None:
    hass = _FakeHass()
    manager = manager_module.ReminderManager(hass, {})
    reminder = _reminder()
    manager._reminders[reminder["id"]] = reminder

    asyncio.run(manager._async_deliver(reminder["id"]))

    assert reminder["id"] not in manager._reminders
    assert len(hass.services.calls) == 1
    assert hass.services.calls[0][0:2] == ("assist_satellite", "announce")
    assert hass.services.calls[0][2]["message"] == "Напоминание: buy bread."


def test_delivery_retries_when_satellite_is_busy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = _FakeHass(satellite_state="playing")
    manager = manager_module.ReminderManager(hass, {})
    reminder = _reminder()
    manager._reminders[reminder["id"]] = reminder
    retries: list[str] = []
    monkeypatch.setattr(manager, "_schedule_retry", retries.append)

    asyncio.run(manager._async_deliver(reminder["id"]))

    assert retries == [reminder["id"]]
    assert reminder["id"] in manager._reminders
    assert not hass.services.calls


def test_create_localizes_naive_due_at(caplog: pytest.LogCaptureFixture) -> None:
    hass = _FakeHass()
    manager = manager_module.ReminderManager(
        hass,
        {manager_module.CONF_DEFAULT_SATELLITE: "assist_satellite.kitchen"},
    )
    caplog.set_level(logging.INFO, logger=manager_module.__name__)

    asyncio.run(
        manager.async_create(
            message="buy bread",
            due_at="2099-08-01T19:00:00",
            device_id=None,
        )
    )

    reminder = next(iter(manager._reminders.values()))
    assert reminder["due_at"].endswith("+03:00")
    assert "async_create called" in caplog.text
    assert "message='buy bread'" in caplog.text
    assert "due_at='2099-08-01T19:00:00'" in caplog.text
    assert "async_create result" in caplog.text
    assert "due_at=2099-08-01T19:00:00+03:00" in caplog.text


def test_update_preserves_explicit_due_at_offset() -> None:
    hass = _FakeHass()
    manager = manager_module.ReminderManager(hass, {})
    reminder = _reminder()
    manager._reminders[reminder["id"]] = reminder

    asyncio.run(
        manager.async_update(
            reminder_id=reminder["id"],
            due_at="2099-08-01T19:00:00+05:00",
        )
    )

    assert manager._reminders[reminder["id"]]["due_at"].endswith("+05:00")


async def _fake_delivery(reminder_id: str) -> None:
    _fake_delivery.called.append(reminder_id)


_fake_delivery.called: list[str] = []


@pytest.fixture(autouse=True)
def reset_fake_delivery() -> None:
    _fake_delivery.called.clear()
