"""DataUpdateCoordinator for ControlMySpa."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ControlMySpaApi, ControlMySpaAuthError, ControlMySpaError
from .const import (
    COMMAND_REFRESH_DELAY,
    CONF_POLL_INTERVAL,
    CONF_SPA_ID,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    LOGGER_NAME,
)

if TYPE_CHECKING:
    from . import ControlMySpaConfigEntry

_LOGGER = logging.getLogger(LOGGER_NAME)


class ControlMySpaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls one spa and sends its commands."""

    config_entry: ControlMySpaConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        api: ControlMySpaApi,
        config_entry: ControlMySpaConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.spa_id: str = config_entry.data[CONF_SPA_ID]
        poll_interval = config_entry.options.get(
            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
            config_entry=config_entry,
        )

    @property
    def state(self) -> dict[str, Any]:
        """Return the spa's currentState block."""
        return (self.data or {}).get("currentState") or {}

    def get_component(
        self, component_type: str, port: str | None = None
    ) -> dict[str, Any] | None:
        """Return the first component of a type (and port, if given)."""
        for component in self.state.get("components") or []:
            if component.get("componentType") != component_type:
                continue
            if port is not None and str(component.get("port")) != str(port):
                continue
            return component
        return None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the latest spa data."""
        try:
            return await self.api.async_get_spa(self.spa_id)
        except ControlMySpaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ControlMySpaError as err:
            raise UpdateFailed(str(err)) from err

    async def async_send_command(self, command: Awaitable[None]) -> None:
        """Run a command, then refresh once the spa has had time to report back."""
        try:
            await command
        except ControlMySpaAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(f"ControlMySpa login failed: {err}") from err
        except ControlMySpaError as err:
            raise HomeAssistantError(f"ControlMySpa command failed: {err}") from err
        await asyncio.sleep(COMMAND_REFRESH_DELAY)
        await self.async_request_refresh()
