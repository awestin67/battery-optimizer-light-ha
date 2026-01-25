import logging
import aiohttp
from homeassistant.core import HomeAssistant, ServiceCall
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

    # --- REGISTRERA TJÄNSTEN (SERVICE) ---
    async def handle_report_peak(call: ServiceCall):
        """Tjänst som automationer kan anropa för att rapportera en topp."""
        try:
            # 1. Hämta sensorernas ID från konfigurationen
            grid_entity = config.get(CONF_GRID_SENSOR)
            
            # 2. Läs av värdena från Home Assistant
            grid_state = hass.states.get(grid_entity)
            
            # 3. Hämta gränsvärdet från moln-koordinatorn
            limit_kw = coordinator.data.get("peak_power_kw", 12.0)
            
            # Validera
            if not grid_state or grid_state.state in ["unknown", "unavailable"]:
                _LOGGER.warning("Could not report peak: Grid sensor unavailable.")
                return

            grid_watts = float(grid_state.state)
            
            # 4. Skicka till molnet
            api_url = f"{config[CONF_API_URL].rstrip('/')}/report_peak"
            payload = {
                "api_key": config[CONF_API_KEY],
                "grid_power_kw": round(grid_watts / 1000.0, 2),
                "limit_kw": limit_kw
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=payload) as resp:
                    if resp.status == 200:
                        _LOGGER.info(f"Reported Peak: {payload['grid_power_kw']} kW (Limit: {limit_kw} kW)")
                    else:
                        _LOGGER.warning(f"Failed to report peak: {resp.status}")

        except Exception as e:
            _LOGGER.error(f"Error in report_peak service: {e}")

    # Registrera tjänsten "battery_optimizer_light.report_peak"
    hass.services.async_register(DOMAIN, "report_peak", handle_report_peak)

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

async def update_listener(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok