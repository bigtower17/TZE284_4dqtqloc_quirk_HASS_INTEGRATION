"""Map from manufacturer to standard clusters for electric heating thermostats."""

from typing import Final

from zigpy.profiles import zha
import zigpy.types as t
from zigpy.zcl.clusters.general import Basic, Groups, Ota, Scenes, Time
from zigpy.zcl.foundation import ZCLAttributeDef

from zhaquirks.const import (
    DEVICE_TYPE,
    ENDPOINTS,
    INPUT_CLUSTERS,
    MODELS_INFO,
    OUTPUT_CLUSTERS,
    PROFILE_ID,
)
from zhaquirks.tuya import (
    TuyaManufClusterAttributes,
    TuyaThermostat,
    TuyaThermostatCluster,
    TuyaUserInterfaceCluster,
)

# Tuya DP mapping: attr_id = dp_type * 256 + dp_number
# dp_type: 1=BOOL, 2=VALUE, 4=ENUM
MOESBHT_ENABLED_ATTR = 0x0101       # DP 1 (BOOL): ON/OFF state
MOESBHT_ENABLED_ENUM_ATTR = 0x0401  # DP 1 (ENUM): ON/OFF state (alternate type)
MOESBHT_TARGET_TEMP_ATTR = 0x0232   # DP 50 (VALUE): Target temperature
MOESBHT_TEMPERATURE_ATTR = 0x0210   # DP 16 (VALUE): Current ambient temperature
MOESBHT_SCHEDULE_MODE_ATTR = 0x017D # DP 125 (BOOL): Program mode (1=program, 0=manual)
MOESBHT_MANUAL_MODE_ATTR = 0x0166   # DP 102 (BOOL): Manual mode (synced with DP 125)
MOESBHT_RUNNING_MODE_ATTR = 0x0480  # DP 128 (ENUM): Circulator state (0=heating, 1=idle)
MOESBHT_CHILD_LOCK_ATTR = 0x0128    # DP 40 (BOOL): Child lock


class MoesBHTManufCluster(TuyaManufClusterAttributes):
    """Manufacturer Specific Cluster for _TZE284_4dqtqloc thermostat."""

    class AttributeDefs(TuyaManufClusterAttributes.AttributeDefs):
        """Attribute definitions."""

        enabled: Final = ZCLAttributeDef(
            id=MOESBHT_ENABLED_ATTR, type=t.uint8_t, is_manufacturer_specific=True
        )
        enabled_enum: Final = ZCLAttributeDef(
            id=MOESBHT_ENABLED_ENUM_ATTR, type=t.uint8_t, is_manufacturer_specific=True
        )
        target_temperature: Final = ZCLAttributeDef(
            id=MOESBHT_TARGET_TEMP_ATTR, type=t.uint32_t, is_manufacturer_specific=True
        )
        temperature: Final = ZCLAttributeDef(
            id=MOESBHT_TEMPERATURE_ATTR, type=t.uint32_t, is_manufacturer_specific=True
        )
        schedule_mode: Final = ZCLAttributeDef(
            id=MOESBHT_SCHEDULE_MODE_ATTR, type=t.uint8_t, is_manufacturer_specific=True
        )
        manual_mode: Final = ZCLAttributeDef(
            id=MOESBHT_MANUAL_MODE_ATTR, type=t.uint8_t, is_manufacturer_specific=True
        )
        running_mode: Final = ZCLAttributeDef(
            id=MOESBHT_RUNNING_MODE_ATTR, type=t.uint8_t, is_manufacturer_specific=True
        )
        child_lock: Final = ZCLAttributeDef(
            id=MOESBHT_CHILD_LOCK_ATTR, type=t.uint8_t, is_manufacturer_specific=True
        )

    async def bind(self):
        """Request device state and propagate cached values on bind."""
        result = await super().bind()

        # Request device to send all current datapoints
        try:
            await self.tuya_mcu_command(0x0001)
        except Exception:
            pass

        # Propagate cached values to thermostat cluster
        if MOESBHT_TEMPERATURE_ATTR in self._attr_cache:
            value = self._attr_cache[MOESBHT_TEMPERATURE_ATTR]
            self.endpoint.device.thermostat_bus.listener_event(
                "temperature_change", "local_temperature", value * 10,
            )

        if MOESBHT_TARGET_TEMP_ATTR in self._attr_cache:
            value = self._attr_cache[MOESBHT_TARGET_TEMP_ATTR]
            self.endpoint.device.thermostat_bus.listener_event(
                "temperature_change", "occupied_heating_setpoint", value * 10,
            )

        # Propagate ON/OFF from DP 102 (manual_mode) cache
        if MOESBHT_MANUAL_MODE_ATTR in self._attr_cache:
            value = self._attr_cache[MOESBHT_MANUAL_MODE_ATTR]
            self.endpoint.device.thermostat_bus.listener_event(
                "enabled_change", value,
            )
        else:
            # Default to Heat if no mode info available
            self.endpoint.device.thermostat_bus.listener_event(
                "enabled_change", 1,
            )

        return result

    def _update_attribute(self, attrid, value):
        super()._update_attribute(attrid, value)

        if attrid == MOESBHT_TARGET_TEMP_ATTR:
            self.endpoint.device.thermostat_bus.listener_event(
                "temperature_change",
                "occupied_heating_setpoint",
                value * 10,
            )
        elif attrid == MOESBHT_TEMPERATURE_ATTR:
            self.endpoint.device.thermostat_bus.listener_event(
                "temperature_change",
                "local_temperature",
                value * 10,
            )
        elif attrid in (MOESBHT_ENABLED_ATTR, MOESBHT_ENABLED_ENUM_ATTR):
            # DP 1: ON/OFF → system_mode
            self.endpoint.device.thermostat_bus.listener_event(
                "enabled_change", value,
            )
        elif attrid == MOESBHT_SCHEDULE_MODE_ATTR:
            if value == 0:
                self.endpoint.device.thermostat_bus.listener_event(
                    "program_change", "manual",
                )
            else:
                self.endpoint.device.thermostat_bus.listener_event(
                    "program_change", "scheduled",
                )
        elif attrid == MOESBHT_MANUAL_MODE_ATTR:
            # DP 102: actual ON/OFF control on this device
            # 0 = off (manual/eco), 1 = on (scheduled/comfort)
            self.endpoint.device.thermostat_bus.listener_event(
                "enabled_change", value,
            )
        elif attrid == MOESBHT_RUNNING_MODE_ATTR:
            # DP 128: Unreliable on this device (always 0).
            # state_change is a no-op; running state is computed from temps.
            self.endpoint.device.thermostat_bus.listener_event(
                "state_change", value,
            )
        elif attrid == MOESBHT_CHILD_LOCK_ATTR:
            self.endpoint.device.ui_bus.listener_event("child_lock_change", value)


