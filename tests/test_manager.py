from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import importlib
import logging
from pathlib import Path
import sys
import types
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_DIR = ROOT / "custom_components" / "llm_reminders"


def _install_homeassistant_stubs() -> None:
    """Provide the small Home Assistant surface used by ReminderManager."""

    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    exceptions = types.ModuleType("homeassistant.exceptions")
    helpers = types.ModuleType("homeassistant.helpers")
    config_validation = types.ModuleType("homeassistant.helpers.config_validation")
    llm_helpers = types.ModuleType("homeassistant.helpers.llm")
    entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")
    event = types.ModuleType("homeassistant.helpers.event")
    storage = types.ModuleType("homeassistant.helpers.storage")
    util = types.ModuleType("homeassistant.util")
    dt = types.ModuleType("homeassistant.util.dt")
    components = types.ModuleType("homeassistant.components")
    llm_platform = types.ModuleType("homeassistant.components.llm")

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

    class Tool:
        pass

    class LLMTools:
        def __init__(self, *, tools: Any, prompt: str | None) -> None:
            self.tools = tools
            self.prompt = prompt

    class LLMContext:
        pass

    class ToolInput:
        pass

    core.HomeAssistant = HomeAssistant
    core.callback = callback
    exceptions.HomeAssistantError = HomeAssistantError
    config_validation.string = str
    llm_helpers.LLMContext = LLMContext
    llm_helpers.ToolInput = ToolInput
    llm_platform.Tool = Tool
    llm_platform.LLMTools = LLMTools
    entity_registry.async_get = lambda _hass: None
    storage.Store = Store
    event.async_call_later = lambda *_args, **_kwargs: None
    event.async_track_point_in_time = lambda *_args, **_kwargs: None
    dt.now = lambda: datetime.now(timezone.utc)
    dt.as_local = lambda value: value.astimezone()
    dt.get_time_zone = lambda _name: timezone(timedelta(hours=3))

    helpers.entity_registry = entity_registry
    helpers.config_validation = config_validation
    helpers.llm = llm_helpers
    helpers.event = event
    helpers.storage = storage
    components.llm = llm_platform
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
            "homeassistant.helpers.config_validation": config_validation,
            "homeassistant.helpers.llm": llm_helpers,
            "homeassistant.helpers.entity_registry": entity_registry,
            "homeassistant.helpers.event": event,
            "homeassistant.helpers.storage": storage,
            "homeassistant.components": components,
            "homeassistant.components.llm": llm_platform,
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
time_resolver_module = importlib.import_module(f"{_PACKAGE_NAME}.time_resolver")


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


def test_create_resolves_calendar_when(caplog: pytest.LogCaptureFixture) -> None:
    hass = _FakeHass()
    manager = manager_module.ReminderManager(
        hass,
        {manager_module.CONF_DEFAULT_SATELLITE: "assist_satellite.kitchen"},
    )
    caplog.set_level(logging.INFO, logger=manager_module.__name__)

    asyncio.run(
        manager.async_create(
            message="buy bread",
            when={
                "date": "2099-08-01",
                "local_time": "19:00",
            },
            device_id=None,
        )
    )

    reminder = next(iter(manager._reminders.values()))
    assert reminder["due_at"].endswith("+03:00")
    assert "async_create called" in caplog.text
    assert "message='buy bread'" in caplog.text
    assert "when={'date': '2099-08-01'" in caplog.text
    assert "async_create result" in caplog.text
    assert "due_at=2099-08-01T19:00:00+03:00" in caplog.text


def test_update_resolves_calendar_when() -> None:
    hass = _FakeHass()
    manager = manager_module.ReminderManager(hass, {})
    reminder = _reminder()
    manager._reminders[reminder["id"]] = reminder

    asyncio.run(
        manager.async_update(
            reminder_id=reminder["id"],
            when={
                "date": "2099-08-01",
                "local_time": "19:00",
            },
        )
    )

    assert manager._reminders[reminder["id"]]["due_at"].endswith("+03:00")


def test_update_clears_pending_retry_before_rescheduling() -> None:
    hass = _FakeHass()
    manager = manager_module.ReminderManager(hass, {})
    reminder = _reminder()
    manager._reminders[reminder["id"]] = reminder
    unsubscribed: list[str] = []
    manager._retry_scheduled[reminder["id"]] = lambda: unsubscribed.append(
        reminder["id"]
    )

    asyncio.run(
        manager.async_update(
            reminder_id=reminder["id"],
            when={
                "date": "2099-08-01",
                "local_time": "19:00",
            },
        )
    )

    assert unsubscribed == [reminder["id"]]
    assert reminder["id"] not in manager._retry_scheduled


