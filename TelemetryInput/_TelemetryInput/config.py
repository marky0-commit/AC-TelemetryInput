import configparser

from _TelemetryInput.utils import console


class Config:
    """
    App configuration — loads from and saves to config.ini.

    All settings have sensible defaults that are written to the file
    the first time the app runs (or when a key is missing).
    """

    def __init__(self, config_path):
        self.update_cfg = False
        self.cfg_file_path = config_path
        self.cfg_parser = configparser.ConfigParser(inline_comment_prefixes=';')
        self.set_defaults()
        self.parse_config()

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------

    def set_defaults(self, save=False):
        # --- Trace visibility ---
        self.show_throttle = True       # Green throttle trace
        self.show_brake = True          # Red brake trace
        self.show_clutch = False        # Clutch trace
        self.show_ffb = False          # FFB trace

        # --- Bar visibility ---
        self.show_throttle_bar = True
        self.show_brake_bar = True
        self.show_clutch_bar = True
        self.show_ffb_bar = True
        self.bar_order = 'throttle,brake,clutch,ffb'

        # --- Info labels ---
        self.show_speed = True
        self.show_gear = True
        self.show_gear_color = True     # Enable RPM-based gear color changes
        self.show_fuel = True
        self.show_wheel = True          # Steering wheel indicator
        self.show_graph_lines = True    # Horizontal 25 / 50 / 75 % guide lines
        self.wheel_image = 'wheel_ring.png'  # PNG filename in icons/ folder
        # Wheel image scaling (px total removed) and minimum scale for small radii
        self.wheel_image_shrink_total = 20.0  # total pixels removed from diameter (e.g. 20 = 10px per side)
        self.wheel_image_min_scale = 0.7      # minimum fraction of diameter for very small wheels

        # --- Bar stop / number display ---
        self.show_bar_base_stop = True   # Show base (bottom) stop block on bars
        self.show_bar_end_stop = True    # Show end (top) stop block on bars
        self.show_bar_numbers = False    # Show percentage number labels on bars

        # --- Gear display ---

        # --- Dimensions ---
        self.app_height = 100           # Graph height in pixels  (10–1000)
        self.app_width = 300            # Graph width in pixels   (10–1000)
        self.bar_width = 18             # Width of each input bar in pixels
        self.padding = 4               # Window padding in pixels
        # Per-side paddings (fallback to `padding` for backwards compatibility)
        self.padding_left = 4
        self.padding_right = 4
        self.padding_top = 4
        self.padding_bottom = 4
        # Explicit wheel size override (0 = auto)
        self.wheel_size = 0
        self.trace_size = 2             # Trace line thickness in pixels (1–10)

        # --- Behaviour ---
        self.sample_rate = 40           # Samples per second (1–100 Hz)
        self.trace_smoothing = 0.35     # Smoothing strength: 0.0 none, 1.0 very smooth
        self.opacity = 0.70             # Overall opacity  (0.0–1.0)
        self.metric = True              # True = km/h, False = mph
        self.steering_sensitivity = 720  # Degrees lock-to-lock for full-scale steering

        # --- Trace colours (RGBA, each channel 0.0–1.0) ---
        self.throttle_color = (0.16, 1.00, 0.00, 1.0)
        self.brake_color    = (1.00, 0.16, 0.00, 1.0)
        self.clutch_color   = (0.16, 1.00, 1.00, 1.0)
        self.ffb_color      = (0.65, 0.65, 0.65, 1.0)

        if save:
            self.save()

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def parse_config(self):
        self.cfg_parser.read(self.cfg_file_path)

        if not self.cfg_parser.has_section('GENERAL'):
            self.cfg_parser.add_section('GENERAL')

        # Remove legacy options that are no longer used by this app version.
        # This keeps AC's Python App Settings page aligned with real behavior.
        for legacy_key in ('show_clutch', 'show_steering', 'steering_color'):
            if self.cfg_parser.has_option('GENERAL', legacy_key):
                self.cfg_parser.remove_option('GENERAL', legacy_key)
                self.update_cfg = True

        self.get_bool('GENERAL', 'show_throttle')
        self.get_bool('GENERAL', 'show_brake')
        self.get_bool('GENERAL', 'show_clutch')
        self.get_bool('GENERAL', 'show_ffb')
        self.get_bool('GENERAL', 'show_throttle_bar')
        self.get_bool('GENERAL', 'show_brake_bar')
        self.get_bool('GENERAL', 'show_clutch_bar')
        self.get_bool('GENERAL', 'show_ffb_bar')
        self.get_str('GENERAL',  'bar_order')
        self.get_bool('GENERAL', 'show_speed')
        self.get_bool('GENERAL', 'show_gear')
        self.get_bool('GENERAL', 'show_gear_color')
        self.get_bool('GENERAL', 'show_fuel')
        self.get_bool('GENERAL', 'show_wheel')
        self.get_bool('GENERAL', 'show_graph_lines')
        self.get_str('GENERAL', 'wheel_image')
        self.get_bool('GENERAL', 'metric')
        self.get_int('GENERAL', 'app_height')
        self.get_int('GENERAL', 'app_width')
        self.get_int('GENERAL', 'bar_width')
        # Legacy single `padding` kept for compatibility; new per-side keys
        self.get_int('GENERAL', 'padding')
        self.get_int('GENERAL', 'padding_left')
        self.get_int('GENERAL', 'padding_right')
        self.get_int('GENERAL', 'padding_top')
        self.get_int('GENERAL', 'padding_bottom')
        self.get_int('GENERAL', 'wheel_size')
        self.get_int('GENERAL', 'trace_size')
        self.get_int('GENERAL', 'sample_rate')
        self.get_int('GENERAL', 'steering_sensitivity')
        self.get_float('GENERAL', 'trace_smoothing')
        self.get_float('GENERAL', 'opacity')
        self.get_float('GENERAL', 'wheel_image_shrink_total')
        self.get_float('GENERAL', 'wheel_image_min_scale')
        self.get_bool('GENERAL', 'show_bar_base_stop')
        self.get_bool('GENERAL', 'show_bar_end_stop')
        self.get_bool('GENERAL', 'show_bar_numbers')
        self.get_rgba('GENERAL', 'throttle_color')
        self.get_rgba('GENERAL', 'brake_color')
        self.get_rgba('GENERAL', 'clutch_color')
        self.get_rgba('GENERAL', 'ffb_color')

        # Migrate legacy single `padding` into per-side values when
        # the individual keys are not present in the file.
        try:
            if not self.cfg_parser.has_option('GENERAL', 'padding_left'):
                self.padding_left = self.padding
            if not self.cfg_parser.has_option('GENERAL', 'padding_right'):
                self.padding_right = self.padding
            if not self.cfg_parser.has_option('GENERAL', 'padding_top'):
                self.padding_top = self.padding
            if not self.cfg_parser.has_option('GENERAL', 'padding_bottom'):
                self.padding_bottom = self.padding
        except Exception:
            pass
        if self.update_cfg:
            self.save()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(self):
        console('saving config')

        self.cfg_parser.set('GENERAL', 'show_throttle',      str(self.show_throttle))
        self.cfg_parser.set('GENERAL', 'show_brake',         str(self.show_brake))
        self.cfg_parser.set('GENERAL', 'show_clutch',        str(self.show_clutch))
        self.cfg_parser.set('GENERAL', 'show_ffb',           str(self.show_ffb))
        self.cfg_parser.set('GENERAL', 'show_throttle_bar',  str(self.show_throttle_bar))
        self.cfg_parser.set('GENERAL', 'show_brake_bar',     str(self.show_brake_bar))
        self.cfg_parser.set('GENERAL', 'show_clutch_bar',    str(self.show_clutch_bar))
        self.cfg_parser.set('GENERAL', 'show_ffb_bar',       str(self.show_ffb_bar))
        self.cfg_parser.set('GENERAL', 'bar_order',           str(self.bar_order))
        self.cfg_parser.set('GENERAL', 'show_speed',         str(self.show_speed))
        self.cfg_parser.set('GENERAL', 'show_gear',          str(self.show_gear))
        self.cfg_parser.set('GENERAL', 'show_gear_color',    str(self.show_gear_color))
        self.cfg_parser.set('GENERAL', 'show_fuel',          str(self.show_fuel))
        self.cfg_parser.set('GENERAL', 'show_wheel',         str(self.show_wheel))
        self.cfg_parser.set('GENERAL', 'show_graph_lines',   str(self.show_graph_lines))
        self.cfg_parser.set('GENERAL', 'wheel_image',        str(self.wheel_image))
        self.cfg_parser.set('GENERAL', 'metric',             str(self.metric))
        self.cfg_parser.set('GENERAL', 'app_height',         str(self.app_height))
        self.cfg_parser.set('GENERAL', 'app_width',          str(self.app_width))
        self.cfg_parser.set('GENERAL', 'bar_width',          str(self.bar_width))
        self.cfg_parser.set('GENERAL', 'padding',            str(self.padding))
        self.cfg_parser.set('GENERAL', 'trace_size',         str(self.trace_size))
        self.cfg_parser.set('GENERAL', 'sample_rate',        str(self.sample_rate))
        self.cfg_parser.set('GENERAL', 'steering_sensitivity', str(self.steering_sensitivity))
        self.cfg_parser.set('GENERAL', 'trace_smoothing',    str(self.trace_smoothing))
        self.cfg_parser.set('GENERAL', 'opacity',            str(self.opacity))
        self.cfg_parser.set('GENERAL', 'wheel_image_shrink_total', str(self.wheel_image_shrink_total))
        self.cfg_parser.set('GENERAL', 'wheel_image_min_scale', str(self.wheel_image_min_scale))
        self.cfg_parser.set('GENERAL', 'show_bar_base_stop', str(self.show_bar_base_stop))
        self.cfg_parser.set('GENERAL', 'show_bar_end_stop',  str(self.show_bar_end_stop))
        self.cfg_parser.set('GENERAL', 'show_bar_numbers',   str(self.show_bar_numbers))
        # Save per-side paddings and optional wheel size
        self.cfg_parser.set('GENERAL', 'padding_left',  str(self.padding_left))
        self.cfg_parser.set('GENERAL', 'padding_right', str(self.padding_right))
        self.cfg_parser.set('GENERAL', 'padding_top',   str(self.padding_top))
        self.cfg_parser.set('GENERAL', 'padding_bottom',str(self.padding_bottom))
        self.cfg_parser.set('GENERAL', 'wheel_size',     str(self.wheel_size))

        # Colours are stored as four 0–100 integers separated by commas
        for attr in ('throttle_color', 'brake_color', 'clutch_color', 'ffb_color'):
            value = ','.join(str(int(ch * 100)) for ch in getattr(self, attr))
            self.cfg_parser.set('GENERAL', attr, value)

        with open(self.cfg_file_path, 'w') as f:
            self.cfg_parser.write(f)

    # ------------------------------------------------------------------
    # Typed getters (fall back to default when key missing or malformed)
    # ------------------------------------------------------------------

    def get_float(self, section, option):
        try:
            value = self.cfg_parser.getfloat(section, option)
        except Exception:
            value = getattr(self, option)
            self.update_cfg = True
        self.__setattr__(option, value)

    def get_bool(self, section, option):
        try:
            value = self.cfg_parser.getboolean(section, option)
        except Exception:
            value = getattr(self, option)
            self.update_cfg = True
        self.__setattr__(option, value)

    def get_int(self, section, option):
        try:
            value = self.cfg_parser.getint(section, option)
        except Exception:
            try:
                value = int(self.cfg_parser.getfloat(section, option))
            except Exception:
                value = getattr(self, option)
            self.update_cfg = True
        self.__setattr__(option, value)

    def get_rgba(self, section, option):
        try:
            raw = self.cfg_parser.get(section, option)
            parts = [int(s) / 100.0 for s in raw.split(',')]
            value = (parts[0], parts[1], parts[2], parts[3])
        except Exception:
            value = getattr(self, option)
            self.update_cfg = True
        self.__setattr__(option, value)

    def get_str(self, section, option):
        try:
            value = self.cfg_parser.get(section, option).strip()
            if not value:
                raise ValueError('empty')
        except Exception:
            value = getattr(self, option)
            self.update_cfg = True
        self.__setattr__(option, value)
