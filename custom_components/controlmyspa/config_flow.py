"""Config flow for ControlMySpa.

The user signs in with their ControlMySpa email and password; the spa is
found from the account, so no spa ID or token is ever typed in.
"""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    ControlMySpaApi,
    ControlMySpaAuthError,
    ControlMySpaConnectionError,
    ControlMySpaError,
)
from .const import (
    CONF_POLL_INTERVAL,
    CONF_SPA_ID,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    LOGGER_NAME,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.PASSWORD, autocomplete="current-password"
            )
        ),
    }
)


def _spa_label(spa: dict[str, Any]) -> str:
    """Return a human-readable name for a spa in the picker."""
    parts = [spa.get("modelType"), spa.get("serialNumber")]
    label = " ".join(str(part) for part in parts if part)
    return label or str(spa.get("_id"))


class ControlMySpaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ControlMySpa."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._credentials: dict[str, str] = {}
        self._spas: list[dict[str, Any]] = []

    async def _async_validate(self, email: str, password: str) -> list[dict[str, Any]]:
        """Log in and return the account's spas."""
        api = ControlMySpaApi(async_get_clientsession(self.hass), email, password)
        await api.async_login()
        return await api.async_get_spas()

    async def _async_try_validate(
        self, user_input: dict[str, Any], errors: dict[str, str]
    ) -> list[dict[str, Any]] | None:
        """Run validation, filling errors on failure."""
        try:
            spas = await self._async_validate(
                user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
        except ControlMySpaAuthError:
            errors["base"] = "invalid_auth"
        except ControlMySpaConnectionError:
            errors["base"] = "cannot_connect"
        except ControlMySpaError:
            errors["base"] = "unknown"
        except Exception:
            _LOGGER.exception("Unexpected error validating ControlMySpa login")
            errors["base"] = "unknown"
        else:
            if not spas:
                errors["base"] = "no_spas"
                return None
            return spas
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for email and password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            spas = await self._async_try_validate(user_input, errors)
            if spas is not None:
                self._credentials = {
                    CONF_EMAIL: user_input[CONF_EMAIL].strip().lower(),
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                }
                self._spas = spas
                if len(spas) == 1:
                    return await self._async_create_for_spa(spas[0])
                return await self.async_step_spa()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_spa(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a spa when the account has more than one."""
        if user_input is not None:
            spa = next(
                spa for spa in self._spas if spa.get("_id") == user_input[CONF_SPA_ID]
            )
            return await self._async_create_for_spa(spa)

        options = [
            SelectOptionDict(value=str(spa["_id"]), label=_spa_label(spa))
            for spa in self._spas
        ]
        return self.async_show_form(
            step_id="spa",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SPA_ID): SelectSelector(
                        SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def _async_create_for_spa(self, spa: dict[str, Any]) -> ConfigFlowResult:
        """Create the entry for one spa."""
        spa_id = str(spa["_id"])
        await self.async_set_unique_id(spa_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"Hot Tub ({_spa_label(spa)})",
            data={**self._credentials, CONF_SPA_ID: spa_id},
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after the stored login stopped working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the password again."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            credentials = {
                CONF_EMAIL: entry.data[CONF_EMAIL],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            spas = await self._async_try_validate(credentials, errors)
            if spas is not None:
                if not any(spa.get("_id") == entry.data[CONF_SPA_ID] for spa in spas):
                    errors["base"] = "spa_not_found"
                else:
                    return self.async_update_reload_and_abort(
                        entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the email or password."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            spas = await self._async_try_validate(user_input, errors)
            if spas is not None:
                if not any(spa.get("_id") == entry.data[CONF_SPA_ID] for spa in spas):
                    errors["base"] = "spa_not_found"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={
                            CONF_EMAIL: user_input[CONF_EMAIL].strip().lower(),
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                        },
                    )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS_SCHEMA, {CONF_EMAIL: entry.data[CONF_EMAIL]}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return ControlMySpaOptionsFlow()


class ControlMySpaOptionsFlow(OptionsFlow):
    """Options: polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options form."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_POLL_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL),
                    ),
                }
            ),
        )
