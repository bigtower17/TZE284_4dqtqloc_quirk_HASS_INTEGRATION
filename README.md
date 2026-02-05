 # ZHA Quirk for Tuya TS0601 `_TZE284_4dqtqloc` Thermostat

 Custom [ZHA](https://www.home-assistant.io/integrations/zha/) quirk for the Tuya TS0601 thermostat with manufacturer code `_TZE284_4dqtqloc`. This device is a Zigbee thermostat with a relay that controls a
 circulator pump for hydronic (water-based) heating systems.

 ## Features

 - **ON/OFF control** from Home Assistant and physical button sync
 - **Target temperature** control with live feedback
 - **Running state** display (heating / idle) computed from temperature comparison
 - **Child lock** support
 - **System mode** (Heat / Off) mapped to the device's native manual/scheduled mode

 ## Device Information

 | Field | Value |
 |---|---|
 | Manufacturer | `_TZE284_4dqtqloc` |
 | Model | `TS0601` |
 | Device Type | Smart Plug (0x0051) |
 | Zigbee Profile | ZHA (0x0104) |
 | Input Clusters | Basic, Groups, Scenes, 0xED00, 0xEF00 (Tuya) |
 | Output Clusters | Time, OTA |

 ## Installation

 1. Copy `ts0601_thermostat_4dqtqloc.py` to your ZHA custom quirks directory:
    ```
    /config/custom_zha_quirks/ts0601_thermostat_4dqtqloc.py
    ```

 2. Make sure custom quirks are enabled in your ZHA configuration (`configuration.yaml`):
    ```yaml
    zha:
      custom_quirks_path: /config/custom_zha_quirks/
    ```

 3. Restart Home Assistant.

 4. Remove and re-add the device if it was previously paired.

 ## Tuya Datapoint Mapping

 This device communicates via the Tuya-specific cluster `0xEF00` using datapoints (DPs) instead of standard ZCL attributes. The quirk translates between Tuya DPs and the ZCL Thermostat cluster (0x0201).

 | DP | Type | Quirk Attribute ID | Description |
 |---|---|---|---|
 | 1 | BOOL | 0x0101 | ON/OFF state (not used by this device) |
 | 16 | VALUE | 0x0210 | Current ambient temperature (tenths of °C) |
 | 40 | BOOL | 0x0128 | Child lock |
 | 50 | VALUE | 0x0232 | Target temperature (tenths of °C) |
 | 102 | BOOL | 0x0166 | Manual mode — **actual ON/OFF control** |
 | 125 | BOOL | 0x017D | Schedule mode (synced with DP 102) |
 | 128 | ENUM | 0x0480 | Running mode (unreliable, always reports 0) |

 ### Key Findings

 **DP 102 is the ON/OFF control**, not DP 1. When the physical button is pressed:
 - DP 102 = 0 → device enters manual/eco mode (low setpoint ~15°C, circulator off)
 - DP 102 = 1 → device enters scheduled/comfort mode (normal setpoint, circulator on)

 The device **never reports DP 1** in any form. DP 128 (running mode) is **always 0** regardless of actual circulator state and cannot be used for running state detection.

 ## How It Works

 ### System Mode (ON/OFF)

 The quirk maps ZCL `system_mode` to DP 102:
 - **Heat** → sends DP 102 = 1 + DP 125 = 1 (scheduled mode)
 - **Off** → sends DP 102 = 0 + DP 125 = 0 (manual mode)

 Physical button presses are detected through incoming DP 102 changes and update `system_mode` accordingly.

 ### Running State

 Since DP 128 is unreliable on this device, running state is **computed from temperature comparison**:
 - `system_mode == Heat` AND `setpoint > current_temperature` → **Heating**
 - Otherwise → **Idle**

 This updates automatically whenever the setpoint, current temperature, or system mode changes.

 ### Temperature

 - Current temperature is read from DP 16 and mapped to `local_temperature`
 - Target temperature is read from DP 50 and mapped to `occupied_heating_setpoint`
 - Temperature changes from HA are sent via DP 50

 ## Exposed Entities

 | Entity | Type | Description |
 |---|---|---|
 | `climate.*` | Climate | Main thermostat control (Heat/Off, temperature) |
 | `sensor.*_hvac_action` | Sensor | Current HVAC action (heating/idle) |
 | `update.*_firmware` | Update | OTA firmware update |

 ## Troubleshooting

 - **Device shows no entities after pairing**: Make sure the quirk file is in the correct directory and HA was restarted (not just the device reconfigured). Check logs for `Loading custom quirk module
 'ts0601_thermostat_4dqtqloc'`.
 - **MoesBHTThermostat error during reconfiguration**: This is normal. Tuya devices do not support standard ZCL reporting configuration. The error can be ignored.
 - **Device always shows "idle"**: Verify that `system_mode` is set to Heat. If the device was physically turned off, DP 102 = 0 sets `system_mode` to Off.
 - **ON/OFF from HA doesn't work**: Make sure you restarted HA after placing the quirk file. The quirk sends DP 102 for ON/OFF, not DP 1.

 ## Technical Notes

 - Attribute IDs follow the Tuya convention: `attr_id = dp_type * 256 + dp_number` (dp_type: 1=BOOL, 2=VALUE, 4=ENUM)
 - The device manages two internal setpoints (comfort and eco) and switches between them based on DP 102
 - DP 125 (schedule_mode) is sent alongside DP 102 for consistency but DP 102 is the primary control
 - The `bind()` method requests all current datapoints from the device and propagates cached values to the thermostat cluster on startup

 ## License

 This quirk is provided as-is for the Home Assistant community. Feel free to use, modify, and redistribute.
