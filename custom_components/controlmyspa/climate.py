"""Climate platform for ControlMySpa: the water thermostat."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.unit_conversion import TemperatureConverter

from . import ControlMySpaConfigEntry
from .entity import ControlMySpaEntity

PARALLEL_UPDATES = 1

# Used when the spa does not report its setup limits
FALLBACK_LIMITS_F = {"HIGH": (80.0, 104.0), "LOW": (50.0, 99.0)}


def _as_float(value: Any) -> float | None:
    """Parse the API's string temperatures ("104.00")."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ControlMySpaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the thermostat."""
    async_add_entities([ControlMySpaClimate(entry.runtime_data)])


class ControlMySpaClimate(ControlMySpaEntity, ClimateEntity):
    """Thermostat for the spa water."""

    _attr_translation_key = "thermostat"
    _attr_name = None
    _attr_hvac_modes = [HVACMode.HEAT]
    _attr_hvac_mode = HVACMode.HEAT
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    def __init__(self, coordinator) -> None:
        """Initialize the thermostat."""
        super().__init__(coordinator, "thermostat")

    @property
    def _celsius(self) -> bool:
        return bool(self.coordinator.state.get("celsius"))

    @property
    def temperature_unit(self) -> str:
        """Return the unit the spa reports in."""
        return UnitOfTemperature.CELSIUS if self._celsius else UnitOfTemperature.FAHRENHEIT

    @property
    def target_temperature_step(self) -> float:
        """Match the portal: 1 degree F or 0.5 degree C."""
        return 0.5 if self._celsius else 1.0

    @property
    def current_temperature(self) -> float | None:
        """Return the water temperature."""
        return _as_float(self.coordinator.state.get("currentTemp"))

    @property
    def target_temperature(self) -> float | None:
        """Return the set point."""
        return _as_float(self.coordinator.state.get("desiredTemp"))

    def _limits_f(self) -> tuple[float, float]:
        """Return (min, max) in Fahrenheit for the active temperature range."""
        temp_range = str(self.coordinator.state.get("tempRange") or "HIGH").upper()
        params = self.coordinator.state.get("setupParams") or {}
        prefix = "lowRange" if temp_range == "LOW" else "highRange"
        low = _as_float(params.get(f"{prefix}Low"))
        high = _as_float(params.get(f"{prefix}High"))
        fallback = FALLBACK_LIMITS_F.get(temp_range, FALLBACK_LIMITS_F["HIGH"])
        return (low or fallback[0], high or fallback[1])

    def _from_f(self, value: float) -> float:
        if not self._celsius:
            return value
        return round(
            TemperatureConverter.convert(
                value, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
            )
            * 2
        ) / 2

    @property
    def min_temp(self) -> float:
        """Return the lowest settable temperature."""
        return self._from_f(self._limits_f()[0])

    @property
    def max_temp(self) -> float:
        """Return the highest settable temperature."""
        return self._from_f(self._limits_f()[1])

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature."""
        target = kwargs.get(ATTR_TEMPERATURE)
        if target is None:
            return
        fahrenheit = float(target)
        if self._celsius:
            # The portal converts Celsius to Fahrenheit before sending
            fahrenheit = round(
                TemperatureConverter.convert(
                    fahrenheit, UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT
                )
            )
        low, high = self._limits_f()
        fahrenheit = int(min(max(fahrenheit, low), high))
        await self.coordinator.async_send_command(
            self.coordinator.api.async_set_temperature(
                self.coordinator.spa_id, fahrenheit
            ),
            expected_state={"desiredTemp": f"{self._from_f(fahrenheit):.2f}"},
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Only heat is supported; nothing to change."""
