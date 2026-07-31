from __future__ import annotations

import json
import logging
from functools import partial
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PROMPT_DATA_KEY
from .manager import ReminderManager
from .prompt_loader import PromptCatalog, load_prompt_catalog

_LOGGER = logging.getLogger(__name__)
_INTEGRATION_DIR = Path(__file__).resolve().parent


async def _log_runtime_layout(hass: HomeAssistant) -> None:
    """Log the files and version of the package loaded by Home Assistant."""
    manifest_path = _INTEGRATION_DIR / "manifest.json"
    llm_path = _INTEGRATION_DIR / "llm.py"
    version: str | None = None
    try:
        manifest_text = await hass.async_add_executor_job(
            partial(manifest_path.read_text, encoding="utf-8")
        )
        version = json.loads(manifest_text).get("version")
    except (OSError, ValueError, TypeError):
        _LOGGER.exception(
            "Unable to read the runtime manifest: path=%s",
            manifest_path,
        )

    _LOGGER.info(
        "LLM Reminders runtime package: module=%s integration_dir=%s "
        "manifest=%s manifest_exists=%s version=%s llm_platform=%s "
        "llm_platform_exists=%s",
        __file__,
        _INTEGRATION_DIR,
        manifest_path,
        manifest_path.is_file(),
        version,
        llm_path,
        llm_path.is_file(),
    )


def _log_hass_component_state(hass: HomeAssistant, phase: str) -> None:
    """Log Home Assistant component state relevant to lazy platform loading."""
    config = getattr(hass, "config", None)
    components = getattr(config, "components", None)
    top_level_components = getattr(config, "top_level_components", None)
    _LOGGER.info(
        "LLM Reminders HA component state: phase=%s hass_data_keys=%s "
        "config_components=%s top_level_components=%s",
        phase,
        sorted(str(key) for key in hass.data),
        sorted(str(component) for component in components)
        if components is not None
        else None,
        sorted(str(component) for component in top_level_components)
        if top_level_components is not None
        else None,
    )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the LLM Reminders integration."""
    _LOGGER.info("async_setup called for LLM Reminders: module=%s", __file__)
    await _log_runtime_layout(hass)
    _log_hass_component_state(hass, "async_setup")
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
    await _log_runtime_layout(hass)
    _log_hass_component_state(hass, "async_setup_entry before manager")
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
    _log_hass_component_state(hass, "async_setup_entry after manager")
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
    _log_hass_component_state(hass, "async_unload_entry after manager")
    return True
