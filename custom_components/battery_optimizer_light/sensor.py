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

from homeassistant.components.sensor import ( # type: ignore
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity # type: ignore
from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE # type: ignore
from .const import (
    DOMAIN,
    CONF_GRID_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_VIRTUAL_LOAD_SENSOR,
    CONF_GRID_SENSOR_INVERT,
)

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        BatteryLightActionSensor(coordinator),
        BatteryLightPowerSensor(coordinator),
        BatteryLightReasonSensor(coordinator),
        BatteryLightBufferSensor(coordinator),
        BatteryLightPeakSensor(coordinator),
        BatteryLightStatusSensor(coordinator),
        BatteryLightVirtualLoadSensor(coordinator)
    ])

class BatteryLightActionSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Optimizer Light Action"
        self._attr_unique_id = f"{coordinator.api_key}_light_action"
        self._attr_icon = "mdi:lightning-bolt-circle"

    @property
    def state(self):
        raw_action = (self.coordinator.data or {}).get("action", "UNKNOWN")

        # Om PeakGuard har aktiverat Solar Override, visa IDLE (Auto) istället för HOLD
        if hasattr(self.coordinator, "peak_guard") and self.coordinator.peak_guard.is_solar_override:
            if raw_action == "HOLD":
                return "IDLE"
        return raw_action

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
        return (self.coordinator.data or {}).get("target_power_kw", 0.0)

class BatteryLightReasonSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Optimizer Light Reason"
        self._attr_unique_id = f"{coordinator.api_key}_light_reason"
        self._attr_icon = "mdi:text-box-outline"

    @property
    def state(self):
        # 1. Kolla först om den lokala effektvakten jobbar
        # (Detta skriver över molnets status, vilket är korrekt eftersom lokalt skydd har prio)
        if hasattr(self.coordinator, "peak_guard"):
            pg = self.coordinator.peak_guard
            if pg.is_active:
                return "Local Peak Guard Triggered"
            if pg.is_solar_override:
                return "Solar Override (Local)"

        # 2. Annars visa vad molnet säger (t.ex. "Charging due to cheap price")
        return (self.coordinator.data or {}).get("reason", "Unknown")

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
        return (self.coordinator.data or {}).get("min_soc_buffer", 0.0)

class BatteryLightPeakSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Optimizer Light Peak Limit"
        self._attr_unique_id = f"{coordinator.api_key}_light_peak_limit"
        self._attr_unit_of_measurement = "kW"
        self._attr_icon = "mdi:transmission-tower-export"
        self._attr_device_class = SensorDeviceClass.POWER

    @property
    def state(self):
        # Hämta värdet från backend. Default 12.0 (högt) om det saknas för att inte trigga i onödan.
        return (self.coordinator.data or {}).get("peak_power_kw", 12.0)

class BatteryLightStatusSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Optimizer Light PeakGuard Status"
        self._attr_unique_id = f"{coordinator.api_key}_peakguard_status"

    @property
    def state(self):
        # Hämtar data från coordinator och lokal peak_guard instans. Först säkerställ att data finns.
        data = self.coordinator.data or {}
        is_active = data.get("is_peak_shaving_active", True)

        is_triggered = False
        in_maintenance = False
        maintenance_reason = None
        is_solar_override = False

        if hasattr(self.coordinator, "peak_guard"):
            pg = self.coordinator.peak_guard
            is_triggered = pg.is_active
            in_maintenance = pg.in_maintenance
            maintenance_reason = pg.maintenance_reason
            is_solar_override = pg.is_solar_override

        if in_maintenance:
            return f"Maintenance mode detected ({maintenance_reason}). Pausing control."

        if is_solar_override:
            return "Solar Override Active"

        if not is_active:
            return "Disabled"
        return "Triggered" if is_triggered else "Monitoring"

    @property
    def icon(self):
        """Returnerar en dynamisk ikon baserat på status."""
        status = self.state
        if status == "Disabled":
            return "mdi:shield-off"
        if status == "Triggered":
            return "mdi:shield-alert"
        if "Maintenance" in status:
            return "mdi:tools"
        if "Solar Override" in status:
            return "mdi:solar-panel"
        return "mdi:shield-search"

class BatteryLightVirtualLoadSensor(SensorEntity):
    """Sensor som visar den beräknade virtuella lasten (för verifiering)."""
    def __init__(self, coordinator):
        # Vi ärver inte från CoordinatorEntity eftersom vi vill polla oftare (default 30s)
        # eller bara visa beräknat värde, oberoende av moln-uppdateringar.
        self.coordinator = coordinator
        self._attr_name = "Optimizer Light Virtual Load"
        self._attr_unique_id = f"{coordinator.api_key}_virtual_load"
        self._attr_unit_of_measurement = "W"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:home-lightning-bolt-outline"

    @property
    def state(self):
        if not hasattr(self.coordinator, "peak_guard"):
            return None

        config = self.coordinator.peak_guard.config
        hass = self.coordinator.hass

        # 1. Om en specifik sensor är vald, visa dess värde
        virtual_load_id = config.get(CONF_VIRTUAL_LOAD_SENSOR)
        if virtual_load_id:
            state = hass.states.get(virtual_load_id)
            if state and state.state not in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
                try:
                    return float(state.state)
                except ValueError:
                    pass
            return None

        # 2. Annars beräkna: Grid + Batteri
        grid_id = config.get(CONF_GRID_SENSOR)
        bat_id = config.get(CONF_BATTERY_POWER_SENSOR)
        invert_grid = config.get(CONF_GRID_SENSOR_INVERT, False)

        grid_val = 0.0
        bat_val = 0.0

        if grid_id:
            state = hass.states.get(grid_id)
            if state and state.state not in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
                try:
                    grid_val = float(state.state)
                except ValueError:
                    pass

        if bat_id:
            state = hass.states.get(bat_id)
            if state and state.state not in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
                try:
                    bat_val = float(state.state)
                except ValueError:
                    pass

        if invert_grid:
            grid_val = -grid_val

        return int(grid_val + bat_val)
