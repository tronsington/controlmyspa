"""Constants for the ControlMySpa integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "controlmyspa"

# Configuration keys
CONF_SPA_ID: Final = "spa_id"
CONF_POLL_INTERVAL: Final = "poll_interval"

# Default values
DEFAULT_POLL_INTERVAL: Final = 180
MIN_POLL_INTERVAL: Final = 30
MAX_POLL_INTERVAL: Final = 3600

# Seconds to wait after a command before re-reading state, so the spa has
# time to report the change back to the cloud
COMMAND_REFRESH_DELAY: Final = 5

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
