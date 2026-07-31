from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .manager import ReminderManager

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the LLM Reminders integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LLM Reminders from a config entry."""
    _LOGGER.info(
        "async_setup_entry called for LLM Reminders: entry_id=%s",
        entry.entry_id,
    )
    options = {**entry.data, **entry.options}
    manager = ReminderManager(hass, options)
    await manager.async_load()
    await manager.async_start()
    managers = hass.data.setdefault(DOMAIN, {})
    managers[entry.entry_id] = manager
    _LOGGER.info(
        "LLM Reminders manager registered: hass.data[%s] entry_ids=%s",
        DOMAIN,
        list(managers),
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload LLM Reminders."""
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
    return True
