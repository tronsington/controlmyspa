"""Base entity for ControlMySpa."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import is_active, normalize_state
from .const import DOMAIN, MANUFACTURER
from .coordinator import ControlMySpaCoordinator


class ControlMySpaEntity(CoordinatorEntity[ControlMySpaCoordinator]):
    """Base entity tied to one spa."""

    _attr_has_entity_name = True

    # Controls need the spa online; status entities stay available regardless
    _requires_online = True

    def __init__(self, coordinator: ControlMySpaCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.spa_id}_{key}"
        data = coordinator.data or {}
        system_info = coordinator.state.get("systemInfo") or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.spa_id)},
            name="Hot Tub",
            manufacturer=MANUFACTURER,
            model=data.get("modelType"),
            sw_version=system_info.get("controllerSoftwareVersion"),
            serial_number=data.get("serialNumber"),
            configuration_url=(
                f"https://controlmyspa.com/portal/spas/{coordinator.spa_id}"
            ),
        )

    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        if not super().available or not self.coordinator.state:
            return False
        if self._requires_online:
            return bool(self.coordinator.state.get("online"))
        return True


class ControlMySpaComponentEntity(ControlMySpaEntity):
    """Entity backed by one entry in currentState.components."""

    def __init__(
        self,
        coordinator: ControlMySpaCoordinator,
        component_type: str,
        port: str | None,
        key: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, key)
        self._component_type = component_type
        self._port = port

    @property
    def component(self) -> dict[str, Any] | None:
        """Return the component's latest data."""
        return self.coordinator.get_component(self._component_type, self._port)

    @property
    def component_state(self) -> str:
        """Return the component's normalized state."""
        component = self.component
        return normalize_state(
            component.get("value") if component else None, self._component_type
        )

    @property
    def available_states(self) -> list[str]:
        """Return the states this component supports, DISABLED excluded."""
        component = self.component or {}
        states = [
            normalize_state(value, self._component_type)
            for value in component.get("availableValues") or []
        ]
        return [state for state in dict.fromkeys(states) if state != "DISABLED"]

    @property
    def on_state(self) -> str:
        """Return the state used to switch the component on (its highest)."""
        active = [state for state in self.available_states if is_active(state)]
        return active[-1] if active else "ON"

    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        return super().available and self.component is not None


def component_ports(
    coordinator: ControlMySpaCoordinator, component_type: str
) -> list[str | None]:
    """Return the ports of every component of a type, in port order."""
    ports = [
        component.get("port")
        for component in coordinator.state.get("components") or []
        if component.get("componentType") == component_type
    ]
    return sorted(ports, key=lambda port: -1 if port is None else int(port))


def port_label(port: str | None) -> int:
    """Return a 1-based number for a 0-based port, as the portal shows it."""
    return 1 if port is None else int(port) + 1
