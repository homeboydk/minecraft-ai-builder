#!/usr/bin/env python3
"""
Hvidovrehavn 1:1 scale builder v2 - STRIP BASED with bbox fills.
Builds in 128-block Z-strips, forceloading only active chunks.
Bbox: S=55.614, W=12.470, N=55.630, E=12.507
Scale 1:1 (1 meter = 1 block)
Origin (SW corner) → MC X=5000, Z=5000
Flat world: bedrock Y=-64, stone Y=-63/-62, grass Y=-61, air Y=-60+
"""

import socket, struct, time, math, json, os, urllib.request, urllib.error, urllib.parse

# ── CONFIG ───────────────────────────────────────────────────────────────────
HOST, PORT, PASS = '127.0.0.1', 25575, 'NME21o3#'

BBOX_S, BBOX_W = 55.614, 12.470
BBOX_N, BBOX_E = 55.630, 12.507

ORIGIN_LAT = BBOX_S
ORIGIN_LON = BBOX_W

MC_ORIGIN_X = 5000
MC_ORIGIN_Z = 5000

LAT_REF = 55.622
METERS_PER_LAT = 111320.0
METERS_PER_LON = 111320.0 * math.cos(math.radians(LAT_REF))  # ~62845

SCALE = 1.0   # 1 meter = 1 block

OSM_CACHE = '/tmp/osm_havn_1to1.json'

GROUND_Y = -61   # grass_block
BASE_Y   = -60   # ground surface to build on
WATER_Y  = -63   # water surface (sunken below grass)
WATER_BED = -65  # stone under water

STRIP_W  = 128   # Z-strip width in blocks (= 8 chunks per strip)

# ── RCON ─────────────────────────────────────────────────────────────────────
def connect():
    s = socket.socket()
    s.settimeout(20)
    s.connect((HOST, PORT))
    def pkt(rid, rt, p):
        d = p.encode('utf-8') + b'\x00\x00'
        s.send(struct.pack('<iii', len(d) + 8, rid, rt) + d)
        r = b''
        while len(r) < 4 or len(r) < struct.unpack('<i', r[:4])[0] + 4:
            chunk = s.recv(4096)
            if not chunk:
                break
            r += chunk
        return r[12:-2].decode('utf-8', 'replace')
    pkt(1, 3, PASS)
    return s, pkt

_s, _pkt = connect()
cmd_count = 0
errors = 0

def cmd(c):
    global _s, _pkt, cmd_count, errors
    try:
        r = _pkt(2, 2, c)
        cmd_count += 1
        if cmd_count % 500 == 0:
            print(f"  [{cmd_count} cmds]", end='\r', flush=True)
        return r
    except Exception as e:
        errors += 1
        time.sleep(0.5)
        try: _s.close()
        except: pass
        try:
            _s, _pkt = connect()
            return _pkt(2, 2, c)
        except:
            return ""

def F(x1, y1, z1, x2, y2, z2, blk, mode=""):
    """Fill region, auto-split > 32768 blocks."""
    if x1 > x2: x1, x2 = x2, x1
    if y1 > y2: y1, y2 = y2, y1
    if z1 > z2: z1, z2 = z2, z1
    vol = (x2-x1+1)*(y2-y1+1)*(z2-z1+1)
    if vol > 32768:
        dx,dy,dz = x2-x1+1, y2-y1+1, z2-z1+1
        if dx >= dy and dx >= dz:
            m = x1+dx//2-1; F(x1,y1,z1,m,y2,z2,blk,mode); F(m+1,y1,z1,x2,y2,z2,blk,mode)
        elif dy >= dz:
            m = y1+dy//2-1; F(x1,y1,z1,x2,m,z2,blk,mode); F(x1,m+1,z1,x2,y2,z2,blk,mode)
        else:
            m = z1+dz//2-1; F(x1,y1,z1,x2,y2,m,blk,mode); F(x1,y1,m+1,x2,y2,z2,blk,mode)
        return
    sfx = f" {mode}" if mode else ""
    cmd(f"fill {x1} {y1} {z1} {x2} {y2} {z2} {blk}{sfx}")

def S(x,y,z,blk):
    cmd(f"setblock {x} {y} {z} {blk}")

# ── COORDINATES ──────────────────────────────────────────────────────────────
def geo_to_mc(lat, lon):
    dlon = lon - ORIGIN_LON
    dlat = lat - ORIGIN_LAT
    mc_x = MC_ORIGIN_X + int(round(dlon * METERS_PER_LON * SCALE))
    mc_z = MC_ORIGIN_Z - int(round(dlat * METERS_PER_LAT * SCALE))
    return mc_x, mc_z

