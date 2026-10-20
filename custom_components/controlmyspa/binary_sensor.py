"""Binary sensor platform for ControlMySpa."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ControlMySpaConfigEntry
from .api import COMPONENT_FILTER, COMPONENT_OZONE, is_active
from .coordinator import ControlMySpaCoordinator
from .entity import (
    ControlMySpaComponentEntity,
    ControlMySpaEntity,
    component_ports,
    port_label,
)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ControlMySpaBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a ControlMySpa status flag."""

    value_fn: Callable[[dict[str, Any]], bool]


STATUS_SENSORS: tuple[ControlMySpaBinarySensorDescription, ...] = (
    ControlMySpaBinarySensorDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda state: bool(state.get("online")),
    ),
    ControlMySpaBinarySensorDescription(
        key="ethernet",
        translation_key="ethernet",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: bool(state.get("ethernetPluggedIn")),
    ),
    ControlMySpaBinarySensorDescription(
        key="rs485",
        translation_key="rs485",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: bool(state.get("rs485ConnectionActive")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ControlMySpaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        ControlMySpaStatusSensor(coordinator, description)
        for description in STATUS_SENSORS
    ]
    for component_type, translation_key in (
        (COMPONENT_OZONE, "ozone"),
        (COMPONENT_FILTER, "filter"),
    ):
        entities.extend(
            ControlMySpaRunningSensor(coordinator, component_type, port, translation_key)
            for port in component_ports(coordinator, component_type)
        )
    async_add_entities(entities)


class ControlMySpaStatusSensor(ControlMySpaEntity, BinarySensorEntity):
    """A spa connectivity flag."""

    entity_description: ControlMySpaBinarySensorDescription
    _requires_online = False

    def __init__(
        self,
        coordinator: ControlMySpaCoordinator,
        description: ControlMySpaBinarySensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the flag."""
        return self.entity_description.value_fn(self.coordinator.state)


class ControlMySpaRunningSensor(ControlMySpaComponentEntity, BinarySensorEntity):
    """Whether the ozone generator or a filter cycle is running."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _requires_online = False

    def __init__(
        self,
        coordinator: ControlMySpaCoordinator,
        component_type: str,
        port: str | None,
        translation_key: str,
    ) -> None:
        """Initialize the sensor."""
        key = (
            translation_key
            if component_type == COMPONENT_OZONE
            else f"{translation_key}_{port_label(port)}"
        )
        super().__init__(coordinator, component_type, port, key)
        self._attr_translation_key = translation_key
        self._attr_translation_placeholders = {"number": str(port_label(port))}

    @property
    def is_on(self) -> bool:
        """Return True if running."""
        return is_active(self.component_state)
