from .coordinator import BatteryOptimizerLightCoordinator
from .const import DOMAIN

async def async_setup_entry(hass, entry):
    """Set up from a config entry."""
    
    # Nu kan vi lita på att entry.data alltid är uppdaterad och korrekt
    config = entry.data

    # Starta Coordinator
    coordinator = BatteryOptimizerLightCoordinator(hass, config)
    
    # Försök hämta data första gången. 
    # Om API-nyckeln är fel kommer detta kasta ett fel, men det är okej.
    # Användaren kan nu gå in och ändra nyckeln via "Konfigurera" och ladda om.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    # Lyssnare för att ladda om integrationen om man ändrar inställningar
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

async def update_listener(hass, entry):
    """Laddar om integrationen när inställningar ändras."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    """Städar upp."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok