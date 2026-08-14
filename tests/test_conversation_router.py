from __future__ import annotations

import asyncio
from dataclasses import dataclass
import importlib
from pathlib import Path
import sys
import types
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_DIR = ROOT / "custom_components" / "llm_reminders"


def _install_homeassistant_stubs() -> tuple[types.ModuleType, types.ModuleType]:
    """Provide the Home Assistant conversation surface used by the router."""

    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    components = types.ModuleType("homeassistant.components")
    conversation = types.ModuleType("homeassistant.components.conversation")
    agent_manager = types.ModuleType(
        "homeassistant.components.conversation.agent_manager"
    )
    models = types.ModuleType("homeassistant.components.conversation.models")

    class HomeAssistant:
        def __init__(self) -> None:
            self.data: dict[str, Any] = {}

    def callback(function: Any) -> Any:
        function.__callback = True
        return function

    async def async_converse(**_kwargs: Any) -> Any:
        return None

    @dataclass
    class ConversationInput:
        text: str
        context: Any
        conversation_id: str | None
        device_id: str | None
        satellite_id: str | None
        language: str
        agent_id: str
        extra_system_prompt: str | None = None

    core.HomeAssistant = HomeAssistant
    core.callback = callback
    conversation.async_converse = async_converse
    models.ConversationInput = ConversationInput
    components.conversation = conversation
    conversation.agent_manager = agent_manager
    conversation.models = models
    homeassistant.core = core
    homeassistant.components = components

    sys.modules.update(
        {
            "homeassistant": homeassistant,
            "homeassistant.core": core,
            "homeassistant.components": components,
            "homeassistant.components.conversation": conversation,
            "homeassistant.components.conversation.agent_manager": agent_manager,
            "homeassistant.components.conversation.models": models,
        }
    )
    return conversation, agent_manager


conversation_stub, agent_manager_stub = _install_homeassistant_stubs()
agent_manager_stub.get_agent_manager = lambda _hass: None
PACKAGE_NAME = "llm_reminders_router_test_package"
package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(INTEGRATION_DIR)]
sys.modules[PACKAGE_NAME] = package
router_module = importlib.import_module(f"{PACKAGE_NAME}.conversation_router")
ConversationInput = sys.modules[
    "homeassistant.components.conversation.models"
].ConversationInput


class _FakeAgentManager:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.unregister_calls = 0

    def register_trigger(self, *, sentences: list[str], trigger_callback: Any) -> Any:
        self.calls.append(
            {"sentences": sentences, "trigger_callback": trigger_callback}
        )

        def unregister() -> None:
            self.unregister_calls += 1

        return unregister


def _input(
    text: str = "напомни продолжить через десять минут",
    *,
    device_id: str | None = "device-kitchen",
    language: str = "ru-RU",
) -> Any:
    return ConversationInput(
        text=text,
        context=types.SimpleNamespace(id="context-id"),
        conversation_id="conversation-id",
        device_id=device_id,
        satellite_id="assist_satellite.kitchen",
        language=language,
        agent_id="conversation.gemma",
        extra_system_prompt="extra prompt",
    )


def _result(speech: str) -> Any:
    return types.SimpleNamespace(
        response=types.SimpleNamespace(
            speech={"plain": {"speech": speech}},
        )
    )


@pytest.mark.parametrize(
    "text",
    [
        "напомни продолжить через десять минут",
        "напомните продолжить через десять минут",
        "создай напоминание о звонке",
        "напоминанием будет купить хлеб",
        "remind me to call tomorrow",
        "set a reminder for the meeting",
        "I was reminding you about the appointment",
        "напомни-ка про документы",
    ],
)
def test_contains_reminder_form_accepts_supported_forms(text: str) -> None:
    assert router_module.contains_reminder_form(text)


@pytest.mark.parametrize(
    "text",
    [
        "включи свет",
        "поставь таймер на пять минут",
        "remindable is not a command",
        "напоминательный режим",
    ],
)
def test_contains_reminder_form_rejects_non_trigger_words(text: str) -> None:
    assert not router_module.contains_reminder_form(text)


def test_trigger_sentences_cover_forms_and_positions() -> None:
    assert len(router_module.ROUTER_SENTENCES) == 4
    assert any("напоминание" in sentence for sentence in router_module.ROUTER_SENTENCES)
    assert any("reminder" in sentence for sentence in router_module.ROUTER_SENTENCES)
    assert any("{prefix}" in sentence for sentence in router_module.ROUTER_SENTENCES)
    assert any("{suffix}" in sentence for sentence in router_module.ROUTER_SENTENCES)


def test_trigger_sentences_match_hassil_when_available() -> None:
    """Exercise the wildcard templates with the same matcher used by HA."""
    pytest.importorskip("hassil")
    from hassil.intents import Intents
    from hassil.recognize import recognize

    intents = Intents.from_dict(
        {
            "language": "en",
            "intents": {
                "ReminderTrigger": {
                    "data": [{"sentences": list(router_module.ROUTER_SENTENCES)}]
                }
            },
            "lists": {
                "prefix": {"wildcard": True},
                "suffix": {"wildcard": True},
            },
        }
    )

    for text in (
        "напомни продолжить через десять минут",
        "создай напоминание о звонке",
        "remind me to call tomorrow",
        "please set a reminder for the meeting",
    ):
        assert recognize(text, intents) is not None


