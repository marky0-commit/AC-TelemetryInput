"""
Run with system Python to generate app image assets.

Usage:
    python generate_assets.py              # generates default procedural F1 wheel
    python generate_assets.py f1wheel.png  # converts your own wheel PNG (needs Pillow: pip install Pillow)
                                           # file must be in the icons/ folder or provide full path
"""
import os, math, struct, zlib, sys

ICONS_DIR = os.path.join(os.path.dirname(__file__), 'icons')
RING_OUT  = os.path.join(ICONS_DIR, 'wheel_ring.png')
SIZE      = 256

CX = CY  = SIZE / 2.0
SCALE      = SIZE / 2.0 * 0.92
R_OUTER    = SCALE
R_INNER    = SCALE * 0.76
R_HUB      = SCALE * 0.14
R_HUB_HOLE = SCALE * 0.07
SPOKE_START_DEG = 90.0
SPOKE_HALF_ARC  = 14.0


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def dist(x, y):
    return math.sqrt((x - CX) ** 2 + (y - CY) ** 2)


def angle_deg_from_12(x, y):
    return (math.degrees(math.atan2(x - CX, -(y - CY)))) % 360.0


def aa_edge(d, r, feather=0.9):
    return clamp((r + feather - d) / (2.0 * feather))


def spoke_gap(ang):
    for i in range(3):
        centre = (SPOKE_START_DEG + i * 120.0) % 360.0
        lo = (centre - SPOKE_HALF_ARC) % 360.0
        hi = (centre + SPOKE_HALF_ARC) % 360.0
        if lo < hi:
            if lo <= ang <= hi:
                return True
        else:
            if ang >= lo or ang <= hi:
                return True
    return False


def sample_pixel(x, y):
    d   = dist(x, y)
    ang = angle_deg_from_12(x, y)
    outer_a = aa_edge(d, R_OUTER)
    if outer_a <= 0:
        return (0, 0, 0, 0)
    if d <= R_HUB + 1.0:
        if d <= R_HUB_HOLE + 0.5:
            hole_a = 1.0 - aa_edge(d, R_HUB_HOLE, 0.7)
            return (20, 20, 20, int(hole_a * outer_a * 255))
        hub_a = aa_edge(d, R_HUB, 0.7) * outer_a
        return (200, 195, 195, int(hub_a * 255))
    if d < R_INNER - 0.5 and d > R_HUB + 1.0:
        return (0, 0, 0, 0)
    if d >= R_INNER - 1.0 and d <= R_OUTER + 1.0:
        if spoke_gap(ang) and d < R_INNER + (R_OUTER - R_INNER) * 0.45:
            gap_fade = clamp((d - R_INNER + 2.0) / 4.0)
            if gap_fade < 0.05:
                return (0, 0, 0, 0)
            rim_fill_a = gap_fade
        else:
            rim_fill_a = 1.0
        inner_a   = aa_edge(d, R_INNER, 0.9)
        rim_alpha = aa_edge(d, R_OUTER) * inner_a * outer_a * rim_fill_a
        highlight = clamp(1.0 - (y - CY + R_OUTER) / (2.0 * R_OUTER))
        r_base = int(clamp(0.30 + 0.18 * highlight) * 255)
        g_base = int(clamp(0.30 + 0.18 * highlight) * 255)
        b_base = int(clamp(0.32 + 0.18 * highlight) * 255)
        return (r_base, g_base, b_base, int(rim_alpha * 255))
    return (0, 0, 0, 0)


def write_png(path, width, height, pixels_rgba):
    def chunk(tag, data):
        c = tag + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)
    sig  = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    raw  = bytearray()
    for row in range(height):
        raw.append(0)
        for col in range(width):
            raw.extend(pixels_rgba[row * width + col])
    idat = chunk(b'IDAT', zlib.compress(bytes(raw), 9))
    iend = chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(sig + ihdr + idat + iend)


os.makedirs(ICONS_DIR, exist_ok=True)

if len(sys.argv) >= 2:
    # --- Convert a user-supplied image ---
    try:
        from PIL import Image
    except ImportError:
        print('Pillow not installed. Run:  pip install Pillow')
        sys.exit(1)

    src = sys.argv[1]
    if not os.path.isfile(src):
        src = os.path.join(ICONS_DIR, sys.argv[1])
    if not os.path.isfile(src):
        print('File not found: ' + sys.argv[1])
        sys.exit(1)

    print('Loading: ' + src)
    img = Image.open(src).convert('RGBA')
    w, h = img.size
    side = min(w, h)
    img  = img.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))

    # Remove white/near-white background via corner flood-fill
    from collections import deque
    pixels = img.load()
    visited = [[False] * side for _ in range(side)]
    queue   = deque()
    for sx, sy in [(0,0),(side-1,0),(0,side-1),(side-1,side-1)]:
        r, g, b, a = pixels[sx, sy]
        if r >= 220 and g >= 220 and b >= 220 and not visited[sx][sy]:
            queue.append((sx, sy))
            visited[sx][sy] = True
    while queue:
        x, y = queue.popleft()
        r, g, b, a = pixels[x, y]
        pixels[x, y] = (r, g, b, 0)
        for nx, ny in [(x-1,y),(x+1,y),(x,y-1),(x,y+1)]:
            if 0 <= nx < side and 0 <= ny < side and not visited[nx][ny]:
                nr, ng, nb, na = pixels[nx, ny]
                if nr >= 190 and ng >= 190 and nb >= 190:
                    visited[nx][ny] = True
                    queue.append((nx, ny))

    img = img.resize((SIZE, SIZE), Image.LANCZOS)
    img.save(RING_OUT)
    print('Saved: ' + RING_OUT)

else:
    # --- Generate procedural F1-style wheel ---
    print('Rendering procedural {}x{} wheel...'.format(SIZE, SIZE))
    pixels = [sample_pixel(col + 0.5, row + 0.5) for row in range(SIZE) for col in range(SIZE)]
    write_png(RING_OUT, SIZE, SIZE, pixels)
    print('Saved: ' + RING_OUT)
    print('To use your own image:  python generate_assets.py f1wheel.png')
