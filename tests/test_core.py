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
mock_sensor.SensorDeviceClass = MagicMock()
mock_sensor.SensorStateClass = MagicMock()
sys.modules["homeassistant.components.sensor"] = mock_sensor

# Lägg till rotmappen i sökvägen så vi kan importera komponenten
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402
from custom_components.battery_optimizer_light.coordinator import BatteryOptimizerLightCoordinator  # noqa: E402
from custom_components.battery_optimizer_light import PeakGuard  # noqa: E402
from custom_components.battery_optimizer_light.sensor import BatteryLightStatusSensor, BatteryLightVirtualLoadSensor  # noqa: E402

# --- MOCK DATA ---
MOCK_CONFIG = {
    "api_url": "http://test-api",
    "api_key": "12345",
    "soc_sensor": "sensor.soc",
    "grid_sensor": "sensor.grid",
    "battery_power_sensor": "sensor.bat_power",
    "virtual_load_sensor": "sensor.husets_netto_last_virtuell",
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

    # Mocka _report_peak för att verifiera argument och undvika nätverksanrop
    guard._report_peak = AsyncMock()

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

    # Verifiera att _report_peak anropades med (current_load, limit_w)
    guard._report_peak.assert_called_with(7000.0, 5000.0)

@pytest.mark.asyncio
async def test_peak_guard_respects_safe_limit(mock_hass_instance):
    """Krav: Om lasten är låg ska vi återgå till molnets plan (eller Auto)."""
    coordinator = MagicMock()
    coordinator.data = {"action": "IDLE"} # Molnet säger IDLE

    guard = PeakGuard(mock_hass_instance, MOCK_CONFIG, coordinator)
    guard._has_reported = True # Låtsas att vi var i ett larm-läge

    # Mocka _report_peak_clear för att verifiera argument
    guard._report_peak_clear = AsyncMock()

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

    # Verifiera att _report_peak_clear anropades med (current_load, limit_w)
    guard._report_peak_clear.assert_called_with(3000.0, 5000.0)

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

def test_status_sensor():
    """Testar att status-sensorn visar rätt text (Disabled/Monitoring/Triggered)."""
    coordinator = MagicMock()
    coordinator.api_key = "12345"
    coordinator.data = {"is_peak_shaving_active": True}

    # Mocka peak_guard på coordinatorn
    peak_guard = MagicMock()
    peak_guard.is_active = False
    peak_guard.in_maintenance = False
    peak_guard.maintenance_reason = None
    coordinator.peak_guard = peak_guard

    sensor = BatteryLightStatusSensor(coordinator)

    # Fall 1: Monitoring (Aktiv men inte triggad)
    assert sensor.state == "Monitoring"
    assert sensor.icon == "mdi:shield-search"

    # Fall 2: Triggered
    peak_guard.is_active = True
    assert sensor.state == "Triggered"
    assert sensor.icon == "mdi:shield-alert"

    # Fall 3: Disabled
    coordinator.data = {"is_peak_shaving_active": False}
    assert sensor.state == "Disabled"
    assert sensor.icon == "mdi:shield-off"

    # Fall 4: Maintenance
    coordinator.data = {"is_peak_shaving_active": True}
    peak_guard.is_active = False
    peak_guard.in_maintenance = True
    peak_guard.maintenance_reason = "Service Mode"
    assert sensor.state == "Maintenance mode detected (Service Mode). Pausing control."
    assert sensor.icon == "mdi:tools"

@pytest.mark.asyncio
async def test_peak_guard_reports_failure_on_overload(mock_hass_instance):
    """Krav: Om behovet överstiger max växelriktareffekt ska failure rapporteras."""
    coordinator = MagicMock()
    # Sätt max_discharge_kw till 3.3 kW (3300 W)
    coordinator.data = {"action": "HOLD", "max_discharge_kw": 3.3}

    guard = PeakGuard(mock_hass_instance, MOCK_CONFIG, coordinator)

    # Vi simulerar att vi redan är i ett peak-läge (har rapporterat start)
    guard._has_reported = True

    # Mocka _report_peak_failure metoden för att verifiera anrop utan att göra nätverksanrop
    guard._report_peak_failure = AsyncMock()

    # Setup sensorvärden
    # Gräns: 5 kW
    limit_state = MagicMock()
    limit_state.state = "5.0"

    # Last: 9 kW. Behov = 9000 - 5000 = 4000 W.
    # Max inverter = 3300 W.
    # 4000 > 3300 -> Failure.
    load_state = MagicMock()
    load_state.state = "9000"

    # SoC: 50%
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

    # Verifiera att _report_peak_failure anropades med (current_load, limit_w)
    guard._report_peak_failure.assert_called_with(9000.0, 5000.0)

@pytest.mark.asyncio
async def test_solar_override_reports_to_cloud(mock_hass_instance):
    """Krav: När Solar Override aktiveras ska det rapporteras till molnet."""
    coordinator = MagicMock()
    coordinator.data = {"action": "HOLD"} # Molnet säger HOLD

    guard = PeakGuard(mock_hass_instance, MOCK_CONFIG, coordinator)

    # Mocka rapport-metoden
    guard._report_solar_override = AsyncMock()

    # Setup sensorer
    limit_state = MagicMock()
    limit_state.state = "5.0"

    # Last: -500 W (Export)
    load_state = MagicMock()
    load_state.state = "-500"

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

    # Kör update
    await guard.update("sensor.husets_netto_last_virtuell", "sensor.optimizer_light_peak_limit")

    # Verifiera att override aktiverades och rapport skickades
    assert guard.is_solar_override is True
    guard._report_solar_override.assert_called_with(-500.0, 5000.0)

@pytest.mark.asyncio
async def test_coordinator_sends_solar_override_flag(mock_hass_instance):
    """Krav: Coordinator ska skicka med is_solar_override flaggan till backend."""
    coordinator = BatteryOptimizerLightCoordinator(mock_hass_instance, MOCK_CONFIG)

    # Mocka SoC state
    mock_state = MagicMock()
    mock_state.state = "50"
    mock_hass_instance.states.get.return_value = mock_state

    # Mocka PeakGuard och sätt override till True
    peak_guard = MagicMock()
    peak_guard.is_solar_override = True
    coordinator.peak_guard = peak_guard

    # Mocka aiohttp session och response
    # Vi patchar där den används: custom_components.battery_optimizer_light.coordinator.aiohttp.ClientSession
    with patch("custom_components.battery_optimizer_light.coordinator.aiohttp.ClientSession") as mock_session_cls:
        mock_session = mock_session_cls.return_value
        mock_session.__aenter__.return_value = mock_session

        mock_post = mock_session.post.return_value
        mock_post.__aenter__.return_value = mock_post
        mock_post.status = 200
        mock_post.json = AsyncMock(return_value={"status": "ok"})

        await coordinator._async_update_data()

        # Verifiera anropet
        _, kwargs = mock_session.post.call_args
        payload = kwargs['json']


        assert payload["is_solar_override"] is True
        assert payload["soc"] == 50.0

@pytest.mark.asyncio
async def test_peak_guard_calculates_load_with_inverted_grid(mock_hass_instance):
    """Krav: Om grid_sensor_invert är True ska grid-värdet negeras vid beräkning."""
    # Konfiguration med inverterad grid sensor och INGEN virtuell sensor
    config = MOCK_CONFIG.copy()
    config["grid_sensor_invert"] = True
    config["virtual_load_sensor"] = None

    coordinator = MagicMock()
    coordinator.data = {"action": "HOLD"}

    guard = PeakGuard(mock_hass_instance, config, coordinator)

    # Setup sensorer
    limit_state = MagicMock()
    limit_state.state = "5.0"

    # Grid: 5000 W (Positivt). Med invert=True betyder detta Export (-5000 W).
    grid_state = MagicMock()
    grid_state.state = "5000"

    # Batteri: 0 W
    bat_state = MagicMock()
    bat_state.state = "0"

    def get_state_side_effect(entity_id):
        if entity_id == "sensor.optimizer_light_peak_limit":
            return limit_state
        if entity_id == "sensor.grid":
            return grid_state
        if entity_id == "sensor.bat_power":
            return bat_state
        return None
    mock_hass_instance.states.get.side_effect = get_state_side_effect

    # Kör update utan virtuell sensor-ID
    await guard.update(None, "sensor.optimizer_light_peak_limit")

    # Om inverteringen fungerade är lasten -5000. -5000 < -200 -> Solar Override.
    assert guard.is_solar_override is True

def test_virtual_load_sensor_calculation():
    """Testar att den virtuella lastsensorn räknar rätt."""
    coordinator = MagicMock()
    coordinator.api_key = "12345"
    coordinator.hass = MagicMock()

    # Mocka config via peak_guard
    peak_guard = MagicMock()
    peak_guard.config = {
        "grid_sensor": "sensor.grid",
        "battery_power_sensor": "sensor.bat",
        "grid_sensor_invert": False,
        "virtual_load_sensor": None
    }
    coordinator.peak_guard = peak_guard

    sensor = BatteryLightVirtualLoadSensor(coordinator)

    # Mocka states
    grid_state = MagicMock()
    grid_state.state = "5000"
    bat_state = MagicMock()
    bat_state.state = "1000"

    def get_state_side_effect(entity_id):
        if entity_id == "sensor.grid":
            return grid_state
        if entity_id == "sensor.bat":
            return bat_state
        return None
    coordinator.hass.states.get.side_effect = get_state_side_effect

    # Fall 1: Normal beräkning (5000 + 1000 = 6000)
    assert sensor.state == 6000

    # Fall 2: Inverterad grid
    peak_guard.config["grid_sensor_invert"] = True
    # (-5000 + 1000 = -4000)
    assert sensor.state == -4000

@pytest.mark.asyncio
async def test_peak_guard_pauses_on_custom_keyword(mock_hass_instance):
    """Krav: Användaren ska kunna konfigurera egna nyckelord för underhåll."""
    config = MOCK_CONFIG.copy()
    config["battery_status_sensor"] = "sensor.generic_battery_status"
    # Konfigurera ett eget nyckelord
    config["battery_status_keywords"] = "service mode, critical error"

    coordinator = MagicMock()
    coordinator.data = {"action": "HOLD"}

    guard = PeakGuard(mock_hass_instance, config, coordinator)

    # Setup sensorer
    limit_state = MagicMock()
    limit_state.state = "5.0"

    # Status: "Service Mode" (matchar vårt egna nyckelord)
    status_state = MagicMock()
    status_state.state = "System is in Service Mode"

    def get_state_side_effect(entity_id):
        if entity_id == "sensor.optimizer_light_peak_limit":
            return limit_state
        if entity_id == "sensor.generic_battery_status":
            return status_state
        return None
    mock_hass_instance.states.get.side_effect = get_state_side_effect

    # Kör update
    await guard.update(None, "sensor.optimizer_light_peak_limit")

    # Verifiera att flaggan sattes
    assert guard._in_maintenance is True
