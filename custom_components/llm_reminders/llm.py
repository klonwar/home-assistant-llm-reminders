"""Home Assistant LLM platform for LLM Reminders."""

from __future__ import annotations

import logging
from pathlib import Path

_LOGGER = logging.getLogger(__name__)
_MODULE_PATH = Path(__file__).resolve()

try:
    from homeassistant.core import HomeAssistant, callback
    from homeassistant.helpers.llm import LLMContext

    from .const import PROMPT_DATA_KEY
    from .llm_diagnostics import log_loader_state
    from .prompt_loader import build_prompt
except Exception:
    _LOGGER.exception(
        "LLM Reminders LLM platform module dependency import failed: file=%s",
        _MODULE_PATH,
    )
    raise

try:
    from homeassistant.components import llm
except Exception:
    _LOGGER.exception(
        "Failed to import the Home Assistant LLM platform for LLM Reminders"
    )
    raise

try:
    from .llm_tools import build_tools, get_manager
except Exception:
    _LOGGER.exception(
        "LLM Reminders LLM tool module import failed: file=%s",
        _MODULE_PATH,
    )
    raise
else:
    _LOGGER.info(
        "Home Assistant LLM platform imported for LLM Reminders: "
        "module=%s llm_module=%s",
        _MODULE_PATH,
        getattr(llm, "__file__", None),
    )


@callback
def async_get_tools(
    hass: HomeAssistant,
    llm_context: LLMContext,
    api_id: str,
) -> llm.LLMTools | None:
    """Return reminder tools for the selected Home Assistant LLM API."""
    _LOGGER.info(
        "async_get_tools called for LLM Reminders: api_id=%s language=%s",
        api_id,
        getattr(llm_context, "language", None),
    )
    _LOGGER.debug(
        "LLM Reminders LLM context: api_id=%s platform=%s assistant=%s "
        "device_id=%s",
        api_id,
        getattr(llm_context, "platform", None),
        getattr(llm_context, "assistant", None),
        getattr(llm_context, "device_id", None),
    )
    log_loader_state(hass, "async_get_tools before manager lookup", llm)
    manager = get_manager(hass)
    if manager is None:
        _LOGGER.debug(
            "async_get_tools returning None: no LLM Reminders manager for api_id=%s",
            api_id,
        )
        return None

    prompt_catalog = hass.data.get(PROMPT_DATA_KEY)
    if prompt_catalog is None:
        _LOGGER.error(
            "LLM Reminders prompt catalog is not loaded; returning tools without "
            "the integration prompt: api_id=%s",
            api_id,
        )
        prompt = None
    else:
        prompt = build_prompt(prompt_catalog, llm_context.language)
        _LOGGER.debug(
            "LLM Reminders prompt selected: api_id=%s language=%s prompt_length=%d",
            api_id,
            llm_context.language,
            len(prompt),
        )

    tools = build_tools()
    try:
        result = llm.LLMTools(tools=tools, prompt=prompt)
    except Exception:
        _LOGGER.exception(
            "async_get_tools failed while constructing LLMTools: api_id=%s "
            "tool_names=%s",
            api_id,
            [tool.name for tool in tools],
        )
        raise

    _LOGGER.info(
        "async_get_tools returning LLM Reminders tools: api_id=%s tool_names=%s",
        api_id,
        [tool.name for tool in tools],
    )
    return result
