from typing import Final
from homeassistant.components.climate import HVACMode, HVACAction

DOMAIN: Final = "daikin_one"

API_BASE_URL: Final = "https://integrator-api.daikinskyport.com/v1"
API_TIMEOUT: Final = 30

CONF_API_KEY: Final = "api_key"
CONF_INTEGRATOR_TOKEN: Final = "integrator_token"
CONF_EMAIL: Final = "email"

DEFAULT_SCAN_INTERVAL: Final = 60
MIN_SCAN_INTERVAL: Final = 30

# API Integer Mappings (Per OpenAPI Documentation)
# Mode: 0=Off, 1=Heat, 2=Cool, 3=Auto, 4=Emergency Heat
MODE_OFF = 0
MODE_HEAT = 1
MODE_COOL = 2
MODE_AUTO = 3
MODE_EMERGENCY_HEAT = 4

# Fan Mode: 0=Auto, 1=On, 2=Circulate
FAN_MODE_AUTO = 0
FAN_MODE_ON = 1
FAN_MODE_CIRCULATE = 2

# Temperature Limits (Standard Daikin One+ Ranges)
MIN_TEMP_FAHRENHEIT: Final = 45
MAX_TEMP_FAHRENHEIT: Final = 90
MIN_TEMP_CELSIUS: Final = 7
MAX_TEMP_CELSIUS: Final = 32
MIN_DEADBAND_CELSIUS: Final = 2.0

# Hold Status: 0=No Hold (Follow Schedule), 1=Permanent Hold, 2=Temporary Hold, 3=Away
HOLD_NONE = 0
HOLD_PERMANENT = 1
HOLD_TEMPORARY = 2
HOLD_AWAY = 3

SCHEDULE_MODE_SCHEDULED: Final = "scheduled"
SCHEDULE_MODE_MANUAL: Final = "manual"
SCHEDULE_MODE_AWAY: Final = "away"

# Equipment Status: 0=Idle, 1=Heat, 2=Cool, 3=Fan, 4=Dehumidify
EQUIPMENT_STATUS_IDLE = 0
EQUIPMENT_STATUS_HEATING = 1
EQUIPMENT_STATUS_COOLING = 2
EQUIPMENT_STATUS_FAN = 3
EQUIPMENT_STATUS_DEHUMIDIFY = 4

HVAC_MODE_MAPPING: Final = {
    MODE_OFF: HVACMode.OFF,
    MODE_HEAT: HVACMode.HEAT,
    MODE_COOL: HVACMode.COOL,
    MODE_AUTO: HVACMode.HEAT_COOL,
    MODE_EMERGENCY_HEAT: HVACMode.HEAT,
}

REVERSE_HVAC_MODE_MAPPING: Final = {
    HVACMode.OFF: MODE_OFF,
    HVACMode.HEAT: MODE_HEAT,
    HVACMode.COOL: MODE_COOL,
    HVACMode.HEAT_COOL: MODE_AUTO,
}

HVAC_ACTION_MAPPING: Final = {
    EQUIPMENT_STATUS_IDLE: HVACAction.IDLE,
    EQUIPMENT_STATUS_HEATING: HVACAction.HEATING,
    EQUIPMENT_STATUS_COOLING: HVACAction.COOLING,
    EQUIPMENT_STATUS_FAN: HVACAction.FAN,
    EQUIPMENT_STATUS_DEHUMIDIFY: HVACAction.DRYING,
}
