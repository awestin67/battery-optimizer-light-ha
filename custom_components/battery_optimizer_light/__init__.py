import logging
import aiohttp
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
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

    # Initiera PeakGuard (Logik-motorn)
    peak_guard = PeakGuard(hass, config, coordinator)

    # --- REGISTRERA TJÄNSTEN SOM AUTOMATIONEN ANROPAR ---
    async def handle_run_peak_guard(call: ServiceCall):
        """Huvudtjänst som anropas av automationen."""
        # Hämta entitets-IDn från automationens 'data'-block
        virtual_load_id = call.data.get("virtual_load_entity")
        limit_id = call.data.get("limit_entity")
        
        # Kör logiken
        await peak_guard.update(virtual_load_id, limit_id)

    # Registrera tjänsten så den syns i Home Assistant
    hass.services.async_register(DOMAIN, "run_peak_guard", handle_run_peak_guard)

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

class PeakGuard:
    """Hanterar logiken för effektvakten (Filter, Hysteres, Rapportering)."""
    
    def __init__(self, hass: HomeAssistant, config, coordinator):
        self.hass = hass
        self.config = config
        self.coordinator = coordinator
        self._has_reported = False # Minne: Har vi rapporterat denna topp än?

    async def update(self, virtual_load_id, limit_id):
        try:
            # 1. Hämta Gränsvärdet (Krävs för filtret)
            limit_state = self.hass.states.get(limit_id)
            if not limit_state or limit_state.state in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
                return
            
            raw_limit = float(limit_state.state)
            # Smart konvertering: Om < 100, anta kW och gör om till Watt
            limit_w = raw_limit * 1000 if raw_limit < 100 else raw_limit

            # 2. Hämta Nuvarande Last
            load_state = self.hass.states.get(virtual_load_id)
            if not load_state or load_state.state in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
                return
            current_load = float(load_state.state)

            # --- DYNAMISKT FILTER (Optimerar prestanda) ---
            # Eftersom automationen triggar ofta, gör vi en snabbkoll här.
            # Om vi INTE redan jobbar med en topp, och lasten är under 90% av gränsen:
            # Avbryt direkt. Spara CPU och loggutrymme.
            
            wake_up_threshold = limit_w * 0.90
            
            if not self._has_reported and current_load < wake_up_threshold:
                return 

            # 3. Hämta SoC (Körs bara om vi passerat filtret)
            soc_entity = self.config.get(CONF_SOC_SENSOR)
            soc_state = self.hass.states.get(soc_entity)
            soc = float(soc_state.state) if soc_state and soc_state.state not in [STATE_UNKNOWN, STATE_UNAVAILABLE] else 0

            # 4. Hysteres (Safe Limit = 1000W under gränsen)
            safe_limit = limit_w - 1000

            # --- HUVUDLOGIK ---
            
            # FALL 1: FAROZON (Last > Gräns)
            if current_load > limit_w and soc > 5:
                # A. Rapportera till molnet (En gång per topp)
                if not self._has_reported:
                    await self._report_peak(current_load, limit_w)
                    self._has_reported = True
                
                # B. Reglera batteriet
                max_inverter = 3300
                need = current_load - limit_w
                power_to_discharge = min(need, max_inverter)
                
                await self._call_script("sonnen_force_discharge", {"power": int(power_to_discharge)})

            # FALL 2: SÄKER ZON (Last <= Safe Limit)
            elif current_load <= safe_limit:
                # A. Återställ rapporterings-flaggan
                self._has_reported = False 
                
                # B. Kolla vad molnet vill göra (via coordinatorn)
                cloud_action = self.coordinator.data.get("action", "IDLE")

                if cloud_action in ["DISCHARGE", "CHARGE"]:
                    pass # Låt molnets strategi (Arbitrage) fortsätta
                
                elif cloud_action == "HOLD":
                    # Anti-spam: Stäng bara av om batteriet faktiskt rör sig (>100W)
                    bat_entity = self.config.get(CONF_BATTERY_POWER_SENSOR)
                    bat_state = self.hass.states.get(bat_entity)
                    bat_power = float(bat_state.state) if bat_state else 0
                    if abs(bat_power) > 100:
                        await self._call_script("sonnen_force_charge", {"power": 0})
                
                else: 
                    # Default: IDLE/Auto
                    # Vi sätter Auto-läge här för att garantera återgång efter en topp.
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
        """Hjälpfunktion för att anropa HA-tjänster."""
        await self.hass.services.async_call("script", script_name, service_data=data)


async def update_listener(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok