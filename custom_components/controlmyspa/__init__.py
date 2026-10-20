"""The ControlMySpa integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ControlMySpaApi
from .const import PLATFORMS
from .coordinator import ControlMySpaCoordinator

type ControlMySpaConfigEntry = ConfigEntry[ControlMySpaCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ControlMySpaConfigEntry) -> bool:
    """Set up ControlMySpa from a config entry."""
    api = ControlMySpaApi(
        async_get_clientsession(hass),
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
    )
    coordinator = ControlMySpaCoordinator(hass, api, entry)

    # Logs in on the first request; bad credentials start a reauth flow
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ControlMySpaConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: ControlMySpaConfigEntry
) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
