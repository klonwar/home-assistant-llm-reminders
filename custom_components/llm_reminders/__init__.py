from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .manager import ReminderManager


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the LLM Reminders integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LLM Reminders from a config entry."""
    options = {**entry.data, **entry.options}
    manager = ReminderManager(hass, options)
    await manager.async_load()
    await manager.async_start()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload LLM Reminders."""
    manager: ReminderManager | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if manager is None:
        return True
    await manager.async_stop()
    return True