MC_SW = geo_to_mc(BBOX_S, BBOX_W)
MC_NE = geo_to_mc(BBOX_N, BBOX_E)
MC_MIN_X = min(MC_SW[0], MC_NE[0])
MC_MAX_X = max(MC_SW[0], MC_NE[0])
MC_MIN_Z = min(MC_SW[1], MC_NE[1])
MC_MAX_Z = max(MC_SW[1], MC_NE[1])

print(f"Build area: X={MC_MIN_X}..{MC_MAX_X}  Z={MC_MIN_Z}..{MC_MAX_Z}")
print(f"Size: {MC_MAX_X-MC_MIN_X} × {MC_MAX_Z-MC_MIN_Z} blocks")
print(f"METERS_PER_LON={METERS_PER_LON:.0f}")

# ── OSM DATA ─────────────────────────────────────────────────────────────────
OVERPASS_QUERY = """
[out:json][timeout:90];
(
  way["building"](55.614,12.470,55.630,12.507);
  way["highway"](55.614,12.470,55.630,12.507);
  way["natural"="water"](55.614,12.470,55.630,12.507);
  way["waterway"](55.614,12.470,55.630,12.507);
  way["natural"="beach"](55.614,12.470,55.630,12.507);
  way["leisure"="beach"](55.614,12.470,55.630,12.507);
  way["landuse"](55.614,12.470,55.630,12.507);
  way["leisure"](55.614,12.470,55.630,12.507);
  way["man_made"](55.614,12.470,55.630,12.507);
  way["amenity"](55.614,12.470,55.630,12.507);
);
out body geom;
""".strip()

def download_osm():
    if os.path.exists(OSM_CACHE):
        print(f"Using cached: {OSM_CACHE}")
        with open(OSM_CACHE) as f:
            return json.load(f)
    print("Downloading from Overpass...")
    data = urllib.parse.urlencode({'data': OVERPASS_QUERY}).encode()
    req = urllib.request.Request("https://overpass-api.de/api/interpreter", data=data)
    req.add_header('User-Agent', 'MinecraftOSMBuilder/2.0')
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode()
    result = json.loads(raw)
    with open(OSM_CACHE, 'w') as f:
        json.dump(result, f)
    print(f"Downloaded {len(result.get('elements',[]))} elements")
    return result

# ── POLYGON TOOLS ─────────────────────────────────────────────────────────────
def way_pts(way):
    pts = []
    for nd in way.get('geometry', []):
        try: pts.append(geo_to_mc(nd['lat'], nd['lon']))
        except: pass
    return pts

def poly_bbox(pts):
    if not pts: return None
    xs = [p[0] for p in pts]
    zs = [p[1] for p in pts]
    return min(xs), max(xs), min(zs), max(zs)

def scanline_fill(pts, y, blk, z_clip_min=None, z_clip_max=None):
    """Scanline fill polygon at height y. Optionally clips to Z range."""
    if len(pts) < 3: return
    zs = [p[1] for p in pts]
    min_z, max_z = min(zs), max(zs)
    if z_clip_min is not None: min_z = max(min_z, z_clip_min)
    if z_clip_max is not None: max_z = min(max_z, z_clip_max)
    if min_z > max_z: return
    n = len(pts)
    for scan_z in range(min_z, max_z + 1):
        xs_int = []
        for i in range(n):
            x1, z1 = pts[i]
            x2, z2 = pts[(i+1) % n]
            if z1 == z2: continue
            # Use half-open interval to avoid double-counting vertices
            if z1 <= z2:
                lo, hi = z1, z2
                if not (lo <= scan_z < hi): continue
            else:
                lo, hi = z2, z1
                if not (lo <= scan_z < hi): continue
            t = (scan_z - z1) / (z2 - z1)
            xs_int.append(x1 + t * (x2 - x1))
        if len(xs_int) < 2: continue
        xs_int.sort()
        for i in range(0, len(xs_int) - 1, 2):
            xi1 = int(math.floor(xs_int[i]))
            xi2 = int(math.ceil(xs_int[i+1]))
            if xi1 <= xi2:
                F(xi1, y, scan_z, xi2, y, scan_z, blk)

