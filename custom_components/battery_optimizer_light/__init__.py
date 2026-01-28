import logging
import aiohttp
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .coordinator import BatteryOptimizerLightCoordinator
from .const import *

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry):
    """Set up from a config entry."""
    config = entry.data
    
    coordinator = BatteryOptimizerLightCoordinator(hass, config)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Initiera Effektvakts-logiken
    peak_guard = PeakGuard(hass, config, coordinator)

    # --- REGISTRERA TJÄNSTEN ---
    async def handle_run_peak_guard(call: ServiceCall):
        """Huvudtjänst som anropas av automationen."""
        virtual_load_id = call.data.get("virtual_load_entity")
        limit_id = call.data.get("limit_entity")
        
        await peak_guard.update(virtual_load_id, limit_id)

    hass.services.async_register(DOMAIN, "run_peak_guard", handle_run_peak_guard)

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

class PeakGuard:
    """Hanterar logiken för effektvakten (Hysteres, Rapportering, Styrning)."""
    
    def __init__(self, hass: HomeAssistant, config, coordinator):
        self.hass = hass
        self.config = config
        self.coordinator = coordinator
        self._has_reported = False # Minne för rapportering

    async def update(self, virtual_load_id, limit_id):
        try:
            # 1. Hämta Current Load (Watt)
            load_state = self.hass.states.get(virtual_load_id)
            if not load_state or load_state.state in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
                return
            current_load = float(load_state.state)

            # 2. Hämta Limit (kW eller Watt)
            limit_state = self.hass.states.get(limit_id)
            if not limit_state or limit_state.state in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
                return
            
            raw_limit = float(limit_state.state)
            
            # AUTOMATISK KONVERTERING:
            # Om värdet är litet (<100), utgå från att det är kW och gör om till Watt.
            limit_w = raw_limit * 1000 if raw_limit < 100 else raw_limit

            # 3. Hämta SoC
            soc_entity = self.config.get(CONF_SOC_SENSOR)
            soc_state = self.hass.states.get(soc_entity)
            soc = float(soc_state.state) if soc_state and soc_state.state not in [STATE_UNKNOWN, STATE_UNAVAILABLE] else 0

            # 4. Beräkna Safe Limit (Hysteres 1000W)
            safe_limit = limit_w - 1000

            # --- BESLUTSLOGIK ---

            # FALL 1: FAROZON (Last > Gräns)
            if current_load > limit_w and soc > 5:
                # A. Rapportera (Om vi inte redan gjort det denna topp)
                if not self._has_reported:
                    await self._report_peak(current_load, limit_w)
                    self._has_reported = True
                
                # B. Reglera (Discharge)
                max_inverter = 3300
                need = current_load - limit_w
                power_to_discharge = min(need, max_inverter)
                
                await self._call_script("sonnen_force_discharge", {"power": int(power_to_discharge)})

            # FALL 2: SÄKER ZON (Last <= Safe Limit)
            elif current_load <= safe_limit:
                # A. Återställ rapporterings-flaggan
                self._has_reported = False

                # B. Kolla Molnets status via Coordinatorn
                cloud_action = self.coordinator.data.get("action", "IDLE")

                if cloud_action in ["DISCHARGE", "CHARGE"]:
                    pass # Låt molnet bestämma (Arbitrage pågår)

                elif cloud_action == "HOLD":
                    # Stoppa batteriet om det rusar (Anti-spam)
                    bat_power_entity = self.config.get(CONF_BATTERY_POWER_SENSOR)
                    bat_state = self.hass.states.get(bat_power_entity)
                    bat_power = float(bat_state.state) if bat_state else 0
                    
                    if abs(bat_power) > 100:
                        await self._call_script("sonnen_force_charge", {"power": 0})

                else: # IDLE / DEFAULT
                    await self._call_script("sonnen_set_auto_mode", {})

        except Exception as e:
            _LOGGER.error(f"Error in PeakGuard: {e}")

    async def _report_peak(self, grid_w, limit_w):
        """Skickar rapport till backend."""
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
                        _LOGGER.info(f"Reported Peak: {payload['grid_power_kw']} kW")
        except Exception as e:
            _LOGGER.error(f"Failed to report peak: {e}")

    async def _call_script(self, script_name, data):
        await self.hass.services.async_call("script", script_name, service_data=data)


async def update_listener(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok