import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig
from .const import *

class BatteryOptimizerLightConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Battery Optimizer Light", data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_API_URL, default=DEFAULT_API_URL): str,
            vol.Required(CONF_API_KEY): str,
            vol.Required(CONF_SOC_SENSOR): EntitySelector(EntitySelectorConfig(domain="sensor", device_class="battery")),
            vol.Required(CONF_GRID_SENSOR): EntitySelector(EntitySelectorConfig(domain="sensor", device_class="power")),
            vol.Required(CONF_BATTERY_POWER_SENSOR): EntitySelector(EntitySelectorConfig(domain="sensor", device_class="power")),
        })

        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return BatteryOptimizerLightOptionsFlow(config_entry)

class BatteryOptimizerLightOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            # SÄKERHETSÅTGÄRD: Rensa mellanslag från strängar
            for key, value in user_input.items():
                if isinstance(value, str):
                    user_input[key] = value.strip()

            # HÄR ÄR FIXEN: Vi skriver över grundkonfigurationen direkt
            self.hass.config_entries.async_update_entry(
                self.config_entry, 
                data=user_input
            )
            return self.async_create_entry(title="", data={})
        
        # Vi läser nuvarande värden direkt från grunddatan
        data = self.config_entry.data
        
        schema = vol.Schema({
            vol.Required(CONF_API_URL, default=data.get(CONF_API_URL, DEFAULT_API_URL)): str,
            vol.Required(CONF_API_KEY, default=data.get(CONF_API_KEY, "")): str,
            vol.Required(CONF_SOC_SENSOR, default=data.get(CONF_SOC_SENSOR)): EntitySelector(EntitySelectorConfig(domain="sensor", device_class="battery")),
            vol.Required(CONF_GRID_SENSOR, default=data.get(CONF_GRID_SENSOR)): EntitySelector(EntitySelectorConfig(domain="sensor", device_class="power")),
            vol.Required(CONF_BATTERY_POWER_SENSOR, default=data.get(CONF_BATTERY_POWER_SENSOR)): EntitySelector(EntitySelectorConfig(domain="sensor", device_class="power")),
        })

        return self.async_show_form(step_id="init", data_schema=schema)