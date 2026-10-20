"""Switch platform for ControlMySpa: single-speed pumps, blowers and panel lock."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ControlMySpaConfigEntry
from .api import COMPONENT_BLOWER, COMPONENT_PUMP, STATE_OFF, is_active
from .coordinator import ControlMySpaCoordinator
from .entity import (
    ControlMySpaComponentEntity,
    ControlMySpaEntity,
    component_ports,
    port_label,
)
from .select import multi_speed

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ControlMySpaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [ControlMySpaPanelLockSwitch(coordinator)]
    for component_type, translation_key in (
        (COMPONENT_PUMP, "pump"),
        (COMPONENT_BLOWER, "blower"),
    ):
        for port in component_ports(coordinator, component_type):
            # Multi-speed components get a select instead (see select.py)
            if not multi_speed(coordinator, component_type, port):
                entities.append(
                    ControlMySpaComponentSwitch(
                        coordinator, component_type, port, translation_key
                    )
                )
    async_add_entities(entities)


class ControlMySpaComponentSwitch(ControlMySpaComponentEntity, SwitchEntity):
    """On/off for a single-speed pump or blower."""

    def __init__(
        self,
        coordinator: ControlMySpaCoordinator,
        component_type: str,
        port: str | None,
        translation_key: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(
            coordinator, component_type, port, f"{translation_key}_{port_label(port)}"
        )
        self._attr_translation_key = translation_key
        self._attr_translation_placeholders = {"number": str(port_label(port))}

    @property
    def is_on(self) -> bool:
        """Return True if running."""
        return is_active(self.component_state)

    async def _set(self, state: str) -> None:
        await self.coordinator.async_send_command(
            self.coordinator.api.async_set_component_state(
                self.coordinator.spa_id, self._component_type, self._port, state
            )
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on."""
        await self._set(self.on_state)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        await self._set(STATE_OFF)


class ControlMySpaPanelLockSwitch(ControlMySpaEntity, SwitchEntity):
    """Locks the spa's physical control panel."""

    _attr_translation_key = "panel_lock"

    def __init__(self, coordinator: ControlMySpaCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "panel_lock")

    @property
    def is_on(self) -> bool:
        """Return True if the panel is locked."""
        return bool(self.coordinator.state.get("panelLock"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Lock the panel."""
        await self.coordinator.async_send_command(
            self.coordinator.api.async_set_panel_lock(self.coordinator.spa_id, True)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unlock the panel."""
        await self.coordinator.async_send_command(
            self.coordinator.api.async_set_panel_lock(self.coordinator.spa_id, False)
        )
