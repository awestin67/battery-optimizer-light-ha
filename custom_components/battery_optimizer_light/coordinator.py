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

            # 2. Payload (Endast det backend behöver)
            payload = {
                "api_key": self.api_key,
                "soc": soc,
                "is_solar_override": is_solar_override
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
