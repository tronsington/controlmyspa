"""Tests for the standalone API client, run against a fake ControlMySpa server.

Needs only aiohttp, pytest and pytest-asyncio (no Home Assistant).
"""

from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import sys
import time

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer
import pytest

# Load api.py directly so the test does not need Home Assistant installed
_API_PATH = Path(__file__).parents[1] / "custom_components" / "controlmyspa" / "api.py"
_spec = importlib.util.spec_from_file_location("controlmyspa_api", _API_PATH)
api = importlib.util.module_from_spec(_spec)
sys.modules["controlmyspa_api"] = api
_spec.loader.exec_module(api)

SPA_ID = "spa123"


def make_jwt(expires_in: float) -> str:
    """Build an unsigned JWT with an exp claim."""

    def b64(data: dict) -> str:
        raw = json.dumps(data).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{b64({'alg': 'none'})}.{b64({'exp': time.time() + expires_in})}.sig"


class FakeCloud:
    """In-memory stand-in for iot.controlmyspa.com/web."""

    def __init__(self) -> None:
        self.access = make_jwt(86400)
        self.refresh = "refresh-1"
        self.password = "hunter2"
        self.refresh_works = True
        self.calls: list[str] = []
        self.commands: list[tuple[str, dict]] = []

    def _new_pair(self) -> dict:
        self.access = make_jwt(86400)
        self.refresh = f"refresh-{len(self.calls)}"
        return {"data": {"accessToken": self.access, "refreshToken": self.refresh}}

    def _authorized(self, request: web.Request) -> bool:
        return request.headers.get("Authorization") == f"Bearer {self.access}"

    async def login(self, request: web.Request) -> web.Response:
        self.calls.append("login")
        body = await request.json()
        if body.get("password") != self.password:
            return web.json_response({"message": "bad"}, status=401)
        return web.json_response(self._new_pair())

    async def refresh_handler(self, request: web.Request) -> web.Response:
        self.calls.append("refresh")
        if not self.refresh_works or (
            request.headers.get("Authorization") != f"Bearer {self.refresh}"
        ):
            return web.json_response({"message": "expired"}, status=401)
        return web.json_response(self._new_pair())

    async def spas(self, request: web.Request) -> web.Response:
        self.calls.append("spas")
        if not self._authorized(request):
            return web.json_response({}, status=401)
        return web.json_response({"data": {"spas": [{"_id": SPA_ID}]}})

    async def spa(self, request: web.Request) -> web.Response:
        self.calls.append("spa")
        if not self._authorized(request):
            return web.json_response({}, status=401)
        # The real record embeds a stale snapshot of currentState
        return web.json_response({"_id": SPA_ID, "currentState": {"desiredTemp": "STALE"}})

    async def current_state(self, request: web.Request) -> web.Response:
        self.calls.append("state")
        if not self._authorized(request):
            return web.json_response({}, status=401)
        return web.json_response(
            {"statusCode": 200, "data": {"currentTemp": "104.00", "desiredTemp": "100.00"}}
        )

    async def command(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            return web.json_response({}, status=401)
        self.commands.append((request.match_info["path"], await request.json()))
        return web.json_response({"statusCode": 200})

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/web/auth/login", self.login)
        app.router.add_get("/web/auth/refresh", self.refresh_handler)
        app.router.add_get("/web/spas", self.spas)
        app.router.add_get("/web/spas/{spa_id}", self.spa)
        app.router.add_get("/web/spas/{spa_id}/current-state", self.current_state)
        app.router.add_post("/web/spa-commands/{path:.*}", self.command)
        return app


@pytest.fixture
async def cloud():
    fake = FakeCloud()
    server = TestServer(fake.app())
    await server.start_server()
    async with ClientSession() as session:
        fake.client = api.ControlMySpaApi(
            session,
            "Owner@Example.com",
            fake.password,
            base_url=str(server.make_url("/web")),
        )
        yield fake
    await server.close()


async def test_first_request_logs_in(cloud):
    spas = await cloud.client.async_get_spas()
    assert spas == [{"_id": SPA_ID}]
    assert cloud.calls == ["login", "spas"]


async def test_current_state_returns_live_data(cloud):
    state = await cloud.client.async_get_current_state(SPA_ID)
    assert state == {"currentTemp": "104.00", "desiredTemp": "100.00"}
    assert cloud.calls == ["login", "state"]


async def test_401_triggers_refresh_not_login(cloud):
    await cloud.client.async_get_spa(SPA_ID)
    cloud.access = make_jwt(86400)  # server-side revoke of the old access token
    data = await cloud.client.async_get_spa(SPA_ID)
    assert data["_id"] == SPA_ID
    assert cloud.calls == ["login", "spa", "spa", "refresh", "spa"]


async def test_failed_refresh_falls_back_to_login(cloud):
    await cloud.client.async_get_spa(SPA_ID)
    cloud.access = make_jwt(86400)
    cloud.refresh_works = False
    await cloud.client.async_get_spa(SPA_ID)
    assert cloud.calls[-3:] == ["refresh", "login", "spa"]


async def test_expiring_token_refreshes_before_request(cloud):
    await cloud.client.async_get_spa(SPA_ID)
    cloud.client._access_expiry = time.time() + 10  # inside the safety margin
    await cloud.client.async_get_spa(SPA_ID)
    assert cloud.calls == ["login", "spa", "refresh", "spa"]


async def test_bad_password_raises_auth_error(cloud):
    cloud.password = "changed"
    with pytest.raises(api.ControlMySpaAuthError):
        await cloud.client.async_get_spas()


async def test_email_is_lowercased(cloud):
    assert cloud.client._email == "owner@example.com"


async def test_component_command_payload(cloud):
    await cloud.client.async_set_component_state(SPA_ID, "PUMP", "1", "ON")
    await cloud.client.async_set_component_state(SPA_ID, "LIGHT", "0", "HIGH")
    await cloud.client.async_set_component_state(SPA_ID, "OZONE", None, "OFF")
    assert cloud.commands == [
        ("component-state", {"spaId": SPA_ID, "via": "WEB", "componentType": "jet", "state": "HIGH", "deviceNumber": 1}),
        ("component-state", {"spaId": SPA_ID, "via": "WEB", "componentType": "light", "state": "HIGH", "deviceNumber": 0}),
        ("component-state", {"spaId": SPA_ID, "via": "WEB", "componentType": "ozone", "state": "OFF"}),
    ]


async def test_temperature_and_mode_payloads(cloud):
    await cloud.client.async_set_temperature(SPA_ID, 102)
    await cloud.client.async_set_heater_mode(SPA_ID, "REST")
    await cloud.client.async_set_temperature_range(SPA_ID, "LOW")
    await cloud.client.async_set_panel_lock(SPA_ID, True)
    assert cloud.commands == [
        ("temperature/value", {"spaId": SPA_ID, "via": "WEB", "value": 102}),
        ("temperature/heater-mode", {"spaId": SPA_ID, "via": "WEB", "mode": "REST"}),
        ("temperature/range", {"spaId": SPA_ID, "via": "WEB", "range": "LOW"}),
        ("panel/state", {"spaId": SPA_ID, "via": "WEB", "state": "LOCK_PANEL"}),
    ]


async def test_invalid_heater_mode_rejected_locally(cloud):
    with pytest.raises(api.ControlMySpaCommandError):
        await cloud.client.async_set_heater_mode(SPA_ID, "TURBO")
    assert cloud.commands == []


@pytest.mark.parametrize(
    ("value", "component_type", "expected"),
    [
        ("LOW", "PUMP", "LOW"),
        ("high", "LIGHT", "HIGH"),
        (2, "PUMP", "HIGH"),
        ("2", "LIGHT", "MED"),
        (1, "OZONE", "ON"),
        (None, "PUMP", "OFF"),
        ("bogus", "PUMP", "OFF"),
    ],
)
def test_normalize_state(value, component_type, expected):
    assert api.normalize_state(value, component_type) == expected