class MoesBHTThermostat(TuyaThermostatCluster):
    """Thermostat cluster for _TZE284_4dqtqloc."""

    def map_attribute(self, attribute, value):
        """Map standardized attribute value to dict of manufacturer values."""

        if attribute == "occupied_heating_setpoint":
            return {MOESBHT_TARGET_TEMP_ATTR: round(value / 10)}
        elif attribute == "system_mode":
            if value == self.SystemMode.Off:
                return {MOESBHT_MANUAL_MODE_ATTR: 0, MOESBHT_SCHEDULE_MODE_ATTR: 0}
            elif value == self.SystemMode.Heat:
                return {MOESBHT_MANUAL_MODE_ATTR: 1, MOESBHT_SCHEDULE_MODE_ATTR: 1}

        return super().map_attribute(attribute, value)

    def _recalculate_running_state(self):
        """Compute running state from setpoint vs current temperature.

        DP 128 is unreliable on this device (always reports 0), so
        running state is derived from temperature comparison instead.
        """
        local_temp = self._attr_cache.get(
            self.attributes_by_name["local_temperature"].id
        )
        setpoint = self._attr_cache.get(
            self.attributes_by_name["occupied_heating_setpoint"].id
        )
        system_mode = self._attr_cache.get(
            self.attributes_by_name["system_mode"].id
        )

        if local_temp is None or setpoint is None:
            return

        # Default to Heat if system_mode hasn't been set yet
        if system_mode is None:
            system_mode = self.SystemMode.Heat

        if system_mode == self.SystemMode.Heat and setpoint > local_temp:
            running_state = self.RunningState.Heat_State_On
            running_mode = self.RunningMode.Heat
        else:
            running_state = self.RunningState.Idle
            running_mode = self.RunningMode.Off

        self._update_attribute(
            self.attributes_by_name["running_state"].id, running_state,
        )
        self._update_attribute(
            self.attributes_by_name["running_mode"].id, running_mode,
        )

    def temperature_change(self, attr, value):
        """Handle temperature changes and recalculate running state."""
        super().temperature_change(attr, value)
        self._recalculate_running_state()

    def state_change(self, value):
        """DP 128 running state - ignored.

        This device does not reliably report running state via DP 128
        (always sends 0). Running state is computed from temperature
        comparison instead, in _recalculate_running_state().
        """

    def enabled_change(self, value):
        """System mode change from ON/OFF DP."""
        if value == 0:
            mode = self.SystemMode.Off
        else:
            mode = self.SystemMode.Heat
        self._update_attribute(self.attributes_by_name["system_mode"].id, mode)
        self._recalculate_running_state()

    def program_change(self, mode):
        """Programming mode change."""
        if mode == "manual":
            value = self.ProgrammingOperationMode.Simple
        else:
            value = self.ProgrammingOperationMode.Schedule_programming_mode

        self._update_attribute(
            self.attributes_by_name["programing_oper_mode"].id, value,
        )


class MoesBHTUserInterface(TuyaUserInterfaceCluster):
    """HVAC User interface cluster for _TZE284_4dqtqloc."""

    _CHILD_LOCK_ATTR = MOESBHT_CHILD_LOCK_ATTR


class Thermostat4dqtqloc(TuyaThermostat):
    """Tuya thermostat _TZE284_4dqtqloc."""

    signature = {
        MODELS_INFO: [
            ("_TZE284_4dqtqloc", "TS0601"),
        ],
        ENDPOINTS: {
            1: {
                PROFILE_ID: zha.PROFILE_ID,
                DEVICE_TYPE: zha.DeviceType.SMART_PLUG,
                INPUT_CLUSTERS: [
                    Basic.cluster_id,
                    Groups.cluster_id,
                    Scenes.cluster_id,
                    0xED00,
                    TuyaManufClusterAttributes.cluster_id,
                ],
                OUTPUT_CLUSTERS: [Time.cluster_id, Ota.cluster_id],
            }
        },
    }

    replacement = {
        ENDPOINTS: {
            1: {
                PROFILE_ID: zha.PROFILE_ID,
                DEVICE_TYPE: zha.DeviceType.THERMOSTAT,
                INPUT_CLUSTERS: [
                    Basic.cluster_id,
                    Groups.cluster_id,
                    Scenes.cluster_id,
                    MoesBHTManufCluster,
                    MoesBHTThermostat,
                    MoesBHTUserInterface,
                ],
                OUTPUT_CLUSTERS: [Time.cluster_id, Ota.cluster_id],
            }
        }
    }
