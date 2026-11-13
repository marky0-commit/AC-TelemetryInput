import ac
import acsys
import math
import os

from _TelemetryInput.utils import console


class ACGraph:
    """
    Scrolling multi-trace graph using AC's native ac.addGraph API.

    Trace thickness is achieved by stacking `trace_width` graphs offset by 1px.
    The background is a label widget so it stays behind the graph traces.
    """

    def __init__(self, window, x, y, width, height, trace_width=2, opacity=0.5, show_lines=True):
        self.window = window
        self.x = int(x)
        self.y = int(y)
        self.width = int(width)
        self.height = int(height)
        self.trace_width = max(1, int(trace_width))
        self.opacity = opacity
        # Single AC graph widget; thickness achieved by multiple series
        self.graph_widget = None
        self._series_count = 0
        self.traces = []
        # Precompute symmetric integer offsets used to nudge series pixels
        # Precompute symmetric offsets used to nudge series pixels so a
        # thick trace looks centered and the edges blend better. For odd
        # widths we keep integer offsets (centered on a pixel). For even
        # widths we use half-pixel offsets (e.g. [-0.5, 0.5]) to reduce
        # the stepped appearance.
        def _compute_offsets(n):
            # Always use integer offsets so series land on distinct pixels.
            # Centered: for n=1 → [0], n=2 → [-1,0], n=3 → [-1,0,1], etc.
            half = n // 2
            return [float(i - half) for i in range(n)]

        self._series_offsets = tuple(_compute_offsets(self.trace_width))

        # Guide lines (labels placed between bg_label and graph_widget).
        # Creation is conditional on the `show_lines` flag so the app
        # settings control a single source of truth for guide rendering.
        self.show_graph_lines = bool(show_lines)
        self._guide_fractions = [0.25, 0.50, 0.75]
        self._guide_series_indices = []

        # Background drawn as a label (behind all graph widgets)
        self.bg_label = ac.addLabel(window, '')
        ac.setPosition(self.bg_label, self.x, self.y)
        ac.setSize(self.bg_label, self.width, self.height)
        # Use a lighter mid-gray background for better contrast
        ac.setBackgroundColor(self.bg_label, 0.18, 0.18, 0.18)
        ac.setBackgroundOpacity(self.bg_label, float(self.opacity))

        self._setup_graphs()

    def _setup_graphs(self):
        # (Guide series are added into the graph widget after the graph
        # is created so they render beneath subsequent trace series.)

        # Create a single, full-size graph widget. We'll add multiple
        # series into this one graph and shift their pixel values by
        # integer offsets to produce a thick trace without drawing into
        # padding.
        g = ac.addGraph(self.window, '')
        # Range -2 to height: value=0 maps to -2 (1px below bottom gap),
        # value=1 maps to height (top edge).
        ac.setRange(g, -2.0, self.height, self.width)
        ac.setPosition(g, self.x, self.y)
        ac.setSize(g, self.width, self.height)
        ac.setBackgroundOpacity(g, 0)
        try:
            ac.drawBorder(g, 0)
        except Exception:
            pass

        self.graph_widget = g

        # Add guide series (these series are drawn first so traces render
        # visually on top of them). We keep a list of their series indices
        # so we can feed constant values to them each update tick.
        try:
            if self.show_graph_lines:
                gr, gg, gb = 0.45, 0.45, 0.45
                for frac in self._guide_fractions:
                    try:
                        ac.addSerieToGraph(self.graph_widget, gr, gg, gb)
                        self._guide_series_indices.append(self._series_count)
                        self._series_count += 1
                    except Exception:
                        pass
        except Exception:
            pass

    def add_trace(self, color):
        """Add a new data series. Returns an ACGraphTrace to push values into."""
        idx = len(self.traces)
        trace = ACGraphTrace(self, color, idx)
        self.traces.append(trace)
        r, g, b, a = color
        # Add `trace_width` series per trace into the single graph and
        # remember their series indices for add_value calls. To soften
        # the visual edges we blend outer series colors toward the
        # background color (fade), producing a smoother-looking trace.
        trace._series_indices = []
        offsets = self._series_offsets
        max_off = max(abs(o) for o in offsets) if offsets else 1.0
        # background color used for blending (matches bg_label)
        bg_r, bg_g, bg_b = 0.18, 0.18, 0.18
        # Use a gentler fade so edges are softened without losing
        # brightness. Ensure a minimum weight so outer series remain
        # reasonably visible.
        fade_strength = 0.35
        min_weight = 0.7
        for off in offsets:
            # weight: 1.0 at centre, reduced toward edges but clamped
            if max_off > 0:
                w = 1.0 - (abs(off) / max_off) * fade_strength
                weight = max(min_weight, min(1.0, w))
            else:
                weight = 1.0

            # lerp toward background to simulate a subtle fade
            sr = bg_r + weight * (r - bg_r)
            sg = bg_g + weight * (g - bg_g)
            sb = bg_b + weight * (b - bg_b)

            # Register the series color (do not further darken by UI
            # opacity here — backgrounds/labels already follow cfg.opacity)
            ac.addSerieToGraph(self.graph_widget, sr, sg, sb)
            trace._series_indices.append(self._series_count)
            self._series_count += 1
        return trace

    def set_opacity(self, opacity):
        self.opacity = opacity
        ac.setBackgroundOpacity(self.bg_label, opacity)

    def update_guides(self):
        """Push constant values to guide series so they draw as horizontal lines."""
        graph_widget = self.graph_widget
        if not self.show_graph_lines or graph_widget is None:
            return

        height = float(self.height)
        for frac, series_idx in zip(self._guide_fractions, self._guide_series_indices):
            try:
                pixel_val = height * (1.0 - float(frac))
                if pixel_val < 0.0:
                    pixel_val = 0.0
                elif pixel_val > height:
                    pixel_val = height
                ac.addValueToGraph(graph_widget, series_idx, pixel_val)
            except Exception:
                pass


