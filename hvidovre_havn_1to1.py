#!/usr/bin/env python3
"""
Hvidovrehavn 1:1 scale builder for Minecraft.
Bounding box: S=55.614, W=12.470, N=55.630, E=12.507
Scale 1:1 (1 meter = 1 block)
Origin (SW corner 55.614°N, 12.470°E) → MC X=2000, Z=2000
Flat world ground at Y=-61 (grass_block), air from Y=-60 up.
"""

import socket, struct, time, math, json, os, urllib.request, urllib.error

# ── CONFIG ─────────────────────────────────────────────────────────────────────
HOST, PORT, PASS = '127.0.0.1', 25575, 'NME21o3#'

BBOX_S, BBOX_W = 55.614, 12.470
BBOX_N, BBOX_E = 55.630, 12.507

ORIGIN_LAT = BBOX_S
ORIGIN_LON = BBOX_W

MC_ORIGIN_X = 2000
MC_ORIGIN_Z = 2000

LAT_REF = 55.622
METERS_PER_LAT = 111320.0
METERS_PER_LON = 111320.0 * math.cos(math.radians(LAT_REF))  # ~62845

SCALE = 1.0  # 1 meter = 1 block

OSM_CACHE = '/tmp/osm_havn_1to1.json'

GROUND_Y  = -61   # grass_block level
BASE_Y    = -60   # build surface (1 above ground)
WATER_Y   = -63   # water surface (sunken)
WATER_BED = -64   # stone under water

# ── RCON ───────────────────────────────────────────────────────────────────────
def connect():
    s = socket.socket()
    s.settimeout(15)
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

def cmd(c):
    global _s, _pkt, cmd_count
    try:
        r = _pkt(2, 2, c)
        cmd_count += 1
        if cmd_count % 200 == 0:
            print(f"  [{cmd_count} cmds sent]", end='\r', flush=True)
        return r
    except Exception as e:
        time.sleep(1.0)
        try:
            _s.close()
        except Exception:
            pass
        _s, _pkt = connect()
        try:
            return _pkt(2, 2, c)
        except Exception:
            return ""

def F(x1, y1, z1, x2, y2, z2, blk, mode=""):
    """Fill region, auto-splits if > 32768 blocks."""
    if x1 > x2: x1, x2 = x2, x1
    if y1 > y2: y1, y2 = y2, y1
    if z1 > z2: z1, z2 = z2, z1
    vol = (x2 - x1 + 1) * (y2 - y1 + 1) * (z2 - z1 + 1)
    if vol > 32768:
        dx = x2 - x1 + 1
        dy = y2 - y1 + 1
        dz = z2 - z1 + 1
        if dx >= dy and dx >= dz:
            m = x1 + dx // 2 - 1
            F(x1, y1, z1, m, y2, z2, blk, mode)
            F(m + 1, y1, z1, x2, y2, z2, blk, mode)
        elif dy >= dz:
            m = y1 + dy // 2 - 1
            F(x1, y1, z1, x2, m, z2, blk, mode)
            F(x1, m + 1, z1, x2, y2, z2, blk, mode)
        else:
            m = z1 + dz // 2 - 1
            F(x1, y1, z1, x2, y2, m, blk, mode)
            F(x1, y1, m + 1, x2, y2, z2, blk, mode)
        return
    suffix = f" {mode}" if mode else ""
    cmd(f"fill {x1} {y1} {z1} {x2} {y2} {z2} {blk}{suffix}")

def S(x, y, z, blk):
    cmd(f"setblock {x} {y} {z} {blk}")

# ── COORDINATE CONVERSION ──────────────────────────────────────────────────────
def geo_to_mc(lat, lon):
    """Convert lat/lon to Minecraft X, Z (integers)."""
    dlat = lat - ORIGIN_LAT
    dlon = lon - ORIGIN_LON
    dx_m = dlon * METERS_PER_LON
    dz_m = dlat * METERS_PER_LAT
    mc_x = MC_ORIGIN_X + int(round(dx_m * SCALE))
    mc_z = MC_ORIGIN_Z - int(round(dz_m * SCALE))  # north = lower Z
    return mc_x, mc_z

