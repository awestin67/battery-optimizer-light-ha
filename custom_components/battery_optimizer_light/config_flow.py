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

import voluptuous as vol  # type: ignore
from homeassistant import config_entries # type: ignore
from homeassistant.core import callback  # type: ignore
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
    TextSelectorConfig,
)
from .const import (
    DOMAIN,
    CONF_API_URL,
    DEFAULT_API_URL,
    CONF_API_KEY,
    CONF_SOC_SENSOR,
    CONF_GRID_SENSOR,
    CONF_GRID_SENSOR_INVERT,
    CONF_BATTERY_POWER_SENSOR,
    CONF_BATTERY_STATUS_SENSOR,
    CONF_BATTERY_STATUS_KEYWORDS,
    CONF_VIRTUAL_LOAD_SENSOR,
    CONF_CONSUMPTION_FORECAST_SENSOR,
    DEFAULT_BATTERY_STATUS_KEYWORDS,
)

class BatteryOptimizerLightConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Battery Optimizer Light", data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_API_URL, default=DEFAULT_API_URL): TextSelector(
                TextSelectorConfig(type="url")
            ),
            vol.Required(CONF_API_KEY): TextSelector(),
            vol.Required(CONF_SOC_SENSOR): EntitySelector(
                EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_GRID_SENSOR): EntitySelector(
                EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Optional(CONF_GRID_SENSOR_INVERT, default=False): bool,
            vol.Required(CONF_BATTERY_POWER_SENSOR): EntitySelector(
                EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Optional(CONF_BATTERY_STATUS_SENSOR): EntitySelector(
                EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(CONF_BATTERY_STATUS_KEYWORDS, default=DEFAULT_BATTERY_STATUS_KEYWORDS): TextSelector(
                TextSelectorConfig(multiline=True)
            ),
            vol.Optional(CONF_VIRTUAL_LOAD_SENSOR): EntitySelector(
                EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Optional(CONF_CONSUMPTION_FORECAST_SENSOR): EntitySelector(
                EntitySelectorConfig(domain="sensor")
            ),
        })

        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return BatteryOptimizerLightOptionsFlow(config_entry)

class BatteryOptimizerLightOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            # SÄKERHETSÅTGÄRD: Rensa mellanslag från strängar
            for key, value in user_input.items():
                if isinstance(value, str):
                    user_input[key] = value.strip()

            # HÄR ÄR FIXEN: Vi skriver över grundkonfigurationen direkt
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data=user_input
            )
            return self.async_create_entry(title="", data={})

        # Vi läser nuvarande värden direkt från grunddatan
        data = self._config_entry.data

        schema = vol.Schema({
            vol.Required(CONF_API_URL, default=data.get(CONF_API_URL, DEFAULT_API_URL)): TextSelector(
                TextSelectorConfig(type="url")
            ),
            vol.Required(CONF_API_KEY, default=data.get(CONF_API_KEY, "")): TextSelector(),
            vol.Required(CONF_SOC_SENSOR, default=data.get(CONF_SOC_SENSOR)): EntitySelector(
                EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_GRID_SENSOR, default=data.get(CONF_GRID_SENSOR)): EntitySelector(
                EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Optional(CONF_GRID_SENSOR_INVERT, default=data.get(CONF_GRID_SENSOR_INVERT, False)): bool,
            vol.Required(CONF_BATTERY_POWER_SENSOR, default=data.get(CONF_BATTERY_POWER_SENSOR)): EntitySelector(
                EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Optional(CONF_BATTERY_STATUS_SENSOR, default=data.get(CONF_BATTERY_STATUS_SENSOR)): EntitySelector(
                EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(CONF_BATTERY_STATUS_KEYWORDS, default=data.get(
                CONF_BATTERY_STATUS_KEYWORDS, DEFAULT_BATTERY_STATUS_KEYWORDS
            )): TextSelector(TextSelectorConfig(multiline=True)),
            vol.Optional(CONF_VIRTUAL_LOAD_SENSOR, default=data.get(CONF_VIRTUAL_LOAD_SENSOR)): EntitySelector(
                EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Optional(CONF_CONSUMPTION_FORECAST_SENSOR, default=data.get(
                CONF_CONSUMPTION_FORECAST_SENSOR
            )): EntitySelector(
                EntitySelectorConfig(domain="sensor")
            ),
        })

        return self.async_show_form(step_id="init", data_schema=schema)
