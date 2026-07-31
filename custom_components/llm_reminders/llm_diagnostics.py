"""Diagnostics for the Home Assistant LLM platform integration."""

from __future__ import annotations

import json
import logging
from functools import partial
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_INTEGRATION_DIR = Path(__file__).resolve().parent


async def async_log_runtime_layout(hass: HomeAssistant) -> None:
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


def log_hass_component_state(hass: HomeAssistant, phase: str) -> None:
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


def log_loader_state(
    hass: HomeAssistant,
    phase: str,
    llm_platform: Any,
) -> None:
    """Log state of the Home Assistant LLM platform loader."""
    config = getattr(hass, "config", None)
    components = getattr(config, "components", None)
    top_level_components = getattr(config, "top_level_components", None)
    loader_key = getattr(llm_platform, "DATA_PLATFORMS", "llm_platforms")
    loader = hass.data.get(loader_key)
    processed = getattr(loader, "_processed", None)
    _LOGGER.info(
        "LLM Reminders LLM loader state: phase=%s loader_key=%s "
        "loader_type=%s loader_initialized=%s processed_domains=%s "
        "hass_data_keys=%s config_components=%s top_level_components=%s "
        "reminder_data_type=%s reminder_entry_ids=%s",
        phase,
        loader_key,
        type(loader).__name__ if loader is not None else None,
        loader is not None,
        sorted(str(domain) for domain in processed)
        if isinstance(processed, dict)
        else None,
        sorted(str(key) for key in hass.data),
        sorted(str(component) for component in components)
        if components is not None
        else None,
        sorted(str(component) for component in top_level_components)
        if top_level_components is not None
        else None,
        type(hass.data.get(DOMAIN)).__name__
        if DOMAIN in hass.data
        else None,
        list(hass.data[DOMAIN])
        if isinstance(hass.data.get(DOMAIN), dict)
        else None,
    )
