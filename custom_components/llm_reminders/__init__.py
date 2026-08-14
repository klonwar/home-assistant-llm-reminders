from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PROMPT_DATA_KEY
from .conversation_router import (
    register_conversation_router,
    unregister_conversation_router,
)
from .llm_diagnostics import async_log_runtime_layout
from .manager import ReminderManager
from .prompt_loader import PromptCatalog, load_prompt_catalog

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the LLM Reminders integration."""
    _LOGGER.debug("async_setup called for LLM Reminders: module=%s", __file__)
    await async_log_runtime_layout(hass)
    try:
        prompt_catalog: PromptCatalog = await hass.async_add_executor_job(
            load_prompt_catalog
        )
    except (OSError, ValueError):
        _LOGGER.exception("Unable to load the LLM Reminders prompt catalog")
        return False

    hass.data[PROMPT_DATA_KEY] = prompt_catalog
    _LOGGER.info(
        "LLM Reminders prompt catalog loaded: languages=%s",
        sorted(prompt_catalog.language_additions),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LLM Reminders from a config entry."""
    _LOGGER.debug(
        "async_setup_entry called for LLM Reminders: entry_id=%s "
        "data_keys=%s option_keys=%s",
        entry.entry_id,
        sorted(entry.data),
        sorted(entry.options),
    )
    await async_log_runtime_layout(hass)
    options = {**entry.data, **entry.options}
    manager = ReminderManager(hass, options)
    try:
        await manager.async_load()
        _LOGGER.debug(
            "LLM Reminders manager storage loaded: entry_id=%s manager_type=%s",
            entry.entry_id,
            type(manager).__name__,
        )
        await manager.async_start()
    except Exception:
        _LOGGER.exception(
            "LLM Reminders manager startup failed: entry_id=%s",
            entry.entry_id,
        )
        raise
    managers = hass.data.setdefault(DOMAIN, {})
    managers[entry.entry_id] = manager
    try:
        register_conversation_router(hass)
    except Exception:
        managers.pop(entry.entry_id, None)
        await manager.async_stop()
        _LOGGER.exception(
            "LLM Reminders conversation router startup failed: entry_id=%s",
            entry.entry_id,
        )
        raise
    _LOGGER.debug(
        "LLM Reminders manager registered: hass.data[%s] entry_ids=%s "
        "manager_type=%s",
        DOMAIN,
        list(managers),
        type(manager).__name__,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload LLM Reminders."""
    _LOGGER.info(
        "async_unload_entry called for LLM Reminders: entry_id=%s",
        entry.entry_id,
    )
    managers = hass.data.get(DOMAIN, {})
    manager: ReminderManager | None = managers.pop(entry.entry_id, None)
    if manager is None:
        if not managers:
            unregister_conversation_router(hass)
        _LOGGER.warning(
            "LLM Reminders unload requested, but no manager was registered: entry_id=%s",
            entry.entry_id,
        )
        return True
    if not hass.data.get(DOMAIN):
        unregister_conversation_router(hass)
    await manager.async_stop()
    _LOGGER.info(
        "LLM Reminders manager unloaded: entry_id=%s",
        entry.entry_id,
    )
    return True