def test_router_registration_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    hass = types.SimpleNamespace(data={})
    manager = _FakeAgentManager()
    monkeypatch.setattr(router_module, "get_agent_manager", lambda _hass: manager)

    first = router_module.register_conversation_router(hass)
    second = router_module.register_conversation_router(hass)

    assert first is second
    assert len(manager.calls) == 1

    router_module.unregister_conversation_router(hass)
    router_module.unregister_conversation_router(hass)

    assert manager.unregister_calls == 1
    assert router_module.ROUTER_DATA_KEY not in hass.data


def test_router_callback_preserves_conversation_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = types.SimpleNamespace(data={})
    manager = _FakeAgentManager()
    monkeypatch.setattr(router_module, "get_agent_manager", lambda _hass: manager)
    captured: dict[str, Any] = {}

    async def async_converse(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return _result("Готово")

    monkeypatch.setattr(conversation_stub, "async_converse", async_converse)
    router_module.register_conversation_router(hass)
    user_input = _input()

    speech = asyncio.run(manager.calls[0]["trigger_callback"](user_input, object()))

    assert speech == "Готово"
    assert captured == {
        "hass": hass,
        "text": user_input.text,
        "conversation_id": user_input.conversation_id,
        "context": user_input.context,
        "language": user_input.language,
        "agent_id": user_input.agent_id,
        "device_id": user_input.device_id,
        "satellite_id": user_input.satellite_id,
        "extra_system_prompt": user_input.extra_system_prompt,
    }


def test_router_fails_closed_without_device(monkeypatch: pytest.MonkeyPatch) -> None:
    hass = types.SimpleNamespace(data={})
    manager = _FakeAgentManager()
    monkeypatch.setattr(router_module, "get_agent_manager", lambda _hass: manager)
    called = False

    async def async_converse(**_kwargs: Any) -> Any:
        nonlocal called
        called = True
        return _result("unexpected")

    monkeypatch.setattr(conversation_stub, "async_converse", async_converse)
    router_module.register_conversation_router(hass)

    speech = asyncio.run(
        manager.calls[0]["trigger_callback"](_input(device_id=None), object())
    )

    assert "устройство" in speech
    assert called is False


def test_router_fails_closed_without_satellite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = types.SimpleNamespace(data={})
    manager = _FakeAgentManager()
    monkeypatch.setattr(router_module, "get_agent_manager", lambda _hass: manager)
    called = False

    async def async_converse(**_kwargs: Any) -> Any:
        nonlocal called
        called = True
        return _result("unexpected")

    monkeypatch.setattr(conversation_stub, "async_converse", async_converse)
    router_module.register_conversation_router(hass)
    user_input = _input()
    user_input.satellite_id = None

    speech = asyncio.run(
        manager.calls[0]["trigger_callback"](user_input, object())
    )

    assert "Assist Satellite" in speech
    assert called is False


def test_router_returns_error_when_conversation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = types.SimpleNamespace(data={})
    manager = _FakeAgentManager()
    monkeypatch.setattr(router_module, "get_agent_manager", lambda _hass: manager)

    async def async_converse(**_kwargs: Any) -> Any:
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(conversation_stub, "async_converse", async_converse)
    router_module.register_conversation_router(hass)

    speech = asyncio.run(manager.calls[0]["trigger_callback"](_input(), object()))

    assert "LLM" in speech


def test_router_returns_error_for_empty_conversation_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = types.SimpleNamespace(data={})
    manager = _FakeAgentManager()
    monkeypatch.setattr(router_module, "get_agent_manager", lambda _hass: manager)

    async def async_converse(**_kwargs: Any) -> Any:
        return _result("  ")

    monkeypatch.setattr(conversation_stub, "async_converse", async_converse)
    router_module.register_conversation_router(hass)

    speech = asyncio.run(manager.calls[0]["trigger_callback"](_input(), object()))

    assert "LLM" in speech


def test_router_keeps_concurrent_requests_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = types.SimpleNamespace(data={})
    manager = _FakeAgentManager()
    monkeypatch.setattr(router_module, "get_agent_manager", lambda _hass: manager)
    captured_devices: list[str] = []

    async def async_converse(**kwargs: Any) -> Any:
        await asyncio.sleep(0)
        captured_devices.append(kwargs["device_id"])
        return _result(kwargs["device_id"])

    monkeypatch.setattr(conversation_stub, "async_converse", async_converse)
    router_module.register_conversation_router(hass)
    callback = manager.calls[0]["trigger_callback"]

    async def run() -> list[str]:
        return await asyncio.gather(
            callback(_input(device_id="device-kitchen"), object()),
            callback(_input(device_id="device-office"), object()),
        )

    speeches = asyncio.run(run())

    assert set(speeches) == {"device-kitchen", "device-office"}
    assert captured_devices == ["device-kitchen", "device-office"]
