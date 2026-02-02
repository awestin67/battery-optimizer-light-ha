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

import logging
import aiohttp
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed  # type: ignore

_LOGGER = logging.getLogger(__name__)

class BatteryOptimizerLightCoordinator(DataUpdateCoordinator):
    """Hanterar kommunikationen för Light-versionen."""

    def __init__(self, hass, config):
        super().__init__(
            hass,
            _LOGGER,
            name="Battery Optimizer Light",
            update_interval=timedelta(minutes=5),
        )
        self.api_url = f"{config['api_url'].rstrip('/')}/signal"
        self.api_key = config['api_key']
        self.soc_entity = config['soc_sensor']
        self.consumption_forecast_entity = config.get("consumption_forecast_sensor")

    async def _async_update_data(self):
        """Körs var 5:e minut."""
        try:
            # 1. Hämta SOC
            soc = None
            soc_state = self.hass.states.get(self.soc_entity)

            # Kontrollera om sensorn är giltig
            if soc_state and soc_state.state not in ["unknown", "unavailable"]:
                try:
                    soc = float(soc_state.state)
                except ValueError:
                    raise UpdateFailed(f"SoC value is not a number: {soc_state.state}") from None
            else:
                # VIKTIGT: Om sensorn är otillgänglig, avbryt istället för att gissa!
                # Detta gör att inget skickas till backend denna gång.
                # Loggar en varning i HA men förstör inte din graf.
                raise UpdateFailed(f"SoC entity {self.soc_entity} is unavailable. Skipping update.")

            is_solar_override = False
            if hasattr(self, "peak_guard") and self.peak_guard:
                is_solar_override = self.peak_guard.is_solar_override

            # 3. Hämta förbrukningsprognos (Valfritt)
            consumption_forecast = 0.0
            if self.consumption_forecast_entity:
                forecast_state = self.hass.states.get(self.consumption_forecast_entity)
                if forecast_state and forecast_state.state not in ["unknown", "unavailable"]:
                    try:
                        consumption_forecast = float(forecast_state.state)
                    except ValueError:
                        pass  # Ignorera om värdet inte är ett tal

            # 2. Payload (Endast det backend behöver)
            payload = {
                "api_key": self.api_key,
                "soc": soc,
                "is_solar_override": is_solar_override,
                "consumption_forecast_kwh": consumption_forecast
            }

            _LOGGER.debug(f"Light-Request: {payload}")

            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, timeout=10) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise UpdateFailed(f"Server {response.status}: {text}")

                    return await response.json()

        except Exception as err:
            _LOGGER.error(f"Light-Error: {err}")
            raise UpdateFailed(f"Connection error: {err}") from err
