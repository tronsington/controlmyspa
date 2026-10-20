"""API client for ControlMySpa.

Standalone (no Home Assistant imports) so it can be tested on its own.

Auth model, taken from the controlmyspa.com web portal:
- POST /web/auth/login with {"email", "password"} returns
  data.accessToken and data.refreshToken.
- GET /web/auth/refresh with "Authorization: Bearer <refresh token>"
  returns a new pair.
- Access tokens last about 24 hours.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
import json
import logging
import time
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

API_BASE_URL = "https://iot.controlmyspa.com/web"
REQUEST_TIMEOUT = ClientTimeout(total=30)

# Refresh this many seconds before the access token actually expires
TOKEN_EXPIRY_MARGIN = 300

# Source the portal tags its commands with
COMMAND_VIA = "WEB"

# Component types as they appear in currentState.components
COMPONENT_PUMP = "PUMP"
COMPONENT_CIRCULATION_PUMP = "CIRCULATION_PUMP"
COMPONENT_LIGHT = "LIGHT"
COMPONENT_BLOWER = "BLOWER"
COMPONENT_MISTER = "MISTER"
COMPONENT_AUX = "AUX"
COMPONENT_OZONE = "OZONE"
COMPONENT_FILTER = "FILTER"

# Component type -> name the command endpoint expects
COMMAND_COMPONENT_TYPES: dict[str, str] = {
    COMPONENT_PUMP: "jet",
    COMPONENT_CIRCULATION_PUMP: "circ-pump",
    COMPONENT_LIGHT: "light",
    COMPONENT_BLOWER: "blower",
    COMPONENT_MISTER: "mister",
    COMPONENT_AUX: "aux",
    COMPONENT_OZONE: "ozone",
}

# Component types addressed by port number ("deviceNumber") in commands
NUMBERED_COMPONENT_TYPES = {
    COMPONENT_PUMP,
    COMPONENT_LIGHT,
    COMPONENT_BLOWER,
    COMPONENT_MISTER,
    COMPONENT_AUX,
}

STATE_OFF = "OFF"
STATE_ON = "ON"
STATE_LOW = "LOW"
STATE_MED = "MED"
STATE_HIGH = "HIGH"
STATE_DISABLED = "DISABLED"
KNOWN_STATES = {STATE_OFF, STATE_ON, STATE_LOW, STATE_MED, STATE_HIGH, STATE_DISABLED}

HEATER_MODES = ["READY", "REST", "READY_REST"]
TEMP_RANGES = ["HIGH", "LOW"]


class ControlMySpaError(Exception):
    """Base exception for ControlMySpa errors."""


class ControlMySpaAuthError(ControlMySpaError):
    """Credentials were rejected."""


class ControlMySpaConnectionError(ControlMySpaError):
    """The API could not be reached."""


class ControlMySpaCommandError(ControlMySpaError):
    """The API rejected a command."""


def normalize_state(value: Any, component_type: str) -> str:
    """Return a component value as one of KNOWN_STATES.

    Mirrors the portal: values can arrive as names ("LOW") or as numbers,
    where the number's meaning depends on the component type.
    """
    if value is None or value == "":
        return STATE_OFF
    if isinstance(value, str):
        text = value.strip()
        if not text.isdigit():
            upper = text.upper()
            return upper if upper in KNOWN_STATES else STATE_OFF
        value = int(text)
    if isinstance(value, (int, float)):
        number = int(value)
        if component_type in (COMPONENT_LIGHT, COMPONENT_BLOWER):
            levels = [STATE_OFF, STATE_LOW, STATE_MED, STATE_HIGH]
        elif component_type in (COMPONENT_PUMP, COMPONENT_CIRCULATION_PUMP):
            levels = [STATE_OFF, STATE_LOW, STATE_HIGH]
        else:
            levels = [STATE_OFF, STATE_ON]
        return levels[number] if 0 <= number < len(levels) else STATE_OFF
    return STATE_OFF


def is_active(state: str) -> bool:
    """Return True if a normalized state means the component is running."""
    return state not in (STATE_OFF, STATE_DISABLED)


def _token_expiry(token: str) -> float:
    """Read the exp claim from a JWT without verifying it. 0 if unreadable."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except (IndexError, KeyError, ValueError, TypeError):
        return 0


