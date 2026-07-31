from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PROMPT_DATA_KEY
from .llm_diagnostics import async_log_runtime_layout, log_hass_component_state
from .manager import ReminderManager
from .prompt_loader import PromptCatalog, load_prompt_catalog

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the LLM Reminders integration."""
    _LOGGER.info("async_setup called for LLM Reminders: module=%s", __file__)
    await async_log_runtime_layout(hass)
    log_hass_component_state(hass, "async_setup")
    try:
        prompt_catalog: PromptCatalog = await hass.async_add_executor_job(
            load_prompt_catalog
        )
    except (OSError, ValueError):
        _LOGGER.exception("Unable to load the LLM Reminders prompt catalog")
        return False

    hass.data[PROMPT_DATA_KEY] = prompt_catalog
    _LOGGER.info(
        "LLM Reminders prompt catalog loaded: languages=%s base_length=%d",
        sorted(prompt_catalog.language_additions),
        len(prompt_catalog.base),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LLM Reminders from a config entry."""
    _LOGGER.info(
        "async_setup_entry called for LLM Reminders: entry_id=%s "
        "data_keys=%s option_keys=%s",
        entry.entry_id,
        sorted(entry.data),
        sorted(entry.options),
    )
    await async_log_runtime_layout(hass)
    log_hass_component_state(hass, "async_setup_entry before manager")
    options = {**entry.data, **entry.options}
    manager = ReminderManager(hass, options)
    try:
        await manager.async_load()
        _LOGGER.info(
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
    _LOGGER.info(
        "LLM Reminders manager registered: hass.data[%s] entry_ids=%s "
        "manager_type=%s",
        DOMAIN,
        list(managers),
        type(manager).__name__,
    )
    log_hass_component_state(hass, "async_setup_entry after manager")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload LLM Reminders."""
    _LOGGER.info(
        "async_unload_entry called for LLM Reminders: entry_id=%s",
        entry.entry_id,
    )
    manager: ReminderManager | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if manager is None:
        _LOGGER.warning(
            "LLM Reminders unload requested, but no manager was registered: entry_id=%s",
            entry.entry_id,
        )
        return True
    await manager.async_stop()
    _LOGGER.info(
        "LLM Reminders manager unloaded: entry_id=%s",
        entry.entry_id,
    )
    log_hass_component_state(hass, "async_unload_entry after manager")
    return True