def test_cancel_clears_pending_retry() -> None:
    hass = _FakeHass()
    manager = manager_module.ReminderManager(hass, {})
    reminder = _reminder()
    manager._reminders[reminder["id"]] = reminder
    unsubscribed: list[str] = []
    manager._retry_scheduled[reminder["id"]] = lambda: unsubscribed.append(
        reminder["id"]
    )

    asyncio.run(manager.async_cancel(reminder_id=reminder["id"]))

    assert unsubscribed == [reminder["id"]]
    assert reminder["id"] not in manager._retry_scheduled


def test_normalize_when_infers_relative_and_calendar_shapes() -> None:
    assert time_resolver_module.normalize_when(
        {"duration": [{"value": "5", "unit": "minute"}]}
    ) == {
        "kind": "relative",
        "duration": [{"value": "5", "unit": "minute"}],
    }
    assert time_resolver_module.normalize_when({"local_time": "14:50"}) == {
        "kind": "calendar",
        "date_ref": "nearest_future",
        "local_time": "14:50",
    }
    assert time_resolver_module.normalize_when(
        {"date": "tomorrow", "local_time": "14:50"}
    ) == {
        "kind": "calendar",
        "date_ref": "tomorrow",
        "local_time": "14:50",
    }


def test_resolve_relative_duration_uses_home_assistant_now() -> None:
    local_timezone = timezone(timedelta(hours=3))
    now = datetime(2026, 8, 12, 12, 50, tzinfo=local_timezone)

    due = manager_module.resolve_when(
        {
            "duration": [{"value": "5", "unit": "minute"}],
        },
        now,
        local_timezone,
    )

    assert due == datetime(2026, 8, 12, 12, 55, tzinfo=local_timezone)


def test_resolve_composed_relative_duration_with_target_time() -> None:
    local_timezone = timezone(timedelta(hours=3))
    now = datetime(2026, 8, 12, 12, 50, tzinfo=local_timezone)

    due = manager_module.resolve_when(
        {
            "duration": [{"value": "1", "unit": "week"}],
            "target_time": "15:00",
        },
        now,
        local_timezone,
    )

    assert due == datetime(2026, 8, 19, 15, tzinfo=local_timezone)


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        (
            {
                "date": "tomorrow",
                "local_time": "15:00",
            },
            datetime(2026, 8, 13, 15, tzinfo=timezone(timedelta(hours=3))),
        ),
        (
            {
                "day_of_month": "15",
                "local_time": "13:00",
            },
            datetime(2026, 8, 15, 13, tzinfo=timezone(timedelta(hours=3))),
        ),
        (
            {
                "month": "7",
                "day_of_month": "15",
                "local_time": "13:00",
            },
            datetime(2027, 7, 15, 13, tzinfo=timezone(timedelta(hours=3))),
        ),
        (
            {
                "weekday": "monday",
                "local_time": "09:00",
            },
            datetime(2026, 8, 17, 9, tzinfo=timezone(timedelta(hours=3))),
        ),
        (
            {
                "local_time": "15:00",
            },
            datetime(2026, 8, 12, 15, tzinfo=timezone(timedelta(hours=3))),
        ),
    ],
)
def test_resolve_calendar_references(when: dict[str, Any], expected: datetime) -> None:
    local_timezone = timezone(timedelta(hours=3))
    now = datetime(2026, 8, 12, 12, 50, tzinfo=local_timezone)

    assert manager_module.resolve_when(when, now, local_timezone) == expected


def test_time_without_date_uses_tomorrow_after_time_passes() -> None:
    local_timezone = timezone(timedelta(hours=3))
    now = datetime(2026, 8, 12, 15, 50, tzinfo=local_timezone)

    assert manager_module.resolve_when(
        {"local_time": "14:50"}, now, local_timezone
    ) == datetime(2026, 8, 13, 14, 50, tzinfo=local_timezone)


def test_resolve_day_period_and_ambiguous_eight() -> None:
    local_timezone = timezone(timedelta(hours=3))
    now = datetime(2026, 8, 12, 12, 50, tzinfo=local_timezone)

    assert manager_module.resolve_when(
        {
            "date": "tomorrow",
            "day_period": "morning",
        },
        now,
        local_timezone,
    ) == datetime(2026, 8, 13, 9, tzinfo=local_timezone)
    assert manager_module.resolve_when(
        {
            "date": "today",
            "hour": "8",
            "meridiem": "unspecified",
        },
        now,
        local_timezone,
    ) == datetime(2026, 8, 12, 20, tzinfo=local_timezone)