MC_SW = geo_to_mc(BBOX_S, BBOX_W)
MC_NE = geo_to_mc(BBOX_N, BBOX_E)
MC_MIN_X = min(MC_SW[0], MC_NE[0])
MC_MAX_X = max(MC_SW[0], MC_NE[0])
MC_MIN_Z = min(MC_SW[1], MC_NE[1])
MC_MAX_Z = max(MC_SW[1], MC_NE[1])

print(f"MC build area: X={MC_MIN_X}..{MC_MAX_X}  Z={MC_MIN_Z}..{MC_MAX_Z}")
print(f"Area size: {MC_MAX_X - MC_MIN_X} x {MC_MAX_Z - MC_MIN_Z} blocks")
print(f"METERS_PER_LON = {METERS_PER_LON:.0f}")

# ── OSM DOWNLOAD ───────────────────────────────────────────────────────────────
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
        print(f"Using cached OSM data: {OSM_CACHE}")
        with open(OSM_CACHE, 'r', encoding='utf-8') as f:
            return json.load(f)
    print("Downloading OSM data from Overpass API...")
    url = "https://overpass-api.de/api/interpreter"
    data = urllib.parse.urlencode({'data': OVERPASS_QUERY}).encode('utf-8')
    req = urllib.request.Request(url, data=data)
    req.add_header('User-Agent', 'MinecraftOSMBuilder/1.0')
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode('utf-8')
    result = json.loads(raw)
    with open(OSM_CACHE, 'w', encoding='utf-8') as f:
        json.dump(result, f)
    print(f"Downloaded {len(result.get('elements', []))} elements, cached to {OSM_CACHE}")
    return result

import urllib.parse

# ── FORCELOAD ──────────────────────────────────────────────────────────────────
def forceload_all(load=True):
    action = "add" if load else "remove"
    step = 256
    count = 0
    for x1 in range(MC_MIN_X, MC_MAX_X + 1, step):
        x2 = min(x1 + step - 1, MC_MAX_X)
        for z1 in range(MC_MIN_Z, MC_MAX_Z + 1, step):
            z2 = min(z1 + step - 1, MC_MAX_Z)
            cmd(f"forceload {action} {x1} {z1} {x2} {z2}")
            count += 1
    print(f"  Forceload {action}: {count} regions")

# ── POLYGON HELPERS ────────────────────────────────────────────────────────────
def way_to_mc_points(way):
    """Extract MC (x, z) points from a way's geometry."""
    geom = way.get('geometry', [])
    pts = []
    for nd in geom:
        try:
            x, z = geo_to_mc(nd['lat'], nd['lon'])
            pts.append((x, z))
        except Exception:
            pass
    return pts

def scanline_fill(points, y, block):
    """Scanline-fill a polygon defined by (x, z) points at height y."""
    if len(points) < 3:
        return
    zs = [p[1] for p in points]
    min_z, max_z = min(zs), max(zs)
    n = len(points)
    for scan_z in range(min_z, max_z + 1):
        intersections = []
        for i in range(n):
            x1, z1 = points[i]
            x2, z2 = points[(i + 1) % n]
            if z1 == z2:
                continue
            if min(z1, z2) <= scan_z <= max(z1, z2):
                t = (scan_z - z1) / (z2 - z1)
                xi = x1 + t * (x2 - x1)
                intersections.append(xi)
        if len(intersections) < 2:
            continue
        intersections.sort()
        for i in range(0, len(intersections) - 1, 2):
            xi1 = int(math.floor(intersections[i]))
            xi2 = int(math.ceil(intersections[i + 1]))
            if xi1 <= xi2:
                F(xi1, y, scan_z, xi2, y, scan_z, block)

