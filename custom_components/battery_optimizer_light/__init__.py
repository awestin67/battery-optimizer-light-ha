# Battery Optimizer Light
# Copyright (C) 2026 @awestin67
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import logging
import aiohttp
from homeassistant.core import HomeAssistant, ServiceCall, CoreState # type: ignore
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN # type: ignore
from homeassistant.helpers.event import async_track_state_change_event # type: ignore
from .coordinator import BatteryOptimizerLightCoordinator
from .const import (
    DOMAIN,
    CONF_SOC_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_API_URL,
    CONF_API_KEY,
    CONF_GRID_SENSOR,
    CONF_GRID_SENSOR_INVERT,
    CONF_BATTERY_STATUS_SENSOR,
    CONF_BATTERY_STATUS_KEYWORDS,
    CONF_VIRTUAL_LOAD_SENSOR,
    DEFAULT_BATTERY_STATUS_KEYWORDS,
)

_LOGGER = logging.getLogger(__name__)

# --- KONFIGURATION ---
LIMIT_ENTITY = "sensor.optimizer_light_peak_limit"

async def async_setup_entry(hass: HomeAssistant, entry):
    """Set up from a config entry."""
    config = entry.data

    coordinator = BatteryOptimizerLightCoordinator(hass, config)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Initiera PeakGuard
    peak_guard = PeakGuard(hass, config, coordinator)
    coordinator.peak_guard = peak_guard

    # Hämta virtuell last-sensor från config (kan vara None)
    virtual_load_entity = config.get(CONF_VIRTUAL_LOAD_SENSOR)

    # --- BAKGRUNDSBEVAKNING ---
    async def on_load_change(event):
        """Körs tyst i bakgrunden varje gång lasten ändras."""
        if hass.state == CoreState.running:
            await peak_guard.update(virtual_load_entity, LIMIT_ENTITY)

    if virtual_load_entity:
        entry.async_on_unload(
            async_track_state_change_event(hass, [virtual_load_entity], on_load_change)
        )
        _LOGGER.info(f"PeakGuard active. Silently monitoring {virtual_load_entity}")
    else:
        # Om ingen virtuell sensor valts, bevaka Grid och Batteri för automatisk beräkning
        grid_entity = config.get(CONF_GRID_SENSOR)
        bat_entity = config.get(CONF_BATTERY_POWER_SENSOR)
        entry.async_on_unload(
            async_track_state_change_event(hass, [grid_entity, bat_entity], on_load_change)
        )
        _LOGGER.info(f"PeakGuard active. Calculating virtual load from {grid_entity} + {bat_entity}")

    async def handle_run_peak_guard(call: ServiceCall):
        v_load = call.data.get("virtual_load_entity", virtual_load_entity)
        limit = call.data.get("limit_entity", LIMIT_ENTITY)
        await peak_guard.update(v_load, limit)

    hass.services.async_register(DOMAIN, "run_peak_guard", handle_run_peak_guard)

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

