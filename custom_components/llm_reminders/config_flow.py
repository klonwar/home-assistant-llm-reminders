from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_DEFAULT_SATELLITE, DOMAIN


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle configuration of LLM Reminders."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="LLM Reminders", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_DEFAULT_SATELLITE): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="assist_satellite")
                    )
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return LLMRemindersOptionsFlowHandler()


class LLMRemindersOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle LLM Reminders options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_DEFAULT_SATELLITE,
            self.config_entry.data.get(CONF_DEFAULT_SATELLITE),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DEFAULT_SATELLITE,
                        default=current,
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="assist_satellite")
                    )
                }
            ),
        )
