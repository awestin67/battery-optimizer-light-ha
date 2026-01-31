import logging
import aiohttp
from homeassistant.core import HomeAssistant, ServiceCall, CoreState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.event import async_track_state_change_event
from .coordinator import BatteryOptimizerLightCoordinator
from .const import (
    DOMAIN,
    CONF_SOC_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_API_URL,
    CONF_API_KEY,
)

_LOGGER = logging.getLogger(__name__)

# --- KONFIGURATION ---
VIRTUAL_LOAD_ENTITY = "sensor.husets_netto_last_virtuell"
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

    # --- BAKGRUNDSBEVAKNING ---
    async def on_load_change(event):
        """Körs tyst i bakgrunden varje gång lasten ändras."""
        if hass.state == CoreState.running:
            await peak_guard.update(VIRTUAL_LOAD_ENTITY, LIMIT_ENTITY)

    entry.async_on_unload(
        async_track_state_change_event(hass, [VIRTUAL_LOAD_ENTITY], on_load_change)
    )

    _LOGGER.info(f"PeakGuard active. Silently monitoring {VIRTUAL_LOAD_ENTITY}")

    async def handle_run_peak_guard(call: ServiceCall):
        v_load = call.data.get("virtual_load_entity", VIRTUAL_LOAD_ENTITY)
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

    @property
    def is_active(self):
        return self._has_reported

    def _set_reported_state(self, state: bool):
        if self._has_reported != state:
            self._has_reported = state
            # När vi går in i peak-läge är ett "hold"-kommando inte längre relevant.
            if state is True:
                self._hold_command_sent = False
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

            # 1. Hämta Gränsvärdet
            limit_state = self.hass.states.get(limit_id)
            if not limit_state or limit_state.state in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
                return

            raw_limit = float(limit_state.state)
            limit_w = raw_limit * 1000 if raw_limit < 100 else raw_limit

            # 2. Hämta Lasten
            load_state = self.hass.states.get(virtual_load_id)
            if not load_state or load_state.state in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
                return
            current_load = float(load_state.state)

            # --- TYST FILTER ---
            wake_up_threshold = limit_w * 0.90
            if not self._has_reported and current_load < wake_up_threshold:
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
                await self._report_peak_clear(current_load)

            # Steg 2: Agera baserat på tillstånd
            if self._has_reported and soc > 5:
                # TILLSTÅND PÅ: Justera urladdning
                max_inverter = 3300
                need = current_load - limit_w
                power_to_discharge = min(max(0, need), max_inverter)

                if power_to_discharge > 100:  # Skicka bara kommando om det finns ett verkligt behov
                    await self._call_script("sonnen_force_discharge", {"power": int(power_to_discharge)})

            else:
                # TILLSTÅND AV: Återgå till molnstrategi
                cloud_action = "HOLD"
                if self.coordinator.data and "action" in self.coordinator.data:
                    cloud_action = str(self.coordinator.data.get("action")).upper()

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

    async def _report_peak_clear(self, grid_w):
        try:
            api_url = f"{self.config[CONF_API_URL].rstrip('/')}/report_peak_clear"
            payload = {
                "api_key": self.config[CONF_API_KEY],
                "grid_power_kw": round(grid_w / 1000.0, 2)
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=payload) as resp:
                    if resp.status == 200:
                        _LOGGER.debug(f"Cloud report sent: PeakGuard Cleared: {payload['grid_power_kw']} kW")
        except Exception as e:
            _LOGGER.error(f"Failed to report peak clear: {e}")

    async def _call_script(self, script_name, data):
        await self.hass.services.async_call("script", script_name, service_data=data)


async def update_listener(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