class ACGraphTrace:
    """A single series inside an ACGraph. Call add_value() each sample tick."""

    def __init__(self, graph, color, index):
        self._graph = graph
        self.color = color
        self._index = index

    def add_value(self, value):
        # Range is -2 to height. Map 0.0 → -2 (fills bottom gap),
        # and 1.0 → height (top edge, no 1px headroom).
        # Formula: full_pixel = value * (height + 2) - 2
        graph = self._graph
        height = float(graph.height)
        min_bottom = -2.0
        max_top = height

        full_pixel = float(value) * (height + 2.0) - 2.0
        full_pixel = max(min_bottom, min(max_top, full_pixel))

        offsets = graph._series_offsets
        graph_widget = graph.graph_widget
        for off, series_idx in zip(offsets, self._series_indices):
            val = max(min_bottom, min(max_top, full_pixel + off))
            try:
                ac.addValueToGraph(graph_widget, series_idx, val)
            except Exception:
                pass


class SteeringWheel:
    """
    Steering wheel rendered from a PNG texture.

    Vanilla AC can draw textured quads but cannot rotate them in real time.
    If CSP texture APIs are available, rotate the PNG via ext_glVertexTex.
    Otherwise draw the PNG statically and keep the coloured hub dot on top.
    """

    HUB_RATIO = 0.123   # hub radius as fraction of wheel radius

    def __init__(self, window, cx, cy, radius, max_deg=180, icons_dir='', image_filename='wheel_ring.png', config=None):
        self.cx = cx
        self.cy = cy
        self.radius = radius
        self.max_deg = max_deg
        self.steering_deg = 0.0
        self._texture = -1
        self._can_rotate_texture = (
            hasattr(ac, 'ext_glSetTexture') and hasattr(ac, 'ext_glVertexTex')
        )
        # Optional config object (instance of Config)
        self._cfg = config

        if not icons_dir:
            return

        ring_path = os.path.join(icons_dir, image_filename)
        if not os.path.isfile(ring_path):
            console('SteeringWheel: image not found: ' + ring_path)
            return

        self._texture = ac.newTexture(ring_path)
        if self._texture == -1:
            console('SteeringWheel: ac.newTexture failed for: ' + ring_path)
        elif self._can_rotate_texture:
            console('SteeringWheel: CSP texture rotation active')
        else:
            console('SteeringWheel: vanilla AC detected - wheel image will stay static')

    def render(self, opacity):
        cx, cy, r = self.cx, self.cy, self.radius

        # Respect global opacity when rendering wheel visuals.
        if self._texture != -1 and self._can_rotate_texture:
            self._draw_rotated_texture(cx, cy, r, self.steering_deg, opacity)
        elif self._texture != -1:
            ac.glColor4f(1.0, 1.0, 1.0, float(opacity))
            # Scale the wheel image down, but avoid extreme shrinkage for small radii.
            diam = r * 2.0
            cfg = getattr(self, '_cfg', None)
            reduction_total = getattr(cfg, 'wheel_image_shrink_total', 20.0) if cfg is not None else 20.0
            min_scale = getattr(cfg, 'wheel_image_min_scale', 0.7) if cfg is not None else 0.7
            img_size = max(1.0, max(diam - float(reduction_total), diam * float(min_scale)))
            half = img_size / 2.0
            ac.glQuadTextured(cx - half, cy - half, img_size, img_size, self._texture)
        else:
            # Multiply ring alpha by opacity so the ring respects global opacity
            self._draw_ring(cx, cy, r * 0.76, r, 0.35, 0.35, 0.35, float(opacity))

    def _draw_rotated_texture(self, cx, cy, r, angle_deg, opacity):
        angle_rad = math.radians(angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # Compute rotated texture size using same scaling logic as static draw
        diam = r * 2.0
        cfg = getattr(self, '_cfg', None)
        reduction_total = getattr(cfg, 'wheel_image_shrink_total', 20.0) if cfg is not None else 20.0
        min_scale = getattr(cfg, 'wheel_image_min_scale', 0.7) if cfg is not None else 0.7
        img_size = max(1.0, max(diam - float(reduction_total), diam * float(min_scale)))
        img_half = img_size / 2.0
        corners = [(-img_half, -img_half), (img_half, -img_half), (img_half, img_half), (-img_half, img_half)]
        tex_uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]

        ac.glColor4f(1.0, 1.0, 1.0, float(opacity))
        ac.glBegin(acsys.GL.Quads)
        ac.ext_glSetTexture(self._texture, 0)
        for (lx, ly), (u, v) in zip(corners, tex_uvs):
            wx = cx + cos_a * lx - sin_a * ly
            wy = cy + sin_a * lx + cos_a * ly
            ac.ext_glVertexTex(wx, wy, u, v)
        ac.glEnd()

    def _draw_ring(self, cx, cy, r_inner, r_outer, red, g, b, a):
        ac.glColor4f(red, g, b, a)
        n = 32
        ac.glBegin(acsys.GL.Quads)
        for i in range(n):
            a1 = 2 * math.pi * i / n
            a2 = 2 * math.pi * (i + 1) / n
            ac.glVertex2f(cx + math.cos(a1) * r_inner, cy + math.sin(a1) * r_inner)
            ac.glVertex2f(cx + math.cos(a1) * r_outer, cy + math.sin(a1) * r_outer)
            ac.glVertex2f(cx + math.cos(a2) * r_outer, cy + math.sin(a2) * r_outer)
            ac.glVertex2f(cx + math.cos(a2) * r_inner, cy + math.sin(a2) * r_inner)
        ac.glEnd()

