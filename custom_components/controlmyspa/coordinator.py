"""DataUpdateCoordinator for ControlMySpa."""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ControlMySpaApi, ControlMySpaAuthError, ControlMySpaError
from .const import (
    COMMAND_REFRESH_DELAYS,
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
        self._spa_record: dict[str, Any] | None = None
        self._pending_refreshes: list[CALLBACK_TYPE] = []
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
        """Fetch the latest spa data.

        Returns the spa record with its currentState replaced by the live
        state. The record's own currentState is a stale snapshot.
        """
        try:
            if self._spa_record is None:
                self._spa_record = await self.api.async_get_spa(self.spa_id)
            state = await self.api.async_get_current_state(self.spa_id)
        except ControlMySpaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ControlMySpaError as err:
            raise UpdateFailed(str(err)) from err
        return {**self._spa_record, "currentState": state}

    async def async_send_command(
        self,
        command: Awaitable[None],
        expected_state: dict[str, Any] | None = None,
    ) -> None:
        """Run a command, then re-read state a few times as the spa reports back.

        expected_state, if given, is merged into currentState right away so
        the UI shows the change before the spa confirms it. The follow-up
        refreshes correct it if the spa did not act on the command.
        """
        try:
            await command
        except ControlMySpaAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(f"ControlMySpa login failed: {err}") from err
        except ControlMySpaError as err:
            raise HomeAssistantError(f"ControlMySpa command failed: {err}") from err
        if expected_state and self.data:
            self.async_set_updated_data(
                {**self.data, "currentState": {**self.state, **expected_state}}
            )
        self._schedule_command_refreshes()

    def _schedule_command_refreshes(self) -> None:
        """Refresh at each COMMAND_REFRESH_DELAYS mark, replacing earlier ones."""
        for cancel in self._pending_refreshes:
            cancel()
        self._pending_refreshes = [
            async_call_later(self.hass, delay, self._async_command_refresh)
            for delay in COMMAND_REFRESH_DELAYS
        ]

    async def _async_command_refresh(self, _now: datetime) -> None:
        """Run one post-command refresh."""
        await self.async_refresh()

    async def async_shutdown(self) -> None:
        """Cancel pending post-command refreshes."""
        for cancel in self._pending_refreshes:
            cancel()
        self._pending_refreshes = []
        await super().async_shutdown()
