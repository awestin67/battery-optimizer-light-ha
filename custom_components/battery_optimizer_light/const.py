# const.py
DOMAIN = "battery_optimizer_light"

# Konfiguration
CONF_API_KEY = "api_key"
CONF_API_URL = "api_url"

# Sensorer
CONF_SOC_SENSOR = "soc_sensor"
CONF_GRID_SENSOR = "grid_sensor"    # Mätare för husets totala förbrukning (Watt)
CONF_BATTERY_POWER_SENSOR = "battery_power_sensor" # Batteriets nuvarande effekt (Watt)
CONF_VIRTUAL_LOAD_SENSOR = "virtual_load_sensor" # Virtuell last (Husets netto utan batteri)

DEFAULT_API_URL = "https://battery-light-development.up.railway.app"
