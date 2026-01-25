from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass, # <--- Importera denna
    SensorStateClass,  # <--- Och denna
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([
        BatteryLightActionSensor(coordinator),
        BatteryLightPowerSensor(coordinator),
        BatteryLightReasonSensor(coordinator),
        BatteryLightBufferSensor(coordinator)
    ])

class BatteryLightActionSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Optimizer Light Action"
        self._attr_unique_id = f"{coordinator.api_key}_light_action"
        self._attr_icon = "mdi:lightning-bolt-circle"

    @property
    def state(self):
        return self.coordinator.data.get("action", "UNKNOWN")

class BatteryLightPowerSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Optimizer Light Power"
        self._attr_unique_id = f"{coordinator.api_key}_light_power"
        self._attr_unit_of_measurement = "kW"
        self._attr_icon = "mdi:flash"

        # Talar om för HA att det är effekt -> Ger rätt grafer och färger
        self._attr_device_class = SensorDeviceClass.POWER
        # Talar om att det är ett mätvärde -> Sparar statistik för långtidshistorik
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def state(self):
        return self.coordinator.data.get("target_power_kw", 0.0)

class BatteryLightReasonSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Optimizer Light Reason"
        self._attr_unique_id = f"{coordinator.api_key}_light_reason"
        self._attr_icon = "mdi:text-box-outline"

    @property
    def state(self):
        return self.coordinator.data.get("reason", "")
class BatteryLightBufferSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Optimizer Light Buffer Target"
        self._attr_unique_id = f"{coordinator.api_key}_light_buffer"
        self._attr_unit_of_measurement = "%"
        self._attr_icon = "mdi:shield-check"
        
        # Visar batteri-procent snyggt i HA
        self._attr_device_class = SensorDeviceClass.BATTERY 

    @property
    def state(self):
        # Hämtar 'min_soc_buffer' från backend JSON. Default 0.0 om det saknas.
        return self.coordinator.data.get("min_soc_buffer", 0.0)