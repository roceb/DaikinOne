# Daikin One+ for Home Assistant

A Home Assistant custom component for Daikin One+ thermostats using the official Daikin Integrator API.

This integration was vibe coded with AI assistance using the official Daikin One+ OpenAPI documentation available at https://www.daikinone.com/openapi/documentation/index.html.

## Requirements

- Daikin One+ thermostat
- Daikin integrator API key and integrator token (obtained from the Daikin developer portal)
- Home Assistant 2024.12.0 or newer

## Installation

1. Copy the `daikin_one` folder into your `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration via Settings > Devices & Services > Add Integration > Daikin One+.

## Configuration

Provide your email, API key, and integrator token during setup. The scan interval can be adjusted in the integration options (minimum 30 seconds).

## Features

- Climate control (heat, cool, auto, off)
- Fan mode control
- Schedule, manual, and away presets
- Temperature, humidity, and air quality sensors
- Equipment status and alert binary sensors
- Humidifier and dehumidifier switches

## Disclaimer

This is an unofficial integration. Use at your own risk.