def scanline_fill_range(pts, y1, y2, blk, z_clip_min=None, z_clip_max=None):
    """Scanline fill polygon over vertical range."""
    if len(pts) < 3: return
    zs = [p[1] for p in pts]
    min_z, max_z = min(zs), max(zs)
    if z_clip_min is not None: min_z = max(min_z, z_clip_min)
    if z_clip_max is not None: max_z = min(max_z, z_clip_max)
    if min_z > max_z: return
    n = len(pts)
    for scan_z in range(min_z, max_z + 1):
        xs_int = []
        for i in range(n):
            x1, z1 = pts[i]
            x2, z2 = pts[(i+1) % n]
            if z1 == z2: continue
            if z1 <= z2:
                if not (z1 <= scan_z < z2): continue
            else:
                if not (z2 <= scan_z < z1): continue
            t = (scan_z - z1) / (z2 - z1)
            xs_int.append(x1 + t * (x2 - x1))
        if len(xs_int) < 2: continue
        xs_int.sort()
        for i in range(0, len(xs_int) - 1, 2):
            xi1 = int(math.floor(xs_int[i]))
            xi2 = int(math.ceil(xs_int[i+1]))
            if xi1 <= xi2:
                F(xi1, y1, scan_z, xi2, y2, scan_z, blk)