def scanline_fill_range(points, y1, y2, block):
    """Scanline-fill a polygon over a vertical range y1..y2."""
    if len(points) < 3:
        return
    zs = [p[1] for p in points]
    min_z, max_z = min(zs), max(zs)
    n = len(points)
    for scan_z in range(min_z, max_z + 1):
        intersections = []
        for i in range(n):
            px1, pz1 = points[i]
            px2, pz2 = points[(i + 1) % n]
            if pz1 == pz2:
                continue
            if min(pz1, pz2) <= scan_z <= max(pz1, pz2):
                t = (scan_z - pz1) / (pz2 - pz1)
                xi = px1 + t * (px2 - px1)
                intersections.append(xi)
        if len(intersections) < 2:
            continue
        intersections.sort()
        for i in range(0, len(intersections) - 1, 2):
            xi1 = int(math.floor(intersections[i]))
            xi2 = int(math.ceil(intersections[i + 1]))
            if xi1 <= xi2:
                F(xi1, y1, scan_z, xi2, y2, scan_z, block)

def draw_polyline(pts, y, block, width=1):
    """Draw a thick polyline at height y."""
    hw = width // 2
    for i in range(len(pts) - 1):
        x1, z1 = pts[i]
        x2, z2 = pts[i + 1]
        dx = abs(x2 - x1)
        dz = abs(z2 - z1)
        steps = max(dx, dz, 1)
        for s in range(steps + 1):
            t = s / steps
            bx = int(round(x1 + t * (x2 - x1)))
            bz = int(round(z1 + t * (z2 - z1)))
            F(bx - hw, y, bz - hw, bx + hw, y, bz + hw, block)

def bbox_of_points(pts):
    if not pts:
        return None
    xs = [p[0] for p in pts]
    zs = [p[1] for p in pts]
    return min(xs), max(xs), min(zs), max(zs)

# ── BUILDING MATERIALS ─────────────────────────────────────────────────────────
def building_material(tags):
    bt = tags.get('building', '').lower()
    bt2 = tags.get('building:use', '').lower()
    amenity = tags.get('amenity', '').lower()

    if bt in ('apartments', 'flat', 'residential') and bt not in ('house', 'detached', 'semidetached_house', 'terrace'):
        # Check if it looks like apartments
        pass

    if bt in ('apartments', 'flat'):
        return 'minecraft:light_gray_concrete'
    if bt in ('commercial', 'retail', 'office', 'supermarket'):
        return 'minecraft:smooth_stone'
    if bt in ('industrial', 'warehouse', 'factory'):
        return 'minecraft:red_concrete'
    if bt in ('school', 'hospital', 'civic', 'public'):
        return 'minecraft:yellow_concrete'
    if amenity in ('school', 'hospital', 'clinic', 'university', 'college'):
        return 'minecraft:yellow_concrete'
    if bt in ('church', 'chapel', 'cathedral', 'place_of_worship'):
        return 'minecraft:stone_bricks'
    if tags.get('amenity') in ('place_of_worship',):
        return 'minecraft:stone_bricks'
    if bt in ('garage', 'garages', 'shed', 'hut', 'carport'):
        return 'minecraft:oak_planks'
    if bt in ('house', 'detached', 'semidetached_house', 'terrace', 'bungalow', 'farm'):
        return 'minecraft:white_concrete'
    if bt in ('residential'):
        return 'minecraft:white_concrete'
    return 'minecraft:white_concrete'

def building_height(tags):
    # Explicit height
    h = tags.get('height', '')
    try:
        return max(3, int(float(h)))
    except Exception:
        pass
    # Levels
    lv = tags.get('building:levels', '')
    try:
        levels = int(float(lv))
        return max(3, levels * 3)
    except Exception:
        pass
    # Defaults by type
    bt = tags.get('building', '').lower()
    if bt in ('garage', 'garages', 'shed', 'carport', 'hut'):
        return 3
    if bt in ('apartments', 'flat'):
        return 9
    if bt in ('commercial', 'retail', 'office', 'supermarket'):
        return 8
    if bt in ('industrial', 'warehouse', 'factory'):
        return 6
    if bt in ('church', 'chapel', 'cathedral'):
        return 12
    return 6  # default residential