class PeakGuard:
    """Hanterar logiken för effektvakten."""

    def __init__(self, hass: HomeAssistant, config, coordinator):
        self.hass = hass
        self.config = config
        self.coordinator = coordinator
        self._has_reported = False
        self._hold_command_sent = False  # Flagga för att undvika upprepade kommandon
        self._capacity_exceeded_logged = False  # Flagga för att logga överlast en gång
        self._is_solar_override = False  # Flagga för sol-override
        self._in_maintenance = False  # Flagga för underhållsläge
        self._maintenance_reason = None  # Orsak till underhållsläge

    @property
    def is_active(self):
        return self._has_reported

    @property
    def is_solar_override(self):
        return self._is_solar_override

    @property
    def in_maintenance(self):
        return self._in_maintenance

    @property
    def maintenance_reason(self):
        return self._maintenance_reason

    def _set_reported_state(self, state: bool):
        if self._has_reported != state:
            self._has_reported = state
            # När vi går in i peak-läge är ett "hold"-kommando inte längre relevant.
            if state is True:
                self._hold_command_sent = False
            else:
                # Återställ flaggor när toppen är över
                self._capacity_exceeded_logged = False
            self.coordinator.async_update_listeners()

    async def update(self, virtual_load_id, limit_id):
        try:
            # 0. Kontrollera om Peak Shaving är aktivt
            is_active = True
            if self.coordinator.data:
                is_active = self.coordinator.data.get("is_peak_shaving_active", True)

            if not is_active:
                if self.is_active:
                    self._set_reported_state(False)
                return

            # 0.1 Kontrollera Batteristatus (Maintenance/Full Charge)
            status_entity = self.config.get(CONF_BATTERY_STATUS_SENSOR)
            if status_entity:
                status_state = self.hass.states.get(status_entity)
                if status_state and status_state.state not in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
                    # Hämta nyckelord från config (eller använd default)
                    keywords_str = self.config.get(CONF_BATTERY_STATUS_KEYWORDS, DEFAULT_BATTERY_STATUS_KEYWORDS)
                    keywords = [k.strip().lower() for k in keywords_str.split(",") if k.strip()]

                    val_display = str(status_state.state)
                    val_lower = val_display.lower()
                    if any(k in val_lower for k in keywords):
                        if not self._in_maintenance:
                            _LOGGER.info(f"🔋 Maintenance mode detected ({val_display}). Pausing control.")
                            self._in_maintenance = True

                        self._maintenance_reason = val_display

                        if self.is_active:
                            self._set_reported_state(False)
                        return
                    elif self._in_maintenance:
                        _LOGGER.info("🔋 Maintenance mode ended. Resuming control.")
                        self._in_maintenance = False
                        self._maintenance_reason = None

            # 1. Hämta Gränsvärdet
            limit_state = self.hass.states.get(limit_id)
            if not limit_state or limit_state.state in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
                return

            raw_limit = float(limit_state.state)
            limit_w = raw_limit * 1000 if raw_limit < 100 else raw_limit

            # 2. Hämta Lasten
            current_load = 0.0
            if virtual_load_id:
                # Använd manuellt vald sensor
                load_state = self.hass.states.get(virtual_load_id)
                if not load_state or load_state.state in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
                    return
                current_load = float(load_state.state)
            else:
                # Beräkna automatiskt: Grid + Batteri
                grid_id = self.config.get(CONF_GRID_SENSOR)
                bat_id = self.config.get(CONF_BATTERY_POWER_SENSOR)

                grid_state = self.hass.states.get(grid_id)
                bat_state = self.hass.states.get(bat_id)

                grid_val = (
                    float(grid_state.state)
                    if grid_state and grid_state.state not in [STATE_UNKNOWN, STATE_UNAVAILABLE]
                    else 0.0
                )
                bat_val = (
                    float(bat_state.state)
                    if bat_state and bat_state.state not in [STATE_UNKNOWN, STATE_UNAVAILABLE]
                    else 0.0
                )

                if self.config.get(CONF_GRID_SENSOR_INVERT, False):
                    grid_val = -grid_val

                current_load = grid_val + bat_val

            # --- TYST FILTER ---
            wake_up_threshold = limit_w * 0.90
            # Avbryt bara om:
            # 1. Ingen peak är aktiv.
            # 2. Ingen Solar Override är aktiv (vi måste kunna stänga av den).
            # 3. Lasten är under varningsgränsen.
            # 4. Vi INTE exporterar (för då måste vi kolla Solar Override).
            if (
                not self._has_reported
                and not self._is_solar_override
                and current_load < wake_up_threshold
                and current_load > -200
            ):
                return

            # 3. Hämta SoC
            soc_entity = self.config.get(CONF_SOC_SENSOR)
            soc_state = self.hass.states.get(soc_entity)
            soc = (
                float(soc_state.state)
                if soc_state and soc_state.state not in [STATE_UNKNOWN, STATE_UNAVAILABLE]
                else 0
            )

            # 4. Gränser
            safe_limit = limit_w - 1000

            # --- NY LOGIK MED HYSTERES ---

            # Steg 1: Bestäm tillstånd (På / Av)
            if not self._has_reported and current_load > limit_w and soc > 5:
                _LOGGER.info(f"🚨 PEAK DETECTED! Load: {current_load} W > Limit: {limit_w} W. Engaging battery.")
                self._set_reported_state(True)
                await self._report_peak(current_load, limit_w)

            elif self._has_reported and current_load <= safe_limit:
                _LOGGER.info(f"✅ PEAK CLEARED. Load: {current_load} W. Returning to strategy.")
                self._set_reported_state(False)
                await self._report_peak_clear(current_load, limit_w)

            # Steg 2: Agera baserat på tillstånd
            if self._has_reported and soc > 5:
                # TILLSTÅND PÅ: Justera urladdning
                max_inverter = 3300.0
                if self.coordinator.data and "max_discharge_kw" in self.coordinator.data:
                    val = self.coordinator.data.get("max_discharge_kw")
                    if val is not None:
                        max_inverter = float(val) * 1000.0

                need = current_load - limit_w

                # Detektera om vi inte klarar att hålla gränsen
                if need > max_inverter:
                    if not self._capacity_exceeded_logged:
                        _LOGGER.warning(
                            f"PeakGuard capacity exceeded! Need: {need} W > Max: {max_inverter} W. "
                            f"Limit {limit_w} W cannot be held."
                        )
                        self._capacity_exceeded_logged = True
                        await self._report_peak_failure(current_load, limit_w)

                power_to_discharge = min(max(0, need), max_inverter)

                if power_to_discharge > 100:  # Skicka bara kommando om det finns ett verkligt behov
                    await self._call_script("sonnen_force_discharge", {"power": int(power_to_discharge)})

            else:
                # TILLSTÅND AV: Återgå till molnstrategi
                cloud_action = "HOLD"
                if self.coordinator.data and "action" in self.coordinator.data:
                    cloud_action = str(self.coordinator.data.get("action")).upper()

                # --- SOLAR OVERRIDE ---
                # Om vi exporterar el (negativ last) och molnet säger HOLD,
                # är det bättre att låta batteriet ladda (Auto) än att tvinga 0W.
                new_override = False
                if cloud_action == "HOLD" and current_load < -200:
                    new_override = True
                    cloud_action = "IDLE"  # Tvinga Auto-läge lokalt

                if self._is_solar_override != new_override:
                    if new_override:
                        await self._report_solar_override(current_load, limit_w)
                    else:
                        await self._report_solar_override_clear(current_load, limit_w)
                    self._is_solar_override = new_override
                    self.coordinator.async_update_listeners()  # Uppdatera sensorer

                if cloud_action != "HOLD":
                    self._hold_command_sent = False  # Återställ om molnet vill något annat

                if cloud_action in ["DISCHARGE", "CHARGE"]:
                    pass  # Låt molnet bestämma

                elif cloud_action == "HOLD":
                    bat_entity = self.config.get(CONF_BATTERY_POWER_SENSOR)
                    bat_state = self.hass.states.get(bat_entity)
                    bat_power = 0
                    if bat_state and bat_state.state not in [
                        STATE_UNKNOWN,
                        STATE_UNAVAILABLE,
                    ]:
                        bat_power = float(bat_state.state)

                    if abs(bat_power) > 100:
                        if not self._hold_command_sent:
                            _LOGGER.debug("HOLD requested, but battery is active. Sending stop command.")
                            await self._call_script("sonnen_force_charge", {"power": 0})
                            self._hold_command_sent = True
                    else:
                        # Batteriet är redan stilla, så nollställ flaggan.
                        if self._hold_command_sent:
                            _LOGGER.debug("Battery is now idle, resetting hold_command_sent flag.")
                        self._hold_command_sent = False

                elif cloud_action == "IDLE":
                    await self._call_script("sonnen_set_auto_mode", {})

                else:
                    pass  # Okänt läge -> Gör inget
        except Exception as e:
            _LOGGER.error(f"Error in PeakGuard update: {e}", exc_info=True)

    async def _report_peak(self, grid_w, limit_w):
        try:
            api_url = f"{self.config[CONF_API_URL].rstrip('/')}/report_peak"
            payload = {
                "api_key": self.config[CONF_API_KEY],
                "grid_power_kw": round(grid_w / 1000.0, 2),
                "limit_kw": round(limit_w / 1000.0, 2)
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=payload) as resp:
                    if resp.status == 200:
                        _LOGGER.debug(f"Cloud report sent: PeakGuard Triggered: {payload['grid_power_kw']} kW")
        except Exception as e:
            _LOGGER.error(f"Failed to report peak: {e}")

    async def _report_peak_clear(self, grid_w, limit_w):
        try:
            api_url = f"{self.config[CONF_API_URL].rstrip('/')}/report_peak_clear"
            payload = {
                "api_key": self.config[CONF_API_KEY],
                "grid_power_kw": round(grid_w / 1000.0, 2),
                "limit_kw": round(limit_w / 1000.0, 2)
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=payload) as resp:
                    if resp.status == 200:
                        _LOGGER.debug(f"Cloud report sent: PeakGuard Cleared: {payload['grid_power_kw']} kW")
        except Exception as e:
            _LOGGER.error(f"Failed to report peak clear: {e}")

    async def _report_peak_failure(self, grid_w, limit_w):
        try:
            api_url = f"{self.config[CONF_API_URL].rstrip('/')}/report_peak_failure"
            payload = {
                "api_key": self.config[CONF_API_KEY],
                "grid_power_kw": round(grid_w / 1000.0, 2),
                "limit_kw": round(limit_w / 1000.0, 2)
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=payload) as resp:
                    if resp.status == 200:
                        _LOGGER.debug(f"Cloud report sent: PeakGuard Failure: {payload['grid_power_kw']} kW")
        except Exception as e:
            _LOGGER.error(f"Failed to report peak failure: {e}")

    async def _report_solar_override(self, grid_w, limit_w):
        try:
            api_url = f"{self.config[CONF_API_URL].rstrip('/')}/report_solar_override"
            payload = {
                "api_key": self.config[CONF_API_KEY],
                "grid_power_kw": round(grid_w / 1000.0, 2),
                "limit_kw": round(limit_w / 1000.0, 2)
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=payload) as resp:
                    if resp.status == 200:
                        _LOGGER.debug(f"Cloud report sent: Solar Override: {payload['grid_power_kw']} kW")
        except Exception as e:
            _LOGGER.error(f"Failed to report solar override: {e}")

    async def _report_solar_override_clear(self, grid_w, limit_w):
        try:
            api_url = f"{self.config[CONF_API_URL].rstrip('/')}/report_solar_override_clear"
            payload = {
                "api_key": self.config[CONF_API_KEY],
                "grid_power_kw": round(grid_w / 1000.0, 2),
                "limit_kw": round(limit_w / 1000.0, 2)
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=payload) as resp:
                    if resp.status == 200:
                        _LOGGER.debug(f"Cloud report sent: Solar Override Cleared: {payload['grid_power_kw']} kW")
        except Exception as e:
            _LOGGER.error(f"Failed to report solar override clear: {e}")

    async def _call_script(self, script_name, data):
        await self.hass.services.async_call("script", script_name, service_data=data)


async def update_listener(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
