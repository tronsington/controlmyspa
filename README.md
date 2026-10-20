# ControlMySpa for Home Assistant

A custom integration for hot tubs connected to Balboa's ControlMySpa cloud
(controlmyspa.com). You sign in once with your ControlMySpa email and
password; the integration finds your spa and keeps its own login fresh, so
there is no token to copy or renew.

## What you get

All entities are grouped under one **Hot Tub** device. Pumps, blowers, lights
and filters are created from what your spa actually reports.

| Entity | Type | Notes |
|---|---|---|
| Thermostat | climate | Set the water temperature. Limits follow the active range (for example 80 to 104 °F in High). |
| Heater mode | select | Ready, Rest, Ready-in-Rest |
| Temperature range | select | High, Low |
| Pump N | select or switch | Select (Off / Low / High) for two-speed pumps, switch for single-speed |
| Blower N | select or switch | Same rule as pumps |
| Light N | light | On / off |
| Panel lock | switch | Locks the spa's physical control panel |
| Water temperature, Set point | sensor | |
| Run mode | sensor | |
| Controller version | sensor | Diagnostic |
| Online | binary sensor | |
| Ethernet connected, RS485 active | binary sensor | Diagnostic |
| Ozone, Filter N | binary sensor | On while running |

Controls become unavailable while the spa is offline; the status sensors stay
available so you can see that it is offline.

## Install (manual)

1. Copy `custom_components/controlmyspa` into your Home Assistant
   `config/custom_components/` folder, so you end up with
   `config/custom_components/controlmyspa/manifest.json`.
2. Restart Home Assistant.
3. Go to **Settings > Devices & services > Add integration**, search for
   **ControlMySpa**, and sign in.

## Install (HACS custom repository)

1. In HACS, open the menu and choose **Custom repositories**.
2. Add `https://github.com/tronsington/controlmyspa` with type **Integration**.
3. Install **ControlMySpa**, restart Home Assistant, then add the integration
   as above.

## How login works

- Signing in sends your email and password to ControlMySpa's own login
  endpoint, the same one the controlmyspa.com portal uses.
- The returned access token lasts about 24 hours. Before it expires the
  integration swaps its refresh token for a new pair. If that is rejected, it
  signs in again with the saved email and password.
- If the password stops working, Home Assistant shows a **Reauthenticate**
  prompt instead of failing silently.
- Diagnostics downloads redact your email, password, tokens, serial number,
  address and IP address.

## Options

**Update interval**: how often the spa's state is read (default 60 seconds,
15 to 3600). After any command the state is re-read at 3, 10 and 25 seconds.

## Migrating from a `rest:` sensor setup

If you used a `rest:` block with a pasted bearer token, delete that block once
this integration is working, then reload or restart. The new entities have
different IDs, so update any dashboards and automations that referenced the
old `sensor.hot_tub_*` entities.

## Notes and limits

- This uses ControlMySpa's private web API, worked out from the
  controlmyspa.com portal. Balboa can change it without notice.
- Spas set to Celsius have not been tested. Temperatures are sent to the API in
  Fahrenheit, the same as the portal does.
- Not affiliated with or endorsed by Balboa Water Group.
