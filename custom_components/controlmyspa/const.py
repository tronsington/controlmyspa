"""Constants for the ControlMySpa integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "controlmyspa"

# Configuration keys
CONF_SPA_ID: Final = "spa_id"
CONF_POLL_INTERVAL: Final = "poll_interval"

# Default values
DEFAULT_POLL_INTERVAL: Final = 60
MIN_POLL_INTERVAL: Final = 15
MAX_POLL_INTERVAL: Final = 3600

# Seconds after a command at which state is re-read. The spa reports the
# change back to the cloud a few seconds after it acts on it.
COMMAND_REFRESH_DELAYS: Final = (3, 10, 25)

MANUFACTURER: Final = "Balboa Water Group"

PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.LIGHT,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

LOGGER_NAME: Final = f"custom_components.{DOMAIN}"
