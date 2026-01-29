import sys
import os
from unittest.mock import MagicMock

# --- MOCK HOME ASSISTANT ---
# Vi måste mocka HA-moduler INNAN vi importerar komponenten
# för att slippa installera 'homeassistant' lokalt.

mock_hass = MagicMock()
sys.modules["homeassistant"] = mock_hass
sys.modules["homeassistant.core"] = mock_hass
sys.modules["homeassistant.helpers"] = mock_hass
sys.modules["homeassistant.helpers.event"] = mock_hass
sys.modules["homeassistant.exceptions"] = mock_hass
sys.modules["homeassistant.components"] = mock_hass

mock_const = MagicMock()
mock_const.STATE_UNAVAILABLE = "unavailable"
mock_const.STATE_UNKNOWN = "unknown"
sys.modules["homeassistant.const"] = mock_const

mock_uc = MagicMock()
class UpdateFailed(Exception):
    pass
mock_uc.UpdateFailed = UpdateFailed

class MockDataUpdateCoordinator:
    def __init__(self, hass, *args, **kwargs):
        self.hass = hass
        self.data = None
        self.async_config_entry_first_refresh = AsyncMock()

mock_uc.DataUpdateCoordinator = MockDataUpdateCoordinator

class MockCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator
mock_uc.CoordinatorEntity = MockCoordinatorEntity
sys.modules["homeassistant.helpers.update_coordinator"] = mock_uc

mock_sensor = MagicMock()
class MockSensorEntity:
    pass
mock_sensor.SensorEntity = MockSensorEntity
mock_sensor.SensorDeviceClass = MagicMock
mock_sensor.SensorStateClass = MagicMock
sys.modules["homeassistant.components.sensor"] = mock_sensor

mock_binary_sensor = MagicMock()
class MockBinarySensorEntity:
    pass
mock_binary_sensor.BinarySensorEntity = MockBinarySensorEntity
sys.modules["homeassistant.components.binary_sensor"] = mock_binary_sensor

# Lägg till rotmappen i sökvägen så vi kan importera komponenten
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402
from custom_components.battery_optimizer_light.coordinator import BatteryOptimizerLightCoordinator  # noqa: E402
from custom_components.battery_optimizer_light import PeakGuard  # noqa: E402
from custom_components.battery_optimizer_light.binary_sensor import BatteryLightPeakShavingActiveSensor  # noqa: E402
from homeassistant.helpers.update_coordinator import UpdateFailed  # noqa: E402

# --- MOCK DATA ---
MOCK_CONFIG = {
    "api_url": "http://test-api",
    "api_key": "12345",
    "soc_sensor": "sensor.soc",
    "grid_sensor": "sensor.grid",
    "battery_power_sensor": "sensor.bat_power"
}

@pytest.fixture
def mock_hass_instance():
    """Skapar en fejkad Home Assistant-instans."""
    hass = MagicMock()
    hass.states.get = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass

@pytest.mark.asyncio
async def test_coordinator_handles_unavailable_soc(mock_hass_instance):
    """Krav: Om SoC är otillgänglig ska vi INTE anropa API:et (för att undvika skräpdata)."""
    coordinator = BatteryOptimizerLightCoordinator(mock_hass_instance, MOCK_CONFIG)

    # Simulera att sensorn är 'unavailable'
    mock_state = MagicMock()
    mock_state.state = "unavailable"
    mock_hass_instance.states.get.return_value = mock_state

    # Vi förväntar oss att UpdateFailed kastas
    with pytest.raises(UpdateFailed) as excinfo:
        await coordinator._async_update_data()

    assert "unavailable" in str(excinfo.value)

