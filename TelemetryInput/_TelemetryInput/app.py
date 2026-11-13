import ac
import acsys
import os
from _TelemetryInput.config import Config
from _TelemetryInput.data import TelemetryData
from _TelemetryInput.utils import console, console_exception
from _TelemetryInput.widgets import ACGraph, InputBar, SteeringWheel

# Config file lives next to the main TelemetryInput.py, two directories up
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.ini')
_ICONS_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons')

# Gap in pixels between layout regions
_GAP = 4
class App:
    """
    Main application class.

    Lifecycle:
        acMain  → App() → load_main()
        acUpdate → on_update(dt)
        render callback → on_render(dt)
        acShutDown → (config.save via entry point)
    """

    def __init__(self):
        self.config = None
        self.telemetry = None
        self.app_window = None
        self.graph_window = None
        self.bars_window = None
        self.settings_window = None   # dedicated settings window
        self.bars_bg = None
        self.settings_bg = None
        self._settings_handlers = []  # keep closures alive (prevent GC)
        self.graph = None
        self.bars = []
        self._bar_items = []
        self.throttle_trace = None
        self.brake_trace = None
        self.clutch_trace = None
        self.ffb_trace = None
        self._smooth_throttle = 0.0
        self._smooth_brake = 0.0
        self.speed_label = None
        self.speed_unit_label = None
        self.fuel_label = None
        self.est_laps_label = None
        self.gear_label = None
        self.gear_label_bold = None
        self.steering_wheel = None
        self._update_timer = 0.0
        self._low_freq_timer = 0.0
        self._update_timeout = 1.0 / 40  # overwritten by apply_config
        self._last_gear_str = ''
        self._last_gear_color = (1.0, 1.0, 1.0)
        self._last_speed_int = None
        self._last_fuel_text = ''
        self._last_est_laps_text = ''

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def load_main(self):
        self.config = Config(_CONFIG_PATH)
        self.telemetry = TelemetryData(self.config)
        self._smooth_throttle = self.telemetry.throttle
        self._smooth_brake = self.telemetry.brake

        # Main window — invisible AC anchor required for app discovery
        self.app_window = ac.newApp("TelemetryInput")
        ac.setTitle(self.app_window, "")
        ac.drawBorder(self.app_window, 0)
        ac.setBackgroundOpacity(self.app_window, 0.0)
        ac.setIconPosition(self.app_window, 0, -10000)
        ac.setSize(self.app_window, 1, 1)

        # Graph window
        self.graph_window = ac.newApp("TelemetryInput_Graph")
        ac.setTitle(self.graph_window, "")
        ac.drawBorder(self.graph_window, 0)
        ac.setBackgroundOpacity(self.graph_window, 0.0)
        ac.setIconPosition(self.graph_window, 0, -10000)

        # Pedals window
        self.bars_window = ac.newApp("TelemetryInput_Pedals")
        ac.setTitle(self.bars_window, "")
        ac.drawBorder(self.bars_window, 0)
        ac.setBackgroundOpacity(self.bars_window, 0.0)
        ac.setIconPosition(self.bars_window, 0, -10000)

        # Dedicated settings window — separate from the 1x1 anchor so it
        # can receive click events normally.
        self.settings_window = ac.newApp("TelemetryInput_Settings")
        ac.setTitle(self.settings_window, "")
        ac.drawBorder(self.settings_window, 0)
        ac.setIconPosition(self.settings_window, 0, -10000)

        self._build_layout()
        self._build_settings()
        console("app loaded — window ready")

    def _get_paddings(self, cfg):
        """Return effective per-side paddings with legacy fallback."""
        return (
            getattr(cfg, 'padding_left', cfg.padding),
            getattr(cfg, 'padding_right', cfg.padding),
            getattr(cfg, 'padding_top', cfg.padding),
            getattr(cfg, 'padding_bottom', cfg.padding),
        )

    def _get_bg_pad(self, pl, pr, pt, pb):
        """Outer breathing-room padding around graph/pedals regions."""
        return 5 if max(pl, pr, pt, pb) > 0 else 0

    def _build_layout(self):
        cfg = self.config
        # per-side padding (fallback to legacy `padding`)
        pl, pr, pt, pb = self._get_paddings(cfg)
        bw  = cfg.bar_width
        # Keep info stack (fuel/gear/speed) inside panel at small sizes.
        unit_font  = max(9, int(cfg.app_height * 0.14))
        speed_font = max(13, int(cfg.app_height * 0.22))
        gear_font  = max(18, int(cfg.app_height * 0.34))
        fuel_font  = max(9, int(cfg.app_height * 0.11))
        col_w      = max(speed_font + 8, gear_font + 4)

        # Small outer background pad for visual breathing room. Keep it
        # when `padding` > 0 but remove it when the user explicitly sets
        # `padding = 0` so they get a snug layout.
        bg_pad = self._get_bg_pad(pl, pr, pt, pb)

        # ---- Graph window ----
        self.telemetry_bg = ac.addLabel(self.graph_window, '')
        # Background sits at window origin; inner graph is offset by
        # bg_pad + padding so visuals align with pedals window.
        ac.setPosition(self.telemetry_bg, 0, 0)
        ac.setSize(self.telemetry_bg, cfg.app_width + pl + pr + bg_pad * 2 - 1, cfg.app_height + pt + pb + bg_pad * 2 + 1)
        ac.setBackgroundColor(self.telemetry_bg, 0.01, 0.01, 0.01)
        ac.setBackgroundOpacity(self.telemetry_bg, cfg.opacity)
        try:
            ac.drawBorder(self.telemetry_bg, 0)
        except Exception:
            pass

        # telemetry_bg covers the full window (dark outer padding).
        # ACGraph is given the inset content area so bg_label only covers
        # the inner region, revealing the dark border. +1 on width keeps
        # the newest sample column at the visible right edge.
        _gx = pl + bg_pad
        _gy = pt + bg_pad
        _cw = cfg.app_width + 1  # graph widget: +1 for right-edge alignment
        _ch = cfg.app_height     # content height
        self.graph = ACGraph(
            window=self.graph_window,
            x=_gx, y=_gy,
            width=_cw,
            height=_ch,
            trace_width=cfg.trace_size,
            opacity=cfg.opacity,
            show_lines=cfg.show_graph_lines,
        )
        # bg_label: exact app_width (no +1 strip on right), 1px taller to
        # cover the 1px AC graph baseline gap at the bottom.
        ac.setSize(self.graph.bg_label, cfg.app_width, _ch + 1)
        # Move only the graph widget down 1px so trace baseline sits lower
        # while staying fully inside bg_label (which is already +1 taller).
        ac.setPosition(self.graph.graph_widget, _gx, _gy + 1)
        if cfg.show_throttle:
            self.throttle_trace = self.graph.add_trace(cfg.throttle_color)
        if cfg.show_brake:
            self.brake_trace = self.graph.add_trace(cfg.brake_color)
        # Optional traces
        if getattr(cfg, 'show_clutch', False):
            self.clutch_trace = self.graph.add_trace(cfg.clutch_color)
        if getattr(cfg, 'show_ffb', False):
            self.ffb_trace = self.graph.add_trace(cfg.ffb_color)

        ac.setSize(self.graph_window, cfg.app_width + pl + pr + bg_pad * 2 - 2, cfg.app_height + pt + pb + bg_pad * 2 + 1)

        # ---- Bars/info window ----
        # Background created first so it renders behind all other widgets
        self.bars_bg = ac.addLabel(self.bars_window, '')
        ac.setBackgroundColor(self.bars_bg, 0.01, 0.01, 0.01)
        ac.setBackgroundOpacity(self.bars_bg, cfg.opacity)
        try:
            ac.drawBorder(self.bars_bg, 0)
        except Exception:
            pass

        self.bars = []
        self._bar_items = []
        # Keep layout anchors for dynamic reflow when visibility changes
        # Start bars at padding + outer bg_pad so they align with the graph.
        # Add a fixed 1px inner left offset so bars never overlap the
        # visible padding area even when `padding` is small or zero.
        left_inner_pad = bg_pad + 1
        bar_x    = pl + left_inner_pad
        bar_slot = 0
        bar_y    = pt + bg_pad
        bar_h    = cfg.app_height
        pct_font = max(10, int(cfg.app_height * 0.10))
        info_base_y = bar_y  # always centred on full app_height regardless of pct
        self._info_base_y = info_base_y
        if cfg.show_bar_numbers:
            pct_y  = bar_y
            bar_y += pct_font + 4
            bar_h -= pct_font + 4
        else:
            pct_y  = bar_y  # won't be shown

        # record anchors for reflow
        self._bars_start_x = bar_x
        self._bars_start_y = bar_y
        self._bar_width = bw
        self._bg_pad = bg_pad

        _VALID = ('throttle', 'brake', 'clutch', 'ffb')
        _bar_defs = {
            'throttle': (cfg.throttle_color, lambda: self.telemetry.throttle, 'show_throttle_bar', False),
            'brake':    (cfg.brake_color,    lambda: self.telemetry.brake,    'show_brake_bar',    False),
            'clutch':   (cfg.clutch_color,   lambda: self.telemetry.clutch,   'show_clutch_bar',   False),
            'ffb':      (cfg.ffb_color,      lambda: self.telemetry.ffb_norm, 'show_ffb_bar',      True),
        }
        order = [s.strip() for s in cfg.bar_order.split(',') if s.strip() in _VALID]
        for k in _VALID:
            if k not in order:
                order.append(k)
        for key in order:
            color, getter, vis_key, is_ffb = _bar_defs[key]
            self._add_bar(bar_x, bar_slot, bar_y, bw, bar_h,
                          color, getter, vis_key, '0', pct_y, pct_font)
            if is_ffb:
                self.bars[-1].is_ffb = True
            bar_slot += 1

        total_bar_w = bar_slot * bw + max(bar_slot - 1, 0) * _GAP
        has_right_content = (cfg.show_fuel or cfg.show_gear or cfg.show_speed or cfg.show_wheel)
        info_x = bar_x + total_bar_w + (_GAP * 2 if bar_slot > 0 and has_right_content else 0)

        info_cy = info_base_y + cfg.app_height // 2
        if cfg.show_fuel or cfg.show_gear or cfg.show_speed:
            fuel_h  = fuel_font  if cfg.show_fuel  else 0
            est_h   = fuel_font  if cfg.show_fuel  else 0
            fuel_gap = 1 if fuel_h and est_h else 0
            fuel_block_h = (fuel_h + fuel_gap + est_h) if cfg.show_fuel else 0
            gear_h  = gear_font  if cfg.show_gear  else 0
            unit_h  = unit_font  if cfg.show_speed else 0
            spd_h   = speed_font if cfg.show_speed else 0
            gap1    = 1
            gap2    = 2
            total_h = (
                fuel_block_h
                + (gap1 if fuel_block_h and gear_h else 0)
                + gear_h
                + (gap2 if gear_h and (unit_h or spd_h) else 0)
                + unit_h
                + spd_h
            )
            min_y = info_base_y
            max_y = info_base_y + cfg.app_height - total_h
            col_y = info_cy - total_h // 2
            if col_y < min_y:
                col_y = min_y
            elif col_y > max_y:
                col_y = max_y

            if cfg.show_fuel:
                self.fuel_label = ac.addLabel(self.bars_window, "--.-L")
                ac.setPosition(self.fuel_label, info_x, col_y)
                ac.setFontSize(self.fuel_label, fuel_font)
                ac.setFontColor(self.fuel_label, 0.72, 0.72, 0.72, cfg.opacity)

                self.est_laps_label = ac.addLabel(self.bars_window, "--.-lap")
                ac.setPosition(self.est_laps_label, info_x, col_y + fuel_h + fuel_gap)
                ac.setFontSize(self.est_laps_label, fuel_font)
                ac.setFontColor(self.est_laps_label, 0.72, 0.72, 0.72, cfg.opacity)

                col_y += fuel_block_h + (gap1 if fuel_block_h and gear_h else 0)

            if cfg.show_gear:
                self.gear_label = ac.addLabel(self.bars_window, "N")
                ac.setPosition(self.gear_label, info_x, col_y)
                ac.setFontSize(self.gear_label, gear_font)
                ac.setFontColor(self.gear_label, 1.0, 1.0, 1.0, cfg.opacity)
                self.gear_label_bold = ac.addLabel(self.bars_window, "N")
                ac.setPosition(self.gear_label_bold, info_x + 1, col_y)
                ac.setFontSize(self.gear_label_bold, gear_font)
                ac.setFontColor(self.gear_label_bold, 1.0, 1.0, 1.0, cfg.opacity)
                col_y += gear_h + gap2

            if cfg.show_speed:
                unit_str = 'kph' if cfg.metric else 'mph'
                self.speed_unit_label = ac.addLabel(self.bars_window, unit_str)
                ac.setPosition(self.speed_unit_label, info_x, col_y)
                ac.setFontSize(self.speed_unit_label, unit_font)
                ac.setFontColor(self.speed_unit_label, 0.75, 0.75, 0.75, 0.85 * cfg.opacity)
                col_y += unit_h

                self.speed_label = ac.addLabel(self.bars_window, "0")
                ac.setPosition(self.speed_label, info_x, col_y)
                ac.setFontSize(self.speed_label, speed_font)
                ac.setFontColor(self.speed_label, 1.0, 1.0, 1.0, cfg.opacity)

            info_x += col_w + _GAP

        # ---- Steering wheel ----
        if cfg.show_wheel:
            # Wheel radius: allow explicit override via config.wheel_size (0 = auto)
            if getattr(cfg, 'wheel_size', 0):
                wheel_r = max(6, int(cfg.wheel_size))
            else:
                # Reduce wheel radius by 5px so the wheel appears smaller
                # on each side compared to previous sizing.
                wheel_r  = max(6, (bar_h // 2) - 5)
            # Place wheel immediately after the info column. Don't add
            # extra `p` here — `p` is applied later when sizing the window.
            wheel_cx = info_x + wheel_r + 5
            wheel_cy = info_cy
            self.steering_wheel = SteeringWheel(
                window=self.bars_window,
                cx=wheel_cx,
                cy=wheel_cy,
                radius=wheel_r,
                max_deg=cfg.steering_sensitivity / 2,
                icons_dir=_ICONS_DIR,
                image_filename=cfg.wheel_image,
                config=cfg,
            )
            info_x = wheel_cx + wheel_r + _GAP

        # Use per-side paddings for overall window sizing
        bars_win_w = info_x + pr
        bars_win_h = cfg.app_height + pt + pb
        # Background sits at window origin; window includes outer bg_pad
        # Add 1px extra bottom padding to match graph background.
        ac.setPosition(self.bars_bg, 0, 0)
        ac.setSize(self.bars_bg, bars_win_w + bg_pad * 2, bars_win_h + bg_pad * 2 + 1)
        ac.setSize(self.bars_window, bars_win_w + bg_pad * 2, bars_win_h + bg_pad * 2 + 1)

        self._refresh_bar_visibility()
        self._apply_info_visibility()

        self._update_timeout = 1.0 / max(cfg.sample_rate, 1)
        try:
            console('TelemetryInput: load_main complete')
        except Exception:
            pass

    def _add_bar(self, bar_x, slot, y_pad, bw, height, color, getter, visible_key, label_text, pct_y, pct_font):
        x = bar_x + slot * (bw + _GAP)
        bar = InputBar(x, y_pad, bw, height, color)
        self.bars.append(bar)
        lbl = ac.addLabel(self.bars_window, '0')
        ac.setPosition(lbl, x, pct_y)
        ac.setSize(lbl, bw, pct_font + 2)
        ac.setFontSize(lbl, pct_font)
        ac.setFontAlignment(lbl, 'center')
        r, g, b, a = color
        ac.setFontColor(lbl, r, g, b, self.config.opacity)
        ac.setText(lbl, label_text)
        self._bar_items.append({
            'bar': bar,
            'getter': getter,
            'visible_key': visible_key,
            'label': lbl,
            'label_text': label_text,
            'label_y': pct_y,
            'label_color': (r, g, b),
        })

    def _refresh_bar_visibility(self):
        # Reflow visible bars so there are no gaps when some are hidden.
        cfg = self.config
        show_numbers = cfg.show_bar_numbers
        if self._bars_start_x is None or self._bar_width is None:
            # nothing to do
            for item in self._bar_items:
                visible = getattr(cfg, item['visible_key'], False)
                try:
                    ac.setVisible(item['label'], 1 if visible and show_numbers else 0)
                except Exception:
                    pass
                if not visible:
                    item['bar'].value = 0.0
            return

        slot = 0
        start_x = self._bars_start_x
        bw = self._bar_width
        bar_y = self._bars_start_y

        for item in self._bar_items:
            visible = getattr(cfg, item['visible_key'], False)
            try:
                ac.setVisible(item['label'], 1 if visible and show_numbers else 0)
            except Exception:
                pass

            if visible:
                new_x = int(start_x + slot * (bw + _GAP))
                # move the bar drawing origin
                try:
                    item['bar'].x = int(new_x)
                except Exception:
                    pass
                # move the percentage label
                try:
                    ac.setPosition(item['label'], new_x, item.get('label_y', bar_y - 10))
                except Exception:
                    pass
                slot += 1
            else:
                item['bar'].value = 0.0

        # Recompute info column and wheel positions based on visible bars
        total_bar_w = slot * bw + max(slot - 1, 0) * _GAP
        has_right_content = (cfg.show_fuel or cfg.show_gear or cfg.show_speed or cfg.show_wheel)
        info_x = start_x + total_bar_w + (_GAP * 2 if slot > 0 and has_right_content else 0)
        info_cy = getattr(self, '_info_base_y', bar_y) + (cfg.app_height // 2)

        # Reposition info labels using the same fit-safe font sizing as build.
        unit_font = max(9, int(cfg.app_height * 0.14))
        speed_font = max(13, int(cfg.app_height * 0.22))
        gear_font = max(18, int(cfg.app_height * 0.34))
        fuel_font = max(9, int(cfg.app_height * 0.11))
        col_w = max(speed_font + 8, gear_font + 4)
        fuel_h = fuel_font if cfg.show_fuel else 0
        est_h = fuel_font if cfg.show_fuel else 0
        fuel_gap = 1 if fuel_h and est_h else 0
        fuel_block_h = (fuel_h + fuel_gap + est_h) if cfg.show_fuel else 0
        gear_h = gear_font if cfg.show_gear else 0
        unit_h = unit_font if cfg.show_speed else 0
        spd_h = speed_font if cfg.show_speed else 0
        gap1 = 1
        gap2 = 2
        total_h = (
            fuel_block_h
            + (gap1 if fuel_block_h and gear_h else 0)
            + gear_h
            + (gap2 if gear_h and (unit_h or spd_h) else 0)
            + unit_h
            + spd_h
        )
        info_base_y = getattr(self, '_info_base_y', bar_y)
        min_y = info_base_y
        max_y = info_base_y + cfg.app_height - total_h
        col_y = info_cy - total_h // 2
        if col_y < min_y:
            col_y = min_y
        elif col_y > max_y:
            col_y = max_y

        if self.fuel_label:
            try:
                ac.setPosition(self.fuel_label, info_x, col_y)
            except Exception:
                pass
        if self.est_laps_label:
            try:
                ac.setPosition(self.est_laps_label, info_x, col_y + fuel_h + fuel_gap)
            except Exception:
                pass
        if self.fuel_label or self.est_laps_label:
            col_y += fuel_block_h + (gap1 if fuel_block_h and gear_h else 0)

        if self.gear_label:
            try:
                ac.setPosition(self.gear_label, info_x, col_y)
            except Exception:
                pass
            if self.gear_label_bold:
                try:
                    ac.setPosition(self.gear_label_bold, info_x + 1, col_y)
                except Exception:
                    pass
            col_y += gear_h + (gap2 if gear_h and (unit_h or spd_h) else 0)

        if self.speed_unit_label:
            try:
                ac.setPosition(self.speed_unit_label, info_x, col_y)
            except Exception:
                pass
            col_y += unit_h

        if self.speed_label:
            try:
                ac.setPosition(self.speed_label, info_x, col_y)
            except Exception:
                pass

        # Advance info_x by the column width if gear/speed are shown
        if cfg.show_fuel or cfg.show_gear or cfg.show_speed:
            info_x += col_w + _GAP

        # Reposition steering wheel
        if self.steering_wheel and cfg.show_wheel:
            try:
                wheel_r = self.steering_wheel.radius
                wheel_cx = info_x + wheel_r + 5
                wheel_cy = info_cy
                self.steering_wheel.cx = wheel_cx
                self.steering_wheel.cy = wheel_cy
                info_x = wheel_cx + wheel_r + _GAP
            except Exception:
                pass

        # Resize window/background to fit new layout
        try:
            # Use per-side paddings for reflow
            pl, pr, pt, pb = self._get_paddings(cfg)
            bars_win_w = info_x + pr
            bars_win_h = cfg.app_height + pt + pb
            # Use the same outer bg_pad policy computed during initial layout.
            bg_pad = getattr(self, '_bg_pad', self._get_bg_pad(pl, pr, pt, pb))
            # Background sits at window origin; inner content uses `padding + bg_pad`.
            # Add 1px extra bottom padding to avoid edge overlap.
            ac.setPosition(self.bars_bg, 0, 0)
            ac.setSize(self.bars_bg, bars_win_w + bg_pad * 2, bars_win_h + bg_pad * 2 + 1)
            ac.setBackgroundOpacity(self.bars_bg, cfg.opacity)
            ac.setSize(self.bars_window, bars_win_w + bg_pad * 2, bars_win_h + bg_pad * 2 + 1)
        except Exception:
            pass

    def _clear_layout(self):
        """Hide and drop references to current layout widgets so we can
        recreate an atomic, fresh UI without duplicates.
        """
        try:
            if getattr(self, 'telemetry_bg', None) is not None:
                try:
                    ac.setVisible(self.telemetry_bg, 0)
                except Exception:
                    try:
                        ac.setPosition(self.telemetry_bg, -10000, -10000)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            if getattr(self, 'graph', None) is not None:
                try:
                    ac.setVisible(self.graph.bg_label, 0)
                except Exception:
                    try:
                        ac.setPosition(self.graph.bg_label, -10000, -10000)
                    except Exception:
                        pass
                try:
                    ac.setVisible(self.graph.graph_widget, 0)
                except Exception:
                    try:
                        ac.setPosition(self.graph.graph_widget, -10000, -10000)
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            if getattr(self, 'bars_bg', None) is not None:
                try:
                    ac.setVisible(self.bars_bg, 0)
                except Exception:
                    try:
                        ac.setPosition(self.bars_bg, -10000, -10000)
                    except Exception:
                        pass
        except Exception:
            pass

        # Hide all bar percentage labels and clear bar data so render loop
        # no longer draws the old bars.
        try:
            for item in list(getattr(self, '_bar_items', []) or []):
                try:
                    lbl = item.get('label')
                    if lbl is not None:
                        ac.setVisible(lbl, 0)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if getattr(self, 'fuel_label', None):
                ac.setVisible(self.fuel_label, 0)
        except Exception:
            pass
        try:
            if getattr(self, 'est_laps_label', None):
                ac.setVisible(self.est_laps_label, 0)
        except Exception:
            pass
        try:
            if getattr(self, 'gear_label', None):
                ac.setVisible(self.gear_label, 0)
        except Exception:
            pass
        try:
            if getattr(self, 'gear_label_bold', None):
                ac.setVisible(self.gear_label_bold, 0)
        except Exception:
            pass
        try:
            if getattr(self, 'speed_label', None):
                ac.setVisible(self.speed_label, 0)
        except Exception:
            pass
        try:
            if getattr(self, 'speed_unit_label', None):
                ac.setVisible(self.speed_unit_label, 0)
        except Exception:
            pass

        # Drop references so the next build starts fresh
        self.bars = []
        self._bar_items = []
        self.throttle_trace = None
        self.brake_trace = None
        self.clutch_trace = None
        self.ffb_trace = None
        self.fuel_label = None
        self.est_laps_label = None
        self.gear_label = None
        self.gear_label_bold = None
        self.speed_label = None
        self.speed_unit_label = None
        self.steering_wheel = None
        self._last_gear_color = (1.0, 1.0, 1.0)
        self._last_speed_int = None
        self._last_fuel_text = ''
        self._last_est_laps_text = ''

    def _recreate_layout_atomic(self):
        """Atomically destroy/recreate the UI area (graph + pedals) to
        safely apply layout changes without incremental glitches.
        """
        try:
            self._clear_layout()
        except Exception:
            pass

        # Build a fresh layout using current config
        try:
            self._build_layout()
        except Exception:
            pass
    
    def _apply_info_visibility(self):
        if self.fuel_label:
            ac.setVisible(self.fuel_label, 1 if self.config.show_fuel else 0)
        if self.est_laps_label:
            ac.setVisible(self.est_laps_label, 1 if self.config.show_fuel else 0)
        if self.gear_label:
            ac.setVisible(self.gear_label, 1 if self.config.show_gear else 0)
        if self.gear_label_bold:
            ac.setVisible(self.gear_label_bold, 1 if self.config.show_gear else 0)
        if self.speed_label:
            ac.setVisible(self.speed_label, 1 if self.config.show_speed else 0)
        if self.speed_unit_label:
            ac.setVisible(self.speed_unit_label, 1 if self.config.show_speed else 0)
            ac.setText(self.speed_unit_label, 'kph' if self.config.metric else 'mph')

    # ------------------------------------------------------------------
    # Update (called every frame by acUpdate)
    # ------------------------------------------------------------------

    def on_update(self, dt):
        self._update_timer    += dt
        self._low_freq_timer  += dt
        cfg = self.config
        tel = self.telemetry

        # High-frequency telemetry sample
        if self._update_timer >= self._update_timeout:
            self._update_timer = 0.0
            tel.update_telemetry()

            # Exponential moving average.
            # trace_smoothing is user-facing "strength":
            #   0.0 = no smoothing, 1.0 = very smooth.
            smoothing = min(max(cfg.trace_smoothing, 0.0), 0.98)
            alpha = 1.0 - smoothing
            self._smooth_throttle += (tel.throttle - self._smooth_throttle) * alpha
            self._smooth_brake += (tel.brake - self._smooth_brake) * alpha

            # Push new sample into each active trace
            if self.throttle_trace:
                self.throttle_trace.add_value(self._smooth_throttle)
            if self.brake_trace:
                self.brake_trace.add_value(self._smooth_brake)
            if self.clutch_trace:
                # clutch is already in 0..1 range (pressed = 1)
                self.clutch_trace.add_value(tel.clutch)
            if self.ffb_trace:
                # use absolute-normalised FFB magnitude
                self.ffb_trace.add_value(tel.ffb_norm)

            # Ensure guide series are fed constant values so they draw
            # as horizontal lines beneath the traces.
            if self.graph is not None:
                try:
                    self.graph.update_guides()
                except Exception:
                    pass

            # Update bar fill values for enabled bars only
            show_numbers = cfg.show_bar_numbers
            for item in self._bar_items:
                if getattr(cfg, item['visible_key'], False):
                    v = item['getter']()
                    item['bar'].value = v
                    if show_numbers:
                        pct = int(v * 100)
                        if item.get('_last_pct') != pct:
                            item['_last_pct'] = pct
                            try:
                                ac.setText(item['label'], str(pct))
                            except Exception:
                                pass
                else:
                    item['bar'].value = 0.0

            # Update speed
            if self.speed_label and cfg.show_speed:
                spd_int = int(tel.speed_kph if cfg.metric else tel.speed_mph)
                if spd_int != self._last_speed_int:
                    self._last_speed_int = spd_int
                    ac.setText(self.speed_label, str(spd_int))

            # Update fuel + estimated laps (split into two lines)
            if self.fuel_label and cfg.show_fuel:
                fuel_text = '{:.1f}L'.format(max(0.0, tel.fuel_liters))
                if fuel_text != self._last_fuel_text:
                    self._last_fuel_text = fuel_text
                    ac.setText(self.fuel_label, fuel_text)
            if self.est_laps_label and cfg.show_fuel:
                est_laps_text = '{:.1f}lap'.format(max(0.0, tel.est_laps))
                if est_laps_text != self._last_est_laps_text:
                    self._last_est_laps_text = est_laps_text
                    ac.setText(self.est_laps_label, est_laps_text)

            # Update steering wheel
            if self.steering_wheel and cfg.show_wheel:
                self.steering_wheel.steering_deg = tel.steering

            if self.gear_label and cfg.show_gear:
                gear = tel.gear_str
                if gear != self._last_gear_str:
                    self._last_gear_str = gear
                    ac.setText(self.gear_label, gear)
                    if self.gear_label_bold:
                        ac.setText(self.gear_label_bold, gear)

                # RPM-based colour: white → orange → red as rev climbs
                rpm = tel.rpm
                peak = tel._peak_rpm
                ratio = rpm / peak if peak > 0 else 0.0
                max_power_rpm = getattr(tel, 'max_power_rpm', 0.0)
                # Match RaceEssentials behavior:
                # normal mode: orange >0.90 and <0.94, red >=0.94
                # max-power mode (if max_power_rpm < observed peak):
                # orange >0.94 and <1.00, red >=1.00
                if cfg.show_gear_color:
                    if max_power_rpm > 0.0 and max_power_rpm < peak:
                        p_ratio = rpm / max_power_rpm if max_power_rpm > 0 else 0.0
                        if p_ratio > 0.94 and p_ratio < 1.0:
                            color = (1.0, 0.46, 0.18)
                        elif p_ratio >= 1.0:
                            color = (1.0, 0.18, 0.18)
                        else:
                            color = (1.0, 1.0, 1.0)
                    else:
                        if ratio > 0.90 and ratio < 0.94:
                            color = (1.0, 0.46, 0.18)
                        elif ratio >= 0.94:
                            color = (1.0, 0.18, 0.18)
                        else:
                            color = (1.0, 1.0, 1.0)
                else:
                    color = (1.0, 1.0, 1.0)
                if color != self._last_gear_color:
                    self._last_gear_color = color
                    r, g, b = color
                    op = cfg.opacity
                    ac.setFontColor(self.gear_label, r, g, b, op)
                    if self.gear_label_bold:
                        ac.setFontColor(self.gear_label_bold, r, g, b, op)

        # Low-frequency housekeeping (~10 Hz)
        if self._low_freq_timer >= 0.1:
            self._low_freq_timer = 0.0
            tel.update_globals()

            # Flush deferred config save (set by settings panel closures)
            if cfg.update_cfg:
                cfg.update_cfg = False
                cfg.save()

            # Dragging a window resets its background opacity — keep all transparent
            ac.setBackgroundOpacity(self.app_window, 0)
            ac.setBackgroundOpacity(self.graph_window, 0)
            ac.setBackgroundOpacity(self.bars_window, 0)

    # ------------------------------------------------------------------
    # Render (called every frame via addRenderCallback)
    # ------------------------------------------------------------------

    def on_render(self, dt):
        cfg = self.config
        if cfg.show_graph_lines and self.graph is not None:
            if not getattr(self.graph, '_guide_series_indices', []):
                pl, pr, pt, pb = self._get_paddings(cfg)
                bg_pad = self._get_bg_pad(pl, pr, pt, pb)
                inner_x = pl + bg_pad + 1
                inner_y = pt + bg_pad
                line_a = min(0.35 + cfg.opacity, 1.0)
                ac.glColor4f(0.45, 0.45, 0.45, line_a)
                for frac in (0.25, 0.50, 0.75):
                    gy = inner_y + cfg.app_height * frac
                    ac.glBegin(acsys.GL.Lines)
                    ac.glVertex2f(inner_x, gy)
                    ac.glVertex2f(inner_x + cfg.app_width - 2, gy)
                    ac.glEnd()

    def on_render_bars(self, dt):
        opacity = self.config.opacity
        show_base = self.config.show_bar_base_stop
        show_end  = self.config.show_bar_end_stop
        for item in self._bar_items:
            if getattr(self.config, item['visible_key'], False):
                try:
                    bar = item['bar']
                    bar.show_base_stop = show_base
                    bar.show_end_stop  = show_end
                    bar.render(opacity)
                except Exception as e:
                    console('Bar render error: {}'.format(e))
        if self.steering_wheel and self.config.show_wheel:
            self.steering_wheel.render(opacity)

    # ------------------------------------------------------------------
    # Settings panel
    # ------------------------------------------------------------------

    def _build_settings(self):
        cfg = self.config
        win = self.settings_window
        left_col_w = 270
        right_col_w = 280
        w = left_col_w + right_col_w + 30
        pad   = 10
        row_h = 26
        sec_h = 18
        gap   = 6

        self.settings_bg = ac.addLabel(win, '')
        ac.setPosition(self.settings_bg, 0, 0)
        ac.setBackgroundColor(self.settings_bg, 0.05, 0.05, 0.05)
        ac.setBackgroundOpacity(self.settings_bg, 0.9)
        try:
            ac.drawBorder(self.settings_bg, 0)
        except Exception:
            pass

        sections = [
            ('General', [
                ('Metric (kph/mph)', 'metric'),
                ('Guide lines', 'show_graph_lines'),
            ]),
            ('Traces', [
                ('Throttle trace', 'show_throttle'),
                ('Brake trace', 'show_brake'),
                ('Clutch trace', 'show_clutch'),
                ('FFB trace', 'show_ffb'),
            ]),
            ('Inputs', [
                ('Throttle bar', 'show_throttle_bar'),
                ('Brake bar', 'show_brake_bar'),
                ('Clutch bar', 'show_clutch_bar'),
                ('FFB bar', 'show_ffb_bar'),
                ('Base stop', 'show_bar_base_stop'),
                ('End stop', 'show_bar_end_stop'),
                ('Percentages', 'show_bar_numbers'),
            ]),
            ('Wheel', [
                ('Steering wheel', 'show_wheel'),
                ('Fuel', 'show_fuel'),
                ('Gear', 'show_gear'),
                ('Gear color', 'show_gear_color'),
                ('Speed', 'show_speed'),
            ]),
        ]

        design_rows = [
            # Layout controls are applied atomically by rebuilding the UI
            # area to avoid transient visual glitches.
            ('Graph width', 'app_width', 80, 1200, 1, True, lambda v: int(v), lambda v: int(v)),
            ('Size', 'app_height', 40, 1000, 1, True, lambda v: int(v), lambda v: int(v)),
            ('Bar width', 'bar_width', 8, 60, 1, True, lambda v: int(v), lambda v: int(v)),
            ('Padding', 'padding', 0, 80, 1, True, lambda v: int(v), lambda v: int(v)),
            ('Padding Left', 'padding_left', 0, 80, 1, True, lambda v: int(v), lambda v: int(v)),
            ('Padding Right', 'padding_right', 0, 80, 1, True, lambda v: int(v), lambda v: int(v)),
            ('Padding Top', 'padding_top', 0, 80, 1, True, lambda v: int(v), lambda v: int(v)),
            ('Padding Bottom', 'padding_bottom', 0, 80, 1, True, lambda v: int(v), lambda v: int(v)),
            ('Trace size', 'trace_size', 1, 10, 1, True, lambda v: int(v), lambda v: int(v)),
            ('Sample rate', 'sample_rate', 1, 120, 1, True, lambda v: int(v), lambda v: int(v)),
            ('Steering range', 'steering_sensitivity', 180, 1440, 10, True, lambda v: int(v), lambda v: int(v)),
            ('Smoothing %', 'trace_smoothing', 0, 98, 1, True, lambda v: max(0.0, min(0.98, float(v) / 100.0)), lambda v: int(v * 100)),
            ('Opacity %', 'opacity', 10, 100, 1, True, lambda v: max(0.10, min(1.0, float(v) / 100.0)), lambda v: int(v * 100)),
            ('Wheel size', 'wheel_size', 0, 200, 1, True, lambda v: int(v), lambda v: int(v)),
            ('Wheel image shrink', 'wheel_image_shrink_total', 0, 80, 1, True, lambda v: float(v), lambda v: int(v)),
            ('Wheel min scale %', 'wheel_image_min_scale', 50, 100, 1, True, lambda v: max(0.10, min(1.0, float(v) / 100.0)), lambda v: int(v * 100)),
        ]

        _LAYOUT_KEYS = (
            'app_width', 'app_height', 'bar_width', 'padding', 'trace_size',
            'padding_left', 'padding_right', 'padding_top', 'padding_bottom', 'wheel_size'
        )
        _BAR_VIS_KEYS = ('show_throttle_bar', 'show_brake_bar', 'show_clutch_bar', 'show_ffb_bar', 'show_wheel',
                         'show_bar_base_stop', 'show_bar_end_stop')
        _REBUILD_KEYS = ('show_bar_numbers',)
        _INFO_KEYS = ('show_fuel', 'show_speed', 'show_gear', 'metric')
        _TRACE_VIS_KEYS = ('show_throttle', 'show_brake', 'show_clutch', 'show_ffb')
        _SIDE_PAD_KEYS = ('padding_left', 'padding_right', 'padding_top', 'padding_bottom')

        def _add_section_header(x, y, text):
            hdr = ac.addLabel(win, text)
            ac.setPosition(hdr, x, y)
            ac.setFontSize(hdr, 11)
            ac.setFontColor(hdr, 0.55, 0.75, 1.0, 1.0)
            return y + sec_h

        def _add_labeled_spinner(label_text, x, y, label_w, spin_w, spin_h,
                                 min_v, max_v, step_v, value):
            lbl = ac.addLabel(win, label_text)
            ac.setPosition(lbl, x, y + 2)
            ac.setFontSize(lbl, 12)

            sp = ac.addSpinner(win, '')
            ac.setRange(sp, min_v, max_v)
            ac.setStep(sp, step_v)
            ac.setValue(sp, value)
            ac.setPosition(sp, x + label_w, y)
            ac.setSize(sp, spin_w, spin_h)
            ac.setFontSize(sp, 13)
            return sp

        def _apply_live_setting(key):
            # Apply changes that can be reflected immediately without reload.
            if key == 'opacity':
                opacity = self.config.opacity
                # Graph background
                if self.graph:
                    try:
                        self.graph.set_opacity(opacity)
                    except Exception:
                        pass
                # Window backgrounds (graph and pedals only)
                try:
                    if self.telemetry_bg:
                        ac.setBackgroundOpacity(self.telemetry_bg, opacity)
                except Exception:
                    pass
                try:
                    if self.bars_bg:
                        ac.setBackgroundOpacity(self.bars_bg, opacity)
                except Exception:
                    pass

                # Update key label alphas (graph/pedals labels only)
                try:
                    if self.gear_label:
                        r, g, b = self._last_gear_color
                        ac.setFontColor(self.gear_label, r, g, b, opacity)
                    if self.gear_label_bold:
                        ac.setFontColor(self.gear_label_bold, r, g, b, opacity)
                    if self.fuel_label:
                        ac.setFontColor(self.fuel_label, 0.72, 0.72, 0.72, opacity)
                    if self.est_laps_label:
                        ac.setFontColor(self.est_laps_label, 0.72, 0.72, 0.72, opacity)
                    if self.speed_unit_label:
                        ac.setFontColor(self.speed_unit_label, 0.75, 0.75, 0.75, 0.85 * opacity)
                    if self.speed_label:
                        ac.setFontColor(self.speed_label, 1.0, 1.0, 1.0, opacity)
                except Exception:
                    pass

                # Update bar percentage label colors
                try:
                    for item in self._bar_items:
                        lbl = item.get('label')
                        if lbl and item.get('label_color'):
                            r, g, b = item.get('label_color')
                            ac.setFontColor(lbl, r, g, b, opacity)
                except Exception:
                    pass

            # Layout and sizing changes are applied atomically by recreating
            # the graph+pedals area to avoid transient visual glitches.
            elif key in _LAYOUT_KEYS:
                try:
                    self._recreate_layout_atomic()
                except Exception:
                    pass

            elif key == 'sample_rate':
                self._update_timeout = 1.0 / max(self.config.sample_rate, 1)
            elif key == 'steering_sensitivity' and self.steering_wheel:
                self.steering_wheel.max_deg = max(1.0, self.config.steering_sensitivity / 2.0)

        design_spinners = {}

        def _make_spinner_handler(spinner_id, key, to_config, live_apply):
            def handler(*args):
                try:
                    raw_val = ac.getValue(spinner_id)
                except Exception:
                    return
                new_val = to_config(raw_val)
                setattr(self.config, key, new_val)
                if key == 'padding':
                    # Master padding updates all side paddings; side controls
                    # can then be used as per-side overrides.
                    self.config.padding_left = int(new_val)
                    self.config.padding_right = int(new_val)
                    self.config.padding_top = int(new_val)
                    self.config.padding_bottom = int(new_val)
                    for side_key in _SIDE_PAD_KEYS:
                        try:
                            ac.setValue(design_spinners[side_key], int(new_val))
                        except Exception:
                            pass
                self.config.update_cfg = True
                if live_apply:
                    _apply_live_setting(key)
            return handler

        # Left column: checkboxes
        left_x = pad
        right_x = pad + left_col_w + pad
        y_left = pad
        y_right = pad

        for sec_name, items in sections:
            y_left = _add_section_header(left_x, y_left, sec_name)

            for label_text, key in items:
                cb = ac.addCheckBox(win, '')
                ac.setPosition(cb, left_x, y_left)
                ac.setSize(cb, 16, 16)
                ac.setValue(cb, 1 if getattr(cfg, key, False) else 0)

                # Per-checkbox closure — captures key, stored to prevent GC.
                def make_handler(k):
                    def handler(*args):
                        new_val = not getattr(self.config, k, False)
                        setattr(self.config, k, new_val)
                        self.config.update_cfg = True
                        if k in _BAR_VIS_KEYS:
                            self._refresh_bar_visibility()
                        elif k in _REBUILD_KEYS:
                            try:
                                self._recreate_layout_atomic()
                            except Exception:
                                pass
                        elif k in _INFO_KEYS:
                            self._apply_info_visibility()
                            self._refresh_bar_visibility()
                            if k == 'show_fuel' and self.config.show_fuel and self.fuel_label is None:
                                try:
                                    self._recreate_layout_atomic()
                                except Exception:
                                    pass

                        if k == 'show_gear_color':
                            if self.gear_label:
                                try:
                                    ac.setFontColor(self.gear_label, 1.0, 1.0, 1.0, self.config.opacity)
                                except Exception:
                                    pass
                            if self.gear_label_bold:
                                try:
                                    ac.setFontColor(self.gear_label_bold, 1.0, 1.0, 1.0, self.config.opacity)
                                except Exception:
                                    pass
                            self._last_gear_color = (1.0, 1.0, 1.0)
                        if k == 'show_graph_lines':
                            try:
                                self._recreate_layout_atomic()
                            except Exception:
                                pass
                        if k in _TRACE_VIS_KEYS:
                            try:
                                self._recreate_layout_atomic()
                            except Exception:
                                pass
                    return handler

                h = make_handler(key)
                self._settings_handlers.append(h)
                ac.addOnCheckBoxChanged(cb, h)

                lbl = ac.addLabel(win, label_text)
                ac.setPosition(lbl, left_x + 16 + 6, y_left - 2)
                ac.setFontSize(lbl, 13)
                y_left += row_h

            y_left += gap

        # Bar Order section
        _ORDER_KEYS   = ('throttle', 'brake', 'clutch', 'ffb')
        _ORDER_LABELS = ('Throttle', 'Brake', 'Clutch', 'FFB')

        y_left = _add_section_header(left_x, y_left, 'Bar Order')

        def _get_order():
            order = [s.strip() for s in self.config.bar_order.split(',') if s.strip() in _ORDER_KEYS]
            for k in _ORDER_KEYS:
                if k not in order:
                    order.append(k)
            return order

        ord_label_w = 70
        ord_spin_w  = 50
        ord_spin_h  = 22

        def _make_order_handler(bar_key, spinner):
            def handler(*args):
                try:
                    new_pos = max(0, min(3, int(ac.getValue(spinner)) - 1))
                    order = _get_order()
                    order.remove(bar_key)
                    order.insert(new_pos, bar_key)
                    self.config.bar_order = ','.join(order)
                    self.config.update_cfg = True
                    self._recreate_layout_atomic()
                except Exception:
                    pass
            return handler

        current_order = _get_order()
        for bar_key, bar_label in zip(_ORDER_KEYS, _ORDER_LABELS):
            sp = _add_labeled_spinner(
                bar_label, left_x, y_left, ord_label_w, ord_spin_w, ord_spin_h,
                1, 4, 1, current_order.index(bar_key) + 1
            )
            h = _make_order_handler(bar_key, sp)
            self._settings_handlers.append(h)
            ac.addOnValueChangeListener(sp, h)
            y_left += row_h

        y_left += gap

        # Design controls on the right column
        y_right = _add_section_header(right_x, y_right, 'Design')

        label_w = 126
        spin_w = 108
        spin_h = 22

        for label_text, key, min_v, max_v, step_v, live_apply, to_cfg, from_cfg in design_rows:
            sp = _add_labeled_spinner(
                label_text, right_x, y_right, label_w, spin_w, spin_h,
                min_v, max_v, step_v, from_cfg(getattr(cfg, key))
            )
            design_spinners[key] = sp

            h = _make_spinner_handler(sp, key, to_cfg, live_apply)
            self._settings_handlers.append(h)
            ac.addOnValueChangeListener(sp, h)
            y_right += row_h

        final_y = max(y_left, y_right) + gap
        ac.setSize(self.settings_bg, w, final_y + pad)
        ac.setSize(win, w, final_y + pad)
        ac.setBackgroundOpacity(win, 0.0)


