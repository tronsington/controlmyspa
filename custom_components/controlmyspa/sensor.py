"""Sensor platform for ControlMySpa."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ControlMySpaConfigEntry
from .coordinator import ControlMySpaCoordinator
from .entity import ControlMySpaEntity

PARALLEL_UPDATES = 0


def _temp(key: str) -> Callable[[dict[str, Any]], float | None]:
    def read(state: dict[str, Any]) -> float | None:
        try:
            return float(state.get(key))
        except (TypeError, ValueError):
            return None

    return read


@dataclass(frozen=True, kw_only=True)
class ControlMySpaSensorDescription(SensorEntityDescription):
    """Describes a ControlMySpa sensor."""

    value_fn: Callable[[dict[str, Any]], Any]
    temperature: bool = False


SENSORS: tuple[ControlMySpaSensorDescription, ...] = (
    ControlMySpaSensorDescription(
        key="current_temperature",
        translation_key="current_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        temperature=True,
        value_fn=_temp("currentTemp"),
    ),
    ControlMySpaSensorDescription(
        key="set_point",
        translation_key="set_point",
        device_class=SensorDeviceClass.TEMPERATURE,
        temperature=True,
        value_fn=_temp("desiredTemp"),
    ),
    ControlMySpaSensorDescription(
        key="run_mode",
        translation_key="run_mode",
        value_fn=lambda state: state.get("runMode"),
    ),
    ControlMySpaSensorDescription(
        key="controller_version",
        translation_key="controller_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: (state.get("systemInfo") or {}).get(
            "controllerSoftwareVersion"
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ControlMySpaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        ControlMySpaSensor(coordinator, description) for description in SENSORS
    )


class ControlMySpaSensor(ControlMySpaEntity, SensorEntity):
    """A read-only spa value."""

    entity_description: ControlMySpaSensorDescription
    _requires_online = False

    def __init__(
        self,
        coordinator: ControlMySpaCoordinator,
        description: ControlMySpaSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the spa's temperature unit for temperature sensors."""
        if not self.entity_description.temperature:
            return None
        if self.coordinator.state.get("celsius"):
            return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @property
    def native_value(self) -> Any:
        """Return the value."""
        return self.entity_description.value_fn(self.coordinator.state)