class ControlMySpaApi:
    """Client for the ControlMySpa cloud API."""

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        base_url: str = API_BASE_URL,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._email = email.strip().lower()
        self._password = password
        self._base_url = base_url
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._access_expiry: float = 0
        self._auth_lock = asyncio.Lock()
        self.on_tokens_updated: Callable[[], None] | None = None

    @property
    def access_token(self) -> str | None:
        """Return the current access token."""
        return self._access_token

    def _set_tokens(self, data: Any) -> None:
        """Store a token pair from a login or refresh response."""
        payload = data.get("data") if isinstance(data, dict) else None
        access = payload.get("accessToken") if isinstance(payload, dict) else None
        if not access:
            raise ControlMySpaAuthError("Response did not include an access token")
        self._access_token = access
        self._refresh_token = payload.get("refreshToken") or self._refresh_token
        self._access_expiry = _token_expiry(access)
        if self.on_tokens_updated:
            self.on_tokens_updated()

    async def _raw_request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        """Send one request and return (status, parsed body)."""
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with self._session.request(
                method,
                f"{self._base_url}{path}",
                json=body,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                try:
                    payload = await response.json(content_type=None)
                except ValueError:
                    payload = None
                return response.status, payload
        except (ClientError, asyncio.TimeoutError) as err:
            raise ControlMySpaConnectionError(
                f"Error talking to ControlMySpa: {type(err).__name__}"
            ) from err

    async def async_login(self) -> None:
        """Log in with email and password."""
        status, payload = await self._raw_request(
            "POST",
            "/auth/login",
            body={"email": self._email, "password": self._password},
        )
        if status in (400, 401, 403, 404):
            raise ControlMySpaAuthError("Email or password was rejected")
        if status == 409:
            # The portal shows a dialog here; the account needs attention
            # (for example new terms to accept) on controlmyspa.com
            raise ControlMySpaAuthError(
                "Login blocked, sign in at controlmyspa.com to resolve"
            )
        if status >= 400:
            raise ControlMySpaConnectionError(f"Login failed with HTTP {status}")
        self._set_tokens(payload)
        _LOGGER.debug("Logged in to ControlMySpa")

    async def _async_refresh(self) -> bool:
        """Swap the refresh token for a new pair. False if it was rejected."""
        if not self._refresh_token:
            return False
        status, payload = await self._raw_request(
            "GET", "/auth/refresh", token=self._refresh_token
        )
        if status >= 400:
            _LOGGER.debug("Token refresh rejected with HTTP %s", status)
            return False
        try:
            self._set_tokens(payload)
        except ControlMySpaAuthError:
            return False
        _LOGGER.debug("Refreshed ControlMySpa access token")
        return True

    async def _async_renew(self, rejected_token: str | None) -> None:
        """Get a working access token: refresh first, log in if that fails."""
        async with self._auth_lock:
            # Another request may already have renewed while we waited
            if self._access_token and self._access_token != rejected_token:
                if time.time() < self._access_expiry - TOKEN_EXPIRY_MARGIN:
                    return
            if not await self._async_refresh():
                await self.async_login()

    async def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        """Send an authenticated request, renewing the token if needed."""
        token = self._access_token
        if not token or (
            self._access_expiry
            and time.time() >= self._access_expiry - TOKEN_EXPIRY_MARGIN
        ):
            await self._async_renew(token)
            token = self._access_token

        status, payload = await self._raw_request(method, path, token=token, body=body)
        if status == 401:
            await self._async_renew(token)
            status, payload = await self._raw_request(
                method, path, token=self._access_token, body=body
            )
            if status == 401:
                raise ControlMySpaAuthError("Access token rejected after renewal")

        if status >= 400:
            message = payload.get("message") if isinstance(payload, dict) else None
            if method != "GET":
                raise ControlMySpaCommandError(
                    message or f"Command failed with HTTP {status}"
                )
            raise ControlMySpaConnectionError(
                message or f"Request failed with HTTP {status}"
            )
        return payload

    async def async_get_spas(self) -> list[dict[str, Any]]:
        """Return the spas linked to this account."""
        payload = await self._request("GET", "/spas")
        data = payload.get("data") if isinstance(payload, dict) else None
        spas = data.get("spas") if isinstance(data, dict) else None
        return spas if isinstance(spas, list) else []

    async def async_get_spa(self, spa_id: str) -> dict[str, Any]:
        """Return one spa, including its currentState."""
        payload = await self._request("GET", f"/spas/{spa_id}")
        if not isinstance(payload, dict) or "currentState" not in payload:
            raise ControlMySpaConnectionError("Spa response had no currentState")
        return payload

    async def _command(self, path: str, spa_id: str, **fields: Any) -> None:
        """Send a spa command."""
        body = {"spaId": spa_id, "via": COMMAND_VIA, **fields}
        await self._request("POST", f"/spa-commands{path}", body=body)

    async def async_set_component_state(
        self,
        spa_id: str,
        component_type: str,
        port: str | int | None,
        state: str,
    ) -> None:
        """Set a pump, light, blower or similar component to a state."""
        command_type = COMMAND_COMPONENT_TYPES.get(component_type)
        if command_type is None:
            raise ControlMySpaCommandError(f"{component_type} cannot be controlled")
        if state == STATE_DISABLED:
            state = STATE_OFF
        # The portal sends HIGH for single-speed jets
        if command_type == "jet" and state == STATE_ON:
            state = STATE_HIGH
        fields: dict[str, Any] = {"componentType": command_type, "state": state}
        if component_type in NUMBERED_COMPONENT_TYPES and port is not None:
            fields["deviceNumber"] = int(port)
        await self._command("/component-state", spa_id, **fields)

    async def async_set_temperature(self, spa_id: str, fahrenheit: float) -> None:
        """Set the desired water temperature, in Fahrenheit."""
        await self._command("/temperature/value", spa_id, value=fahrenheit)

    async def async_set_heater_mode(self, spa_id: str, mode: str) -> None:
        """Set the heater mode (READY, REST, READY_REST)."""
        if mode not in HEATER_MODES:
            raise ControlMySpaCommandError(f"Unknown heater mode {mode}")
        await self._command("/temperature/heater-mode", spa_id, mode=mode)

    async def async_set_temperature_range(self, spa_id: str, temp_range: str) -> None:
        """Set the temperature range (HIGH or LOW)."""
        if temp_range not in TEMP_RANGES:
            raise ControlMySpaCommandError(f"Unknown temperature range {temp_range}")
        await self._command("/temperature/range", spa_id, range=temp_range)

    async def async_set_panel_lock(self, spa_id: str, locked: bool) -> None:
        """Lock or unlock the spa's control panel."""
        state = "LOCK_PANEL" if locked else "UNLOCK_PANEL"
        await self._command("/panel/state", spa_id, state=state)