@pytest.mark.asyncio
async def test_peak_guard_triggers_discharge(mock_hass_instance):
    """Krav: Om lasten är högre än gränsen ska batteriet urladdas."""
    coordinator = MagicMock()
    coordinator.data = {"action": "HOLD"} # Molnet säger HOLD, men PeakGuard ska ta över

    guard = PeakGuard(mock_hass_instance, MOCK_CONFIG, coordinator)

    # Setup av sensorvärden
    # Gräns: 5 kW
    limit_state = MagicMock()
    limit_state.state = "5.0"

    # Last: 7 kW (2 kW över gränsen)
    load_state = MagicMock()
    load_state.state = "7000"

    # SoC: 50% (Tillräckligt för att agera)
    soc_state = MagicMock()
    soc_state.state = "50"

    def get_state_side_effect(entity_id):
        if entity_id == "sensor.optimizer_light_peak_limit":
            return limit_state
        if entity_id == "sensor.husets_netto_last_virtuell":
            return load_state
        if entity_id == "sensor.soc":
            return soc_state
        return None

    mock_hass_instance.states.get.side_effect = get_state_side_effect

    # Kör logiken
    await guard.update("sensor.husets_netto_last_virtuell", "sensor.optimizer_light_peak_limit")

    # Verifiera att scriptet anropades
    # Behovet är 7000 - 5000 = 2000 W
    mock_hass_instance.services.async_call.assert_called_with(
        "script",
        "sonnen_force_discharge",
        service_data={"power": 2000}
    )

@pytest.mark.asyncio
async def test_peak_guard_respects_safe_limit(mock_hass_instance):
    """Krav: Om lasten är låg ska vi återgå till molnets plan (eller Auto)."""
    coordinator = MagicMock()
    coordinator.data = {"action": "IDLE"} # Molnet säger IDLE

    guard = PeakGuard(mock_hass_instance, MOCK_CONFIG, coordinator)
    guard._has_reported = True # Låtsas att vi var i ett larm-läge

    # Gräns: 5 kW, Safe limit blir 4 kW
    limit_state = MagicMock()
    limit_state.state = "5.0"
    # Last: 3 kW (Väl under safe limit)
    load_state = MagicMock()
    load_state.state = "3000"
    soc_state = MagicMock()
    soc_state.state = "50"

    def get_state_side_effect(entity_id):
        if entity_id == "sensor.optimizer_light_peak_limit":
            return limit_state
        if entity_id == "sensor.husets_netto_last_virtuell":
            return load_state
        if entity_id == "sensor.soc":
            return soc_state
        return None
    mock_hass_instance.states.get.side_effect = get_state_side_effect

    # Kör logiken
    await guard.update("sensor.husets_netto_last_virtuell", "sensor.optimizer_light_peak_limit")

    # Eftersom molnet sa IDLE, ska vi anropa auto_mode
    mock_hass_instance.services.async_call.assert_called_with(
        "script",
        "sonnen_set_auto_mode",
        service_data={}
    )

@pytest.mark.asyncio
async def test_peak_guard_disabled_by_backend(mock_hass_instance):
    """Krav: Om backend säger att peak shaving är inaktivt ska inget hända."""
    coordinator = MagicMock()
    # is_peak_shaving_active = False
    coordinator.data = {"action": "HOLD", "is_peak_shaving_active": False}

    guard = PeakGuard(mock_hass_instance, MOCK_CONFIG, coordinator)

    # Setup sensor values that WOULD trigger a peak
    limit_state = MagicMock()
    limit_state.state = "5.0"
    load_state = MagicMock()
    load_state.state = "7000" # 7kW > 5kW
    soc_state = MagicMock()
    soc_state.state = "50"

    def get_state_side_effect(entity_id):
        if entity_id == "sensor.optimizer_light_peak_limit":
            return limit_state
        if entity_id == "sensor.husets_netto_last_virtuell":
            return load_state
        if entity_id == "sensor.soc":
            return soc_state
        return None
    mock_hass_instance.states.get.side_effect = get_state_side_effect

    # Run logic
    await guard.update("sensor.husets_netto_last_virtuell", "sensor.optimizer_light_peak_limit")

    # Verify NO calls were made
    mock_hass_instance.services.async_call.assert_not_called()

def test_binary_sensor_peak_shaving_active():
    """Testar att binärsensorn läser värdet från coordinator."""
    coordinator = MagicMock()
    coordinator.api_key = "12345"

    # Fall 1: Aktivt (True)
    coordinator.data = {"is_peak_shaving_active": True}
    sensor = BatteryLightPeakShavingActiveSensor(coordinator)
    assert sensor.is_on is True
    assert sensor._attr_unique_id == "12345_peak_shaving_active"

    # Fall 2: Inaktivt (False)
    coordinator.data = {"is_peak_shaving_active": False}
    assert sensor.is_on is False

    # Fall 3: Saknas (Default True)
    coordinator.data = {}
    assert sensor.is_on is True

