"""
Converts any steering wheel photo (white/light background) into a transparent
RGBA PNG ready for use as icons/wheel_ring.png.

Usage:
    python process_wheel_image.py <path_to_your_image>

Example:
    python process_wheel_image.py wheel_source.jpg

Requires Pillow — install once with:
    pip install Pillow
"""
import sys, os

try:
    from PIL import Image
except ImportError:
    print("Pillow is not installed. Run:  pip install Pillow")
    sys.exit(1)

OUT = os.path.join(os.path.dirname(__file__), 'icons', 'wheel_ring.png')

# ---- Input ---------------------------------------------------------------
if len(sys.argv) < 2:
    # Auto-detect common filenames next to this script
    candidates = ['wheel_source.jpg', 'wheel_source.png', 'wheel_source.jpeg',
                  'wheel.jpg', 'wheel.png']
    src = None
    for c in candidates:
        p = os.path.join(os.path.dirname(__file__), c)
        if os.path.exists(p):
            src = p
            break
    if src is None:
        print("Usage: python process_wheel_image.py <your_image.jpg>")
        print("Or save your image as 'wheel_source.jpg' next to this script.")
        sys.exit(1)
else:
    src = sys.argv[1]

print(f"Loading: {src}")
img = Image.open(src).convert('RGBA')

# ---- Crop to tight square centred on the wheel ---------------------------
w, h = img.size
side = min(w, h)
left = (w - side) // 2
top  = (h - side) // 2
img  = img.crop((left, top, left + side, top + side))
w = h = side

# ---- Remove white / near-white background --------------------------------
# Strategy: flood-fill from the four corners to find background pixels,
# then replace them with transparent. Handles most product-photo backgrounds.

pixels = img.load()

# Threshold: pixels brighter than this in all channels are considered background
BG_THRESH   = 230
FLOOD_THRESH = 40   # how similar a neighbour must be to spread

def is_bg_seed(r, g, b, a):
    return r >= BG_THRESH and g >= BG_THRESH and b >= BG_THRESH

# BFS flood fill from all four corners
from collections import deque

visited = [[False] * h for _ in range(w)]
queue   = deque()

for sx, sy in [(0, 0), (w-1, 0), (0, h-1), (w-1, h-1)]:
    r, g, b, a = pixels[sx, sy]
    if is_bg_seed(r, g, b, a) and not visited[sx][sy]:
        queue.append((sx, sy))
        visited[sx][sy] = True

while queue:
    x, y = queue.popleft()
    r, g, b, a = pixels[x, y]
    pixels[x, y] = (0, 0, 0, 0)    # transparent with zeroed RGB to avoid white halo when rotated

    for nx, ny in [(x-1,y),(x+1,y),(x,y-1),(x,y+1)]:
        if 0 <= nx < w and 0 <= ny < h and not visited[nx][ny]:
            nr, ng, nb, na = pixels[nx, ny]
            # Spread if this neighbour is also near-white
            if nr >= BG_THRESH - FLOOD_THRESH and ng >= BG_THRESH - FLOOD_THRESH and nb >= BG_THRESH - FLOOD_THRESH:
                visited[nx][ny] = True
                queue.append((nx, ny))

# ---- Soft edge: feather any remaining near-white fringe ------------------
import math

for y in range(h):
    for x in range(w):
        r, g, b, a = pixels[x, y]
        if a > 0 and r > 200 and g > 200 and b > 200:
            # Partially transparent based on how white it is
            whiteness = (r + g + b) / 3.0
            fade = 1.0 - max(0.0, (whiteness - 210) / 45.0)
            pixels[x, y] = (r, g, b, int(a * fade))

# ---- Clean hidden RGB on fully transparent pixels -----------------------
# Some renderers sample RGB from neighboring transparent texels during
# rotation/bilinear filtering. Zeroing these texels prevents a faint square
# box or white halo from appearing around the wheel.
for y in range(h):
    for x in range(w):
        r, g, b, a = pixels[x, y]
        if a == 0:
            pixels[x, y] = (0, 0, 0, 0)

# ---- Resize to 256×256 for crisp in-game rendering ----------------------
TARGET = 256
img = img.resize((TARGET, TARGET), Image.LANCZOS)

# ---- Save ----------------------------------------------------------------
os.makedirs(os.path.dirname(OUT), exist_ok=True)
img.save(OUT)
print(f"Saved: {OUT}")
print("Restart Assetto Corsa (or reload the app) to see the new wheel.")
