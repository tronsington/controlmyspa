"""Light platform for ControlMySpa."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ControlMySpaConfigEntry
from .api import COMPONENT_LIGHT, STATE_OFF, is_active
from .coordinator import ControlMySpaCoordinator
from .entity import ControlMySpaComponentEntity, component_ports, port_label

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ControlMySpaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up lights."""
    coordinator = entry.runtime_data
    async_add_entities(
        ControlMySpaLight(coordinator, port)
        for port in component_ports(coordinator, COMPONENT_LIGHT)
    )


class ControlMySpaLight(ControlMySpaComponentEntity, LightEntity):
    """A spa light."""

    _attr_translation_key = "light"
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, coordinator: ControlMySpaCoordinator, port: str | None) -> None:
        """Initialize the light."""
        super().__init__(
            coordinator, COMPONENT_LIGHT, port, f"light_{port_label(port)}"
        )
        self._attr_translation_placeholders = {"number": str(port_label(port))}

    @property
    def is_on(self) -> bool:
        """Return True if lit."""
        return is_active(self.component_state)

    async def _set(self, state: str) -> None:
        await self.coordinator.async_send_command(
            self.coordinator.api.async_set_component_state(
                self.coordinator.spa_id, COMPONENT_LIGHT, self._port, state
            )
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on."""
        await self._set(self.on_state)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        await self._set(STATE_OFF)
