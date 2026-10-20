"""Diagnostics support for ControlMySpa."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from . import ControlMySpaConfigEntry

TO_REDACT = {
    CONF_EMAIL,
    CONF_PASSWORD,
    "access_token",
    "refresh_token",
    "accessToken",
    "refreshToken",
    "token",
    "secret",
    "api_key",
    "password",
    "ownerEmail",
    "ownerName",
    "ownerId",
    "activatorEmail",
    "dealerName",
    "address",
    "phone",
    "ipAddress",
    "regKey",
    "serialNumber",
    "spaSerialNumber",
    "spaOwnerId",
    "lastMqttMessages",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ControlMySpaConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "last_update_success": coordinator.last_update_success,
        "last_exception": (
            str(coordinator.last_exception) if coordinator.last_exception else None
        ),
        "spa": async_redact_data(coordinator.data or {}, TO_REDACT),
    }