# ── LANDUSE MATERIAL ───────────────────────────────────────────────────────────
def landuse_material(tags):
    lu = tags.get('landuse', '').lower()
    leisure = tags.get('leisure', '').lower()
    natural = tags.get('natural', '').lower()

    if lu in ('park', 'garden', 'grass', 'recreation_ground', 'village_green'):
        return 'minecraft:grass_block'
    if leisure in ('park', 'garden', 'pitch', 'playground', 'golf_course'):
        return 'minecraft:grass_block'
    if lu in ('forest', 'wood') or natural in ('wood', 'scrub'):
        return 'FOREST'
    if lu in ('residential',):
        return 'minecraft:dirt_path'
    if lu in ('commercial', 'retail', 'industrial'):
        return 'minecraft:smooth_stone'
    if lu in ('harbour', 'port'):
        return 'minecraft:stone_bricks'
    if lu in ('farmland', 'allotments', 'orchard', 'vineyard', 'meadow'):
        return 'minecraft:farmland'
    if leisure in ('marina',):
        return 'minecraft:stone_bricks'
    return None

# ── ROAD MATERIAL & WIDTH ──────────────────────────────────────────────────────
ROAD_SPECS = {
    'motorway':      ('minecraft:gray_concrete', 8),
    'motorway_link': ('minecraft:gray_concrete', 6),
    'trunk':         ('minecraft:gray_concrete', 8),
    'trunk_link':    ('minecraft:gray_concrete', 6),
    'primary':       ('minecraft:gray_concrete', 6),
    'primary_link':  ('minecraft:gray_concrete', 5),
    'secondary':     ('minecraft:smooth_stone', 5),
    'secondary_link':('minecraft:smooth_stone', 4),
    'tertiary':      ('minecraft:smooth_stone', 4),
    'tertiary_link': ('minecraft:smooth_stone', 3),
    'residential':   ('minecraft:smooth_stone', 3),
    'unclassified':  ('minecraft:smooth_stone', 3),
    'living_street': ('minecraft:smooth_stone', 2),
    'service':       ('minecraft:smooth_stone', 2),
    'road':          ('minecraft:smooth_stone', 3),
    'footway':       ('minecraft:gravel', 1),
    'pedestrian':    ('minecraft:gravel', 2),
    'path':          ('minecraft:gravel', 1),
    'cycleway':      ('minecraft:gravel', 1),
    'track':         ('minecraft:dirt_path', 1),
    'steps':         ('minecraft:stone_bricks', 1),
}

def road_spec(tags):
    hw = tags.get('highway', '').lower()
    return ROAD_SPECS.get(hw, ('minecraft:smooth_stone', 2))