class InputBar:
    """Vertical bar that fills bottom-up proportional to value (0-1)."""

    def __init__(self, x, y, width, height, color):
        self.x = int(x)
        self.y = int(y)
        self.width = int(width)
        self.height = int(height)
        self.color = color
        self.value = 0.0
        self.is_ffb = False
        self.show_base_stop = True
        self.show_end_stop = True

    def render(self, opacity):
        track_x = self.x
        track_y = self.y
        track_w = self.width
        track_h = self.height
        value = self.value
        bg_alpha = min(1.0, opacity + 0.12)
        base_gray = 0.34
        if self.is_ffb:
            ac.glColor4f(base_gray, base_gray, base_gray, bg_alpha)
            ac.glQuad(track_x, track_y, track_w, track_h)
            fill_h = int(value * track_h)
            if value > 0.0 and fill_h == 0:
                fill_h = 1
            if fill_h > 0:
                if value >= 0.999:
                    ac.glColor4f(1.0, 0.0, 0.0, opacity)
                else:
                    r, g, b, a = self.color
                    ac.glColor4f(r, g, b, opacity)
                ac.glQuad(track_x, track_y + track_h - fill_h, track_w, fill_h)
            return

        # Default: dark background, coloured fill, no outlines
        stop_h = 2
        stop_gap = 1
        show_base = self.show_base_stop
        show_end  = self.show_end_stop
        top_stop_y = track_y + 1
        bottom_stop_y = track_y + track_h - stop_h
        # Body region adjusts based on which stops are visible
        body_top = (top_stop_y + stop_h + stop_gap) if show_end else (track_y + 1)
        body_bot = (bottom_stop_y - stop_gap)        if show_base else (track_y + track_h)
        body_y = body_top
        body_h = max(1, body_bot - body_y)

        ac.glColor4f(base_gray, base_gray, base_gray, bg_alpha)
        ac.glQuad(track_x, body_y, track_w, body_h)
        if show_end:
            ac.glQuad(track_x, top_stop_y, track_w, stop_h)
        if show_base:
            ac.glQuad(track_x, bottom_stop_y, track_w, stop_h)

        fill_h = int(value * body_h)
        if value > 0.0 and fill_h == 0:
            fill_h = 1
        if fill_h > 0:
            r, g, b, a = self.color
            ac.glColor4f(r, g, b, opacity)
            ac.glQuad(track_x, body_y + body_h - fill_h, track_w, fill_h)

        # Stop markers turn color only when active; otherwise stay gray
        if show_base and value >= 0.003:
            r, g, b, a = self.color
            ac.glColor4f(r, g, b, min(1.0, opacity + 0.15))
            ac.glQuad(track_x, bottom_stop_y, track_w, stop_h)

        if show_end and value >= 1.0:
            r, g, b, a = self.color
            ac.glColor4f(r, g, b, min(1.0, opacity + 0.15))
            ac.glQuad(track_x, top_stop_y, track_w, stop_h)
