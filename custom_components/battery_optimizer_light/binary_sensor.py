from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        BatteryLightPeakShavingActiveSensor(coordinator),
    ])

class BatteryLightPeakShavingActiveSensor(CoordinatorEntity, BinarySensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Optimizer Light Peak Shaving Active"
        self._attr_unique_id = f"{coordinator.api_key}_peak_shaving_active"
        self._attr_icon = "mdi:shield-check"

    @property
    def is_on(self):
        # Default till True om värdet saknas, precis som i logiken
        return self.coordinator.data.get("is_peak_shaving_active", True)