def test_resolve_rejects_ambiguous_or_past_calendar_time() -> None:
    local_timezone = timezone(timedelta(hours=3))
    now = datetime(2026, 8, 12, 12, 50, tzinfo=local_timezone)

    with pytest.raises(ValueError, match="ambiguous"):
        manager_module.resolve_when(
            {
                "date": "today",
                "hour": "3",
                "meridiem": "unspecified",
            },
            now,
            local_timezone,
        )
    with pytest.raises(ValueError, match="future"):
        manager_module.resolve_when(
            {
                "date": "today",
                "local_time": "09:00",
            },
            now,
            local_timezone,
        )


def test_resolve_rejects_mixed_or_conflicting_time_fields() -> None:
    local_timezone = timezone(timedelta(hours=3))
    now = datetime(2026, 8, 12, 12, 50, tzinfo=local_timezone)

    with pytest.raises(ValueError, match="cannot mix duration and calendar"):
        manager_module.resolve_when(
            {
                "duration": [{"value": "5", "unit": "minute"}],
                "local_time": "15:00",
            },
            now,
            local_timezone,
        )
    with pytest.raises(ValueError, match="date cannot be combined"):
        manager_module.resolve_when(
            {
                "date": "tomorrow",
                "weekday": "monday",
                "local_time": "15:00",
            },
            now,
            local_timezone,
        )
    with pytest.raises(ValueError, match="month requires day_of_month"):
        manager_module.resolve_when(
            {
                "month": "8",
                "local_time": "15:00",
            },
            now,
            local_timezone,
        )
    with pytest.raises(ValueError, match="unsupported fields: kind"):
        manager_module.resolve_when(
            {"kind": "calendar", "local_time": "15:00"},
            now,
            local_timezone,
        )


def test_resolve_rejects_nonexistent_dst_time() -> None:
    try:
        local_timezone = ZoneInfo("Europe/Berlin")
    except ZoneInfoNotFoundError:
        pytest.skip("system timezone data is not installed")
    now = datetime(2026, 3, 28, 12, 0, tzinfo=local_timezone)

    with pytest.raises(ValueError, match="does not exist"):
        manager_module.resolve_when(
            {
                "date": "tomorrow",
                "local_time": "02:30",
            },
            now,
            local_timezone,
        )


def test_tool_schemas_accept_minimal_when_and_reject_internal_fields() -> None:
    vol = pytest.importorskip("voluptuous")
    llm_tools_module = importlib.import_module(f"{_PACKAGE_NAME}.llm_tools")
    valid_create = {
        "message": "call",
        "when": {"local_time": "14:50"},
    }
    assert llm_tools_module.CreateReminderTool.parameters(valid_create) == valid_create

    with pytest.raises(vol.Invalid):
        llm_tools_module.CreateReminderTool.parameters(
            {
                "message": "call",
                "when": {"kind": "calendar", "local_time": "14:50"},
            }
        )
    with pytest.raises(vol.Invalid):
        llm_tools_module.CreateReminderTool.parameters(
            {
                "message": "call",
                "when": {"date_ref": "tomorrow", "local_time": "14:50"},
            }
        )
    with pytest.raises(vol.Invalid):
        llm_tools_module.UpdateReminderTool.parameters(
            {
                "reminder_id": "reminder_test",
                "due_at": "2026-08-12T13:00:00+03:00",
            }
        )
    with pytest.raises(vol.Invalid):
        llm_tools_module.UpdateReminderTool.parameters(
            {
                "reminder_id": "reminder_test",
                "when": {"kind": "calendar", "local_time": "14:50"},
            }
        )


def test_tool_descriptions_explain_the_structured_time_contract() -> None:
    pytest.importorskip("voluptuous")
    llm_tools_module = importlib.import_module(f"{_PACKAGE_NAME}.llm_tools")

    assert "duration for 'in 5 minutes'" in (
        llm_tools_module.CreateReminderTool.description
    )
    assert "nearest future occurrence" in llm_tools_module.CreateReminderTool.description
    assert "Do not send kind, date_ref" in llm_tools_module.CreateReminderTool.description
    assert "same field-only extraction" in (
        llm_tools_module.UpdateReminderTool.description
    )


async def _fake_delivery(reminder_id: str) -> None:
    _fake_delivery.called.append(reminder_id)


_fake_delivery.called: list[str] = []


@pytest.fixture(autouse=True)
def reset_fake_delivery() -> None:
    _fake_delivery.called.clear()