def draw_road(pts, y, blk, width):
    """Draw thick polyline road."""
    hw = max(0, width // 2)
    for i in range(len(pts) - 1):
        x1,z1 = pts[i]; x2,z2 = pts[i+1]
        steps = max(abs(x2-x1), abs(z2-z1), 1)
        for s in range(steps + 1):
            t = s / steps
            bx = int(round(x1 + t*(x2-x1)))
            bz = int(round(z1 + t*(z2-z1)))
            F(bx-hw, y, bz-hw, bx+hw, y, bz+hw, blk)

# ── FORCELOAD STRIP ───────────────────────────────────────────────────────────
def forceload_strip(z1, z2, load=True):
    """Forceload chunks covering X=MC_MIN_X..MC_MAX_X, Z=z1..z2."""
    action = "add" if load else "remove"
    x_step = 256
    for xa in range(MC_MIN_X, MC_MAX_X + 1, x_step):
        xb = min(xa + x_step - 1, MC_MAX_X)
        cmd(f"forceload {action} {xa} {z1} {xb} {z2}")
    time.sleep(0.1)   # Give server a moment to load chunks

# ── MATERIAL HELPERS ──────────────────────────────────────────────────────────
def bld_mat(tags):
    bt = tags.get('building','').lower()
    amenity = tags.get('amenity','').lower()
    if bt in ('apartments','flat'): return 'minecraft:light_gray_concrete'
    if bt in ('commercial','retail','office','supermarket'): return 'minecraft:smooth_stone'
    if bt in ('industrial','warehouse','factory'): return 'minecraft:red_concrete'
    if bt in ('school','hospital','civic','public') or amenity in ('school','hospital','university'):
        return 'minecraft:yellow_concrete'
    if bt in ('church','chapel','cathedral','place_of_worship'): return 'minecraft:stone_bricks'
    if bt in ('garage','garages','shed','hut','carport'): return 'minecraft:oak_planks'
    return 'minecraft:white_concrete'

def bld_height(tags):
    try: return max(3, int(float(tags['height'])))
    except: pass
    try: return max(3, int(float(tags['building:levels'])) * 3)
    except: pass
    bt = tags.get('building','').lower()
    if bt in ('garage','shed','carport','hut'): return 3
    if bt in ('apartments','flat'): return 9
    if bt in ('commercial','retail','office'): return 6
    if bt in ('industrial','warehouse'): return 5
    return 5

ROAD_SPECS = {
    'motorway':('minecraft:gray_concrete',8),
    'trunk':('minecraft:gray_concrete',7),
    'primary':('minecraft:gray_concrete',6),
    'secondary':('minecraft:smooth_stone',5),
    'tertiary':('minecraft:smooth_stone',4),
    'residential':('minecraft:smooth_stone',4),
    'unclassified':('minecraft:smooth_stone',3),
    'living_street':('minecraft:smooth_stone',3),
    'service':('minecraft:smooth_stone',3),
    'road':('minecraft:smooth_stone',4),
    'footway':('minecraft:gravel',2),
    'pedestrian':('minecraft:gravel',3),
    'path':('minecraft:gravel',2),
    'cycleway':('minecraft:gravel',2),
    'track':('minecraft:dirt_path',2),
    'steps':('minecraft:stone_bricks',2),
}
def road_spec(tags):
    hw = tags.get('highway','').lower()
    return ROAD_SPECS.get(hw, ('minecraft:smooth_stone',3))

def landuse_mat(tags):
    lu = tags.get('landuse','').lower()
    lei = tags.get('leisure','').lower()
    nat = tags.get('natural','').lower()
    if lu in ('park','garden','grass','recreation_ground') or lei in ('park','garden','pitch','playground'):
        return 'minecraft:moss_block'
    if lu in ('forest','wood') or nat in ('wood','scrub'):
        return 'minecraft:moss_block'
    if lu in ('residential',): return 'minecraft:dirt_path'
    if lu in ('commercial','retail','industrial'): return 'minecraft:smooth_stone'
    if lu in ('harbour','port') or lei in ('marina',): return 'minecraft:stone_bricks'
    if lu in ('farmland','allotments','meadow'): return 'minecraft:farmland'
    return None

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    osm = download_osm()
    elements = osm.get('elements', [])
    print(f"Loaded {len(elements)} OSM elements")

    buildings, roads, waters, beaches, landuses, piers = [], [], [], [], [], []
    for el in elements:
        if el.get('type') != 'way': continue
        tags = el.get('tags', {})
        if not el.get('geometry'): continue
        if tags.get('building'):
            buildings.append(el)
        elif tags.get('highway'):
            roads.append(el)
        elif tags.get('natural') == 'beach' or tags.get('leisure') == 'beach':
            beaches.append(el)
        elif tags.get('natural') in ('water',) or tags.get('waterway'):
            waters.append(el)
        elif tags.get('man_made') in ('pier','breakwater','jetty','groyne','seawall','quay'):
            piers.append(el)
        elif tags.get('landuse') or tags.get('leisure') or tags.get('natural'):
            landuses.append(el)

    print(f"Buildings:{len(buildings)} Roads:{len(roads)} Water:{len(waters)} "
          f"Beach:{len(beaches)} Landuse:{len(landuses)} Piers:{len(piers)}")

    # ── Verification marker ────────────────────────────────────────────────────
    print("\n[INIT] Placing verification markers (should appear instantly)...")
    # Load just the origin chunks
    cmd(f"forceload add {MC_MIN_X} {MC_MIN_Z} {MC_MIN_X+64} {MC_MIN_Z+64}")
    time.sleep(0.3)
    # Place 3 colored pillars at origin corner so player can find the build
    for dy in range(10):
        S(MC_MIN_X,   BASE_Y + dy, MC_MIN_Z,   'minecraft:red_concrete')
        S(MC_MIN_X+2, BASE_Y + dy, MC_MIN_Z,   'minecraft:yellow_concrete')
        S(MC_MIN_X+4, BASE_Y + dy, MC_MIN_Z,   'minecraft:lime_concrete')
    r = cmd(f"execute if block {MC_MIN_X} {BASE_Y} {MC_MIN_Z} minecraft:red_concrete")
    print(f"  Verify marker at {MC_MIN_X},{BASE_Y},{MC_MIN_Z}: {repr(r)}")
    if 'true' not in r.lower() and 'passed' not in r.lower():
        print("  WARNING: Test marker not confirmed! Chunks may not be loading correctly.")
        print("  Trying alternative approach...")
        # Try direct teleport to check
        cmd(f"tp HomeboyDK {MC_MIN_X} {BASE_Y+20} {MC_MIN_Z}")
        time.sleep(2)
        r2 = cmd(f"execute if block {MC_MIN_X} {BASE_Y} {MC_MIN_Z} minecraft:red_concrete")
        print(f"  After tp, verify: {repr(r2)}")

    # ── Process in Z-STRIPS ───────────────────────────────────────────────────
    total_strips = math.ceil((MC_MAX_Z - MC_MIN_Z + 1) / STRIP_W)
    print(f"\n[BUILD] Processing {total_strips} Z-strips of {STRIP_W} blocks each...")

    strip_num = 0
    for strip_z0 in range(MC_MIN_Z, MC_MAX_Z + 1, STRIP_W):
        strip_z1 = min(strip_z0 + STRIP_W - 1, MC_MAX_Z)
        strip_num += 1
        print(f"\n  Strip {strip_num}/{total_strips}: Z={strip_z0}..{strip_z1}")

        # Forceload this strip
        forceload_strip(strip_z0, strip_z1, True)

        # Clear strip: air from BASE_Y to 80
        F(MC_MIN_X, BASE_Y, strip_z0, MC_MAX_X, 80, strip_z1, 'minecraft:air')

        # Water
        for el in waters:
            pts = way_pts(el)
            if not pts: continue
            bb = poly_bbox(pts)
            if not bb or bb[3] < strip_z0 or bb[2] > strip_z1: continue
            if len(pts) >= 3:
                scanline_fill(pts, WATER_BED, 'minecraft:stone', strip_z0, strip_z1)
                scanline_fill(pts, WATER_BED+1, 'minecraft:stone', strip_z0, strip_z1)
                scanline_fill(pts, WATER_Y, 'minecraft:water', strip_z0, strip_z1)
                scanline_fill(pts, GROUND_Y, 'minecraft:air', strip_z0, strip_z1)
                scanline_fill(pts, BASE_Y, 'minecraft:air', strip_z0, strip_z1)
            else:
                draw_road(pts, WATER_Y, 'minecraft:water', 4)

        # Beach
        for el in beaches:
            pts = way_pts(el)
            if not pts or len(pts) < 3: continue
            bb = poly_bbox(pts)
            if not bb or bb[3] < strip_z0 or bb[2] > strip_z1: continue
            scanline_fill(pts, GROUND_Y, 'minecraft:sand', strip_z0, strip_z1)
            scanline_fill(pts, BASE_Y, 'minecraft:sand', strip_z0, strip_z1)

        # Landuse
        for el in landuses:
            pts = way_pts(el)
            if not pts or len(pts) < 3: continue
            bb = poly_bbox(pts)
            if not bb or bb[3] < strip_z0 or bb[2] > strip_z1: continue
            mat = landuse_mat(el.get('tags', {}))
            if mat is None: continue
            scanline_fill(pts, BASE_Y, mat, strip_z0, strip_z1)

        # Buildings (scanline fill for footprint + walls)
        for el in buildings:
            pts = way_pts(el)
            if not pts or len(pts) < 3: continue
            bb = poly_bbox(pts)
            if not bb or bb[3] < strip_z0 or bb[2] > strip_z1: continue
            tags = el.get('tags', {})
            wall = bld_mat(tags)
            height = bld_height(tags)
            roof_y = BASE_Y + height - 1
            # Floor
            scanline_fill(pts, BASE_Y, wall, strip_z0, strip_z1)
            # Walls (full height)
            if height > 1:
                scanline_fill_range(pts, BASE_Y + 1, roof_y - 1, wall, strip_z0, strip_z1)
            # Roof: gray concrete slab
            scanline_fill(pts, roof_y, 'minecraft:gray_concrete', strip_z0, strip_z1)

        # Roads (drawn ON TOP of everything else)
        for el in roads:
            pts = way_pts(el)
            if not pts: continue
            # Quick Z bbox check
            zvals = [p[1] for p in pts]
            if min(zvals) > strip_z1 or max(zvals) < strip_z0: continue
            tags = el.get('tags', {})
            mat, width = road_spec(tags)
            # Clip points to strip range (just skip segments fully outside)
            draw_road(pts, BASE_Y, mat, width)

        # Piers
        for el in piers:
            pts = way_pts(el)
            if not pts: continue
            zvals = [p[1] for p in pts]
            if min(zvals) > strip_z1 or max(zvals) < strip_z0: continue
            if len(pts) >= 3:
                bb = poly_bbox(pts)
                if bb and not (bb[3] < strip_z0 or bb[2] > strip_z1):
                    scanline_fill(pts, BASE_Y,   'minecraft:stone_bricks', strip_z0, strip_z1)
                    scanline_fill(pts, BASE_Y+1, 'minecraft:stone_bricks', strip_z0, strip_z1)
                    scanline_fill(pts, BASE_Y+2, 'minecraft:stone_bricks', strip_z0, strip_z1)
            else:
                draw_road(pts, BASE_Y,   'minecraft:stone_bricks', 5)
                draw_road(pts, BASE_Y+1, 'minecraft:stone_bricks', 5)
                draw_road(pts, BASE_Y+2, 'minecraft:stone_bricks', 5)

        # Unload this strip
        forceload_strip(strip_z0, strip_z1, False)
        print(f"    Strip done, {cmd_count} total cmds so far")

    # ── Teleport player to center overview ────────────────────────────────────
    cx = (MC_MIN_X + MC_MAX_X) // 2
    cz = (MC_MIN_Z + MC_MAX_Z) // 2
    # Re-load center for teleport
    cmd(f"forceload add {cx-64} {cz-64} {cx+64} {cz+64}")
    time.sleep(0.5)
    cmd(f"tp HomeboyDK {cx} 250 {cz}")
    cmd(f"forceload remove {cx-64} {cz-64} {cx+64} {cz+64}")

    print(f"\nDone! {cmd_count} total RCON commands, {errors} reconnects.")
    print(f"Build center: X={cx}, Z={cz}")
    print(f"SW corner markers: X={MC_MIN_X}, Z={MC_MIN_Z} (red/yellow/lime pillars)")

if __name__ == '__main__':
    main()
