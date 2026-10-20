"""Select platform for ControlMySpa: heater mode, range and multi-speed pumps."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ControlMySpaConfigEntry
from .api import (
    COMPONENT_BLOWER,
    COMPONENT_PUMP,
    HEATER_MODES,
    TEMP_RANGES,
    is_active,
    normalize_state,
)
from .coordinator import ControlMySpaCoordinator
from .entity import (
    ControlMySpaComponentEntity,
    ControlMySpaEntity,
    component_ports,
    port_label,
)

PARALLEL_UPDATES = 1


def multi_speed(coordinator: ControlMySpaCoordinator, component_type: str, port) -> bool:
    """Return True if a component has more than one 'on' speed."""
    component = coordinator.get_component(component_type, port) or {}
    values = {
        normalize_state(value, component_type)
        for value in component.get("availableValues") or []
    }
    return len({value for value in values if is_active(value)}) > 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ControlMySpaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up selects."""
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = [
        ControlMySpaHeaterModeSelect(coordinator),
        ControlMySpaTempRangeSelect(coordinator),
    ]
    for component_type, translation_key in (
        (COMPONENT_PUMP, "pump"),
        (COMPONENT_BLOWER, "blower"),
    ):
        for port in component_ports(coordinator, component_type):
            if multi_speed(coordinator, component_type, port):
                entities.append(
                    ControlMySpaSpeedSelect(
                        coordinator, component_type, port, translation_key
                    )
                )
    async_add_entities(entities)


class ControlMySpaHeaterModeSelect(ControlMySpaEntity, SelectEntity):
    """Ready / Rest / Ready-in-Rest."""

    _attr_translation_key = "heater_mode"
    _attr_options = [mode.lower() for mode in HEATER_MODES]

    def __init__(self, coordinator: ControlMySpaCoordinator) -> None:
        """Initialize the select."""
        super().__init__(coordinator, "heater_mode")

    @property
    def current_option(self) -> str | None:
        """Return the current heater mode."""
        mode = str(self.coordinator.state.get("heaterMode") or "").lower()
        return mode if mode in self.options else None

    async def async_select_option(self, option: str) -> None:
        """Change the heater mode."""
        await self.coordinator.async_send_command(
            self.coordinator.api.async_set_heater_mode(
                self.coordinator.spa_id, option.upper()
            )
        )


class ControlMySpaTempRangeSelect(ControlMySpaEntity, SelectEntity):
    """High / Low temperature range."""

    _attr_translation_key = "temperature_range"
    _attr_options = [temp_range.lower() for temp_range in TEMP_RANGES]

    def __init__(self, coordinator: ControlMySpaCoordinator) -> None:
        """Initialize the select."""
        super().__init__(coordinator, "temperature_range")

    @property
    def current_option(self) -> str | None:
        """Return the current range."""
        temp_range = str(self.coordinator.state.get("tempRange") or "").lower()
        return temp_range if temp_range in self.options else None

    async def async_select_option(self, option: str) -> None:
        """Change the range."""
        await self.coordinator.async_send_command(
            self.coordinator.api.async_set_temperature_range(
                self.coordinator.spa_id, option.upper()
            )
        )


class ControlMySpaSpeedSelect(ControlMySpaComponentEntity, SelectEntity):
    """Off / Low / High for a multi-speed pump or blower."""

    def __init__(
        self,
        coordinator: ControlMySpaCoordinator,
        component_type: str,
        port: str | None,
        translation_key: str,
    ) -> None:
        """Initialize the select."""
        super().__init__(
            coordinator, component_type, port, f"{translation_key}_{port_label(port)}"
        )
        self._attr_translation_key = translation_key
        self._attr_translation_placeholders = {"number": str(port_label(port))}

    @property
    def options(self) -> list[str]:
        """Return the speeds this component supports."""
        return [state.lower() for state in self.available_states]

    @property
    def current_option(self) -> str | None:
        """Return the current speed."""
        state = self.component_state.lower()
        return state if state in self.options else None

    async def async_select_option(self, option: str) -> None:
        """Change the speed."""
        await self.coordinator.async_send_command(
            self.coordinator.api.async_set_component_state(
                self.coordinator.spa_id, self._component_type, self._port, option.upper()
            )
        )
