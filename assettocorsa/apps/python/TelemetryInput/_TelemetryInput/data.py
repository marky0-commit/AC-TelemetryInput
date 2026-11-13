import ac
import acsys
import codecs
import json
import os
import sys

_apps_py_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
for _p in (_apps_py_dir, os.path.join(_apps_py_dir, 'RaceEssentials'), os.path.join(_apps_py_dir, 'system')):
    if _p not in sys.path:
        sys.path.append(_p)

try:
    # RaceEssentials uses this source first.
    from raceessentials_lib.sim_info import info as _SIM_INFO
except Exception:
    try:
        from sim_info import info as _SIM_INFO
    except Exception:
        try:
            from system.sim_info import info as _SIM_INFO
        except Exception:
            _SIM_INFO = None

_CS = acsys.CS
_STATE = ac.getCarState
_CS_FUEL_KEYS = ('Fuel', 'FuelL', 'FuelLiter', 'FuelLiters')
_CS_LAPCOUNT = getattr(_CS, 'LapCount', None)


class TelemetryData:
    """
    Reads live telemetry from Assetto Corsa via the ac / acsys API.

    Call update_globals() at low frequency (~10 Hz) for data that
    rarely changes, and update_telemetry() at the configured sample
    rate for per-frame inputs.
    """

    car_id = 0
    throttle = 0.0
    brake = 0.0
    clutch = 0.0
    steering = 0.0
    steering_norm = 0.5
    gear_str = 'N'
    speed_kph = 0.0
    speed_mph = 0.0
    ffb = 0.0
    ffb_norm = 0.0
    fuel_liters = 0.0
    fuel_per_lap = 0.0
    est_laps = 0.0
    rpm = 0.0
    _peak_rpm = 3000.0
    max_power_rpm = 0.0
    _car_name = ''
    _last_lap_count = -1
    _lap_fuel_start = 0.0

    def __init__(self, config):
        self.config = config
        self.update_globals()
        self.update_telemetry()

    def _load_max_power_rpm(self, car_name):
        """Load max-power RPM from car UI power curve (RaceEssentials style)."""
        if not car_name:
            self.max_power_rpm = 0.0
            return

        ui_path = os.path.join('content', 'cars', car_name, 'ui', 'ui_car.json')
        best_power = -1
        best_rpm = 0.0

        for enc in ('utf-8-sig', 'latin-1'):
            try:
                with codecs.open(ui_path, 'r', enc) as f:
                    raw = f.read().replace('\r', '').replace('\n', '').replace('\t', '')
                data = json.loads(raw)
                for step in data.get('powerCurve', []):
                    try:
                        rpm = float(step[0])
                        power = float(step[1])
                    except Exception:
                        continue
                    if power >= best_power:
                        best_power = power
                        best_rpm = rpm
                self.max_power_rpm = best_rpm if best_rpm > 0 else 0.0
                return
            except Exception:
                pass

        self.max_power_rpm = 0.0

    def update_globals(self):
        """Refresh slowly-changing data (focused car)."""
        self.car_id = ac.getFocusedCar()
        try:
            car_name = ac.getCarName(self.car_id)
        except Exception:
            car_name = ''

        if car_name != self._car_name:
            self._car_name = car_name
            self._peak_rpm = 3000.0
            self._load_max_power_rpm(car_name)
            self.fuel_per_lap = 0.0
            self.est_laps = 0.0
            self._last_lap_count = -1
            self._lap_fuel_start = 0.0

    def _read_fuel_liters(self, cid, get_state):
        # 1) RaceEssentials-style source
        if _SIM_INFO is not None:
            try:
                v = float(_SIM_INFO.physics.fuel)
                if v >= 0.0:
                    return v
            except Exception:
                pass

        # 2) AC car state fallbacks
        for fuel_key in _CS_FUEL_KEYS:
            fuel_state = getattr(_CS, fuel_key, None)
            if fuel_state is None:
                continue
            try:
                v = float(get_state(cid, fuel_state))
                if v >= 0.0:
                    return v
            except Exception:
                pass
            try:
                v = float(get_state(0, fuel_state))
                if v >= 0.0:
                    return v
            except Exception:
                pass

        return 0.0

    def update_telemetry(self):
        """Refresh high-frequency input / motion data."""
        cid = self.car_id
        get_state = _STATE

        self.throttle = get_state(cid, _CS.Gas)
        self.brake    = get_state(cid, _CS.Brake)
        # AC clutch: 1.0 = fully released, 0.0 = fully pressed
        self.clutch   = 1.0 - get_state(cid, _CS.Clutch)

        self.steering = get_state(cid, _CS.Steer)
        sens = self.config.steering_sensitivity or 720
        steering_norm = 0.5 - (self.steering / sens)
        if steering_norm < 0.0:
            steering_norm = 0.0
        elif steering_norm > 1.0:
            steering_norm = 1.0
        self.steering_norm = steering_norm

        # Gear: 0=Reverse, 1=Neutral, 2=1st, 3=2nd …
        gear = get_state(cid, _CS.Gear)
        if gear == 0:
            self.gear_str = 'R'
        elif gear == 1:
            self.gear_str = 'N'
        else:
            self.gear_str = str(gear - 1)

        self.speed_kph = get_state(cid, _CS.SpeedKMH)
        self.speed_mph = get_state(cid, _CS.SpeedMPH)
        self.ffb = get_state(cid, _CS.LastFF)
        abs_ffb = abs(self.ffb)
        self.ffb_norm = abs_ffb if abs_ffb < 1.0 else 1.0

        self.fuel_liters = max(0.0, self._read_fuel_liters(cid, get_state))

        # Estimated laps from average fuel consumption per completed lap.
        lap_count = 0
        if _CS_LAPCOUNT is not None:
            try:
                lap_count = int(get_state(cid, _CS_LAPCOUNT))
            except Exception:
                try:
                    lap_count = int(get_state(0, _CS_LAPCOUNT))
                except Exception:
                    lap_count = 0

        if self._last_lap_count < 0:
            self._last_lap_count = lap_count
            self._lap_fuel_start = self.fuel_liters
        elif lap_count > self._last_lap_count:
            spent = self._lap_fuel_start - self.fuel_liters
            # Ignore invalid spikes (pit refuel, teleports, malformed reads).
            if spent > 0.05 and spent < 50.0:
                if self.fuel_per_lap <= 0.0:
                    self.fuel_per_lap = spent
                else:
                    self.fuel_per_lap = (self.fuel_per_lap * 0.7) + (spent * 0.3)
            self._last_lap_count = lap_count
            self._lap_fuel_start = self.fuel_liters

        if self.fuel_per_lap > 0.001:
            self.est_laps = self.fuel_liters / self.fuel_per_lap
        else:
            self.est_laps = 0.0

        self.rpm = get_state(cid, _CS.RPM)
        if self.rpm > self._peak_rpm:
            self._peak_rpm = self.rpm