# ── MAIN BUILD ─────────────────────────────────────────────────────────────────
def main():
    # Download/load OSM
    osm = download_osm()
    elements = osm.get('elements', [])
    print(f"Loaded {len(elements)} OSM elements")

    # Separate by type
    buildings = []
    roads = []
    waters = []
    beaches = []
    landuses = []
    piers = []

    for el in elements:
        if el.get('type') != 'way':
            continue
        tags = el.get('tags', {})
        geom = el.get('geometry', [])
        if not geom:
            continue

        if tags.get('building'):
            buildings.append(el)
        elif tags.get('highway'):
            roads.append(el)
        elif tags.get('natural') in ('water', 'beach') or tags.get('waterway') or tags.get('leisure') == 'beach':
            if tags.get('natural') == 'beach' or tags.get('leisure') == 'beach':
                beaches.append(el)
            else:
                waters.append(el)
        elif tags.get('man_made') in ('pier', 'breakwater', 'jetty', 'groyne', 'seawall', 'quay'):
            piers.append(el)
        elif tags.get('landuse') or tags.get('leisure') or tags.get('natural'):
            landuses.append(el)

    print(f"Buildings: {len(buildings)}, Roads: {len(roads)}, Water: {len(waters)}, "
          f"Beach: {len(beaches)}, Landuse: {len(landuses)}, Piers: {len(piers)}")

    # ── Step 0: Forceload ────────────────────────────────────────────────────────
    print("\n[0/8] Forceloading chunks...")
    forceload_all(True)

    # ── Step 1: Clear & base ─────────────────────────────────────────────────────
    print("\n[1/8] Clearing build area (air Y=-60..80)...")
    F(MC_MIN_X, BASE_Y, MC_MIN_Z, MC_MAX_X, 80, MC_MAX_Z, 'minecraft:air')
    print("  Clear done.")

    # ── Step 2: Water bodies ─────────────────────────────────────────────────────
    print(f"\n[2/8] Building {len(waters)} water bodies...")
    for idx, el in enumerate(waters):
        try:
            tags = el.get('tags', {})
            name = tags.get('name', tags.get('waterway', tags.get('natural', '?')))
            pts = way_to_mc_points(el)
            if not pts:
                continue
            print(f"  Water {idx+1}/{len(waters)}: {name}")
            if len(pts) >= 3:
                # Fill water sunken: stone at -64, water at -63, air from -62 up
                # First fill stone under water
                scanline_fill(pts, WATER_BED, 'minecraft:stone')
                # Water layer
                scanline_fill(pts, WATER_Y, 'minecraft:water')
                # Clear Y=-62 to BASE_Y-1 with air (remove grass/dirt above)
                scanline_fill(pts, GROUND_Y, 'minecraft:air')  # -61
                scanline_fill(pts, BASE_Y, 'minecraft:air')    # -60
            else:
                # Line water
                draw_polyline(pts, WATER_Y, 'minecraft:water', width=3)
        except Exception as e:
            print(f"  ERROR water {idx}: {e}")

    # ── Step 3: Beach ────────────────────────────────────────────────────────────
    print(f"\n[3/8] Building {len(beaches)} beach areas...")
    for idx, el in enumerate(beaches):
        try:
            tags = el.get('tags', {})
            name = tags.get('name', 'beach')
            pts = way_to_mc_points(el)
            if not pts or len(pts) < 3:
                continue
            print(f"  Beach {idx+1}/{len(beaches)}: {name}")
            # Sand at ground level AND base level
            scanline_fill(pts, GROUND_Y, 'minecraft:sand')  # replace grass at -61
            scanline_fill(pts, BASE_Y, 'minecraft:sand')    # sand at -60
        except Exception as e:
            print(f"  ERROR beach {idx}: {e}")

    # ── Step 4: Landuse ──────────────────────────────────────────────────────────
    print(f"\n[4/8] Building {len(landuses)} landuse areas...")
    for idx, el in enumerate(landuses):
        try:
            tags = el.get('tags', {})
            lu = tags.get('landuse', tags.get('leisure', tags.get('natural', '?')))
            pts = way_to_mc_points(el)
            if not pts or len(pts) < 3:
                continue
            mat = landuse_material(tags)
            if mat is None:
                continue
            print(f"  Landuse {idx+1}/{len(landuses)}: {lu}")
            if mat == 'FOREST':
                # Ground coverage
                scanline_fill(pts, BASE_Y, 'minecraft:grass_block')
                # Trees every 5 blocks in bounding box
                bb = bbox_of_points(pts)
                if bb:
                    xmin, xmax, zmin, zmax = bb
                    for tx in range(xmin, xmax + 1, 5):
                        for tz in range(zmin, zmax + 1, 5):
                            # Check if inside polygon (rough: use scanline logic)
                            if point_in_poly(tx, tz, pts):
                                # Trunk Y=-60 to -57 (4 blocks)
                                F(tx, BASE_Y, tz, tx, BASE_Y + 3, tz, 'minecraft:dark_oak_log')
                                # Leaves Y=-56 to -54
                                F(tx - 1, BASE_Y + 4, tz - 1, tx + 1, BASE_Y + 6, tz + 1, 'minecraft:dark_oak_leaves[persistent=true]')
            else:
                scanline_fill(pts, BASE_Y, mat)
        except Exception as e:
            print(f"  ERROR landuse {idx}: {e}")

    # ── Step 5: Buildings ────────────────────────────────────────────────────────
    print(f"\n[5/8] Building {len(buildings)} buildings...")
    for idx, el in enumerate(buildings):
        try:
            tags = el.get('tags', {})
            name = tags.get('name', tags.get('building', '?'))
            pts = way_to_mc_points(el)
            if not pts or len(pts) < 3:
                continue
            wall = building_material(tags)
            height = building_height(tags)
            roof_y = BASE_Y + height - 1
            print(f"  Building {idx+1}/{len(buildings)}: {name} ({height}blk, {wall.split(':')[1]})")
            # Fill walls from BASE_Y to roof_y-1
            if height > 1:
                scanline_fill_range(pts, BASE_Y, roof_y - 1, wall)
            # Roof at top
            scanline_fill(pts, roof_y, 'minecraft:gray_concrete')
        except Exception as e:
            print(f"  ERROR building {idx}: {e}")

    # ── Step 6: Roads ────────────────────────────────────────────────────────────
    print(f"\n[6/8] Building {len(roads)} roads...")
    for idx, el in enumerate(roads):
        try:
            tags = el.get('tags', {})
            hw_type = tags.get('highway', '?')
            name = tags.get('name', hw_type)
            pts = way_to_mc_points(el)
            if not pts:
                continue
            mat, width = road_spec(tags)
            print(f"  Road {idx+1}/{len(roads)}: {name} ({hw_type}, w={width})")
            draw_polyline(pts, BASE_Y, mat, width=width)
        except Exception as e:
            print(f"  ERROR road {idx}: {e}")

    # ── Step 7: Piers / Breakwaters ──────────────────────────────────────────────
    print(f"\n[7/8] Building {len(piers)} piers/breakwaters...")
    for idx, el in enumerate(piers):
        try:
            tags = el.get('tags', {})
            mm = tags.get('man_made', '?')
            name = tags.get('name', mm)
            pts = way_to_mc_points(el)
            if not pts:
                continue
            print(f"  Pier {idx+1}/{len(piers)}: {name} ({mm})")
            if len(pts) >= 3:
                # Polygon pier — 2 blocks tall
                scanline_fill(pts, BASE_Y, 'minecraft:stone_bricks')
                scanline_fill(pts, BASE_Y + 1, 'minecraft:stone_bricks')
            else:
                # Polyline breakwater — 4 wide, 2 tall
                draw_polyline(pts, BASE_Y, 'minecraft:stone_bricks', width=4)
                draw_polyline(pts, BASE_Y + 1, 'minecraft:stone_bricks', width=4)
        except Exception as e:
            print(f"  ERROR pier {idx}: {e}")

    # ── Step 8: Unload & teleport ─────────────────────────────────────────────────
    print("\n[8/8] Unloading chunks and teleporting player...")
    forceload_all(False)

    # Center of build area
    cx = (MC_MIN_X + MC_MAX_X) // 2
    cz = (MC_MIN_Z + MC_MAX_Z) // 2
    cmd(f"tp HomeboyDK {cx} 100 {cz}")
    print(f"  Teleported HomeboyDK to overview: {cx}, 100, {cz}")

    print(f"\nDone! Total RCON commands sent: {cmd_count}")

# ── POINT IN POLYGON (ray casting) ────────────────────────────────────────────
def point_in_poly(px, pz, poly):
    """Returns True if (px, pz) is inside polygon."""
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, zi = poly[i]
        xj, zj = poly[j]
        if ((zi > pz) != (zj > pz)) and (px < (xj - xi) * (pz - zi) / (zj - zi) + xi):
            inside = not inside
        j = i
    return inside

if __name__ == '__main__':
    main()
