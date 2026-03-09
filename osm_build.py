#!/usr/bin/env python3
"""
OSM → Minecraft builder for Hvidovre/Åmarken area, Denmark.
Bounding box: S=55.605, W=12.458, N=55.645, E=12.558
Scale 1:10 (1m = 0.1 blocks), origin SW → MC X=500, Z=500
"""

import socket, struct, time, math, json, os, urllib.request

# ── CONFIG ────────────────────────────────────────────────────────────────────
HOST, PORT, PASS = '127.0.0.1', 25575, 'NME21o3#'

BBOX_S, BBOX_W = 55.605, 12.458
BBOX_N, BBOX_E = 55.645, 12.558

ORIGIN_LAT = BBOX_S   # SW corner
ORIGIN_LON = BBOX_W

MC_ORIGIN_X = 500
MC_ORIGIN_Z = 500

# Meters per degree at lat ~55.625°N
LAT_REF      = 55.625
METERS_PER_LAT = 111320.0
METERS_PER_LON = 111320.0 * math.cos(math.radians(LAT_REF))  # ~62800

SCALE = 0.1   # meters → blocks (1m = 0.1 blocks)

OSM_CACHE = '/tmp/osm_hvidovre.json'

# ── RCON ──────────────────────────────────────────────────────────────────────
def connect():
    s = socket.socket(); s.settimeout(10); s.connect((HOST, PORT))
    def pkt(rid, rt, p):
        d = p.encode('utf-8') + b'\x00\x00'
        s.send(struct.pack('<iii', len(d)+8, rid, rt) + d)
        r = b''
        while len(r) < 4 or len(r) < struct.unpack('<i', r[:4])[0]+4:
            r += s.recv(4096)
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
        if cmd_count % 100 == 0:
            print(f"  [{cmd_count} cmds]", end='\r', flush=True)
        return r
    except Exception:
        time.sleep(0.5)
        try: _s.close()
        except: pass
        _s, _pkt = connect()
        return _pkt(2, 2, c)

def F(x1, y1, z1, x2, y2, z2, blk, mode=""):
    """fill, auto-splits if > 32768 blocks"""
    if x1 > x2: x1, x2 = x2, x1
    if y1 > y2: y1, y2 = y2, y1
    if z1 > z2: z1, z2 = z2, z1
    vol = (x2-x1+1)*(y2-y1+1)*(z2-z1+1)
    if vol > 32768:
        dx, dy, dz = x2-x1+1, y2-y1+1, z2-z1+1
        if dx >= dy and dx >= dz:
            m = x1 + dx//2 - 1
            F(x1,y1,z1, m,y2,z2, blk, mode); F(m+1,y1,z1, x2,y2,z2, blk, mode)
        elif dy >= dz:
            m = y1 + dy//2 - 1
            F(x1,y1,z1, x2,m,z2, blk, mode); F(x1,m+1,z1, x2,y2,z2, blk, mode)
        else:
            m = z1 + dz//2 - 1
            F(x1,y1,z1, x2,y2,m, blk, mode); F(x1,y1,m+1, x2,y2,z2, blk, mode)
        return
    suffix = f" {mode}" if mode else ""
    cmd(f"fill {x1} {y1} {z1} {x2} {y2} {z2} {blk}{suffix}")

def S(x, y, z, blk):
    cmd(f"setblock {x} {y} {z} {blk}")

# ── COORDINATE CONVERSION ─────────────────────────────────────────────────────
def geo_to_mc(lat, lon):
    """Convert lat/lon to Minecraft X, Z (integers)."""
    dlat = lat - ORIGIN_LAT   # positive = north
    dlon = lon - ORIGIN_LON   # positive = east
    dx_m = dlon * METERS_PER_LON
    dz_m = dlat * METERS_PER_LAT
    mc_x = MC_ORIGIN_X + int(round(dx_m * SCALE))
    mc_z = MC_ORIGIN_Z - int(round(dz_m * SCALE))   # north = lower Z
    return mc_x, mc_z

# Pre-compute MC bounding box corners
MC_SW = geo_to_mc(BBOX_S, BBOX_W)
MC_NE = geo_to_mc(BBOX_N, BBOX_E)
MC_MIN_X = min(MC_SW[0], MC_NE[0])
MC_MAX_X = max(MC_SW[0], MC_NE[0])
MC_MIN_Z = min(MC_SW[1], MC_NE[1])
MC_MAX_Z = max(MC_SW[1], MC_NE[1])

print(f"MC build area: X={MC_MIN_X}..{MC_MAX_X}, Z={MC_MIN_Z}..{MC_MAX_Z}")

# ── OSM DOWNLOAD ──────────────────────────────────────────────────────────────
def download_osm():
    # Merge three pre-downloaded files into a single element list
    files = ['/tmp/osm_buildings.json', '/tmp/osm_roads.json', '/tmp/osm_other.json']
    elements = []
    for fn in files:
        with open(fn, 'r', encoding='utf-8') as f:
            d = json.load(f)
        elements.extend(d.get('elements', []))
        print(f"  {fn}: {len(d.get('elements',[]))} elements")
    print(f"Total: {len(elements)} elements")
    return {'elements': elements}
    return json.loads(raw)

# ── POLYGON HELPERS ───────────────────────────────────────────────────────────
def way_to_mc_points(way):
    """Extract MC (x,z) points from a way's geometry."""
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
    """
    Scanline fill a polygon defined by (x,z) points.
    For each z row, find x extents and call F().
    """
    if len(points) < 3:
        return
    xs = [p[0] for p in points]
    zs = [p[1] for p in points]
    min_z, max_z = min(zs), max(zs)
    n = len(points)

    for scan_z in range(min_z, max_z + 1):
        intersections = []
        for i in range(n):
            x1, z1 = points[i]
            x2, z2 = points[(i+1) % n]
            if z1 == z2:
                continue
            if min(z1, z2) <= scan_z <= max(z1, z2):
                # x at this scan_z
                t = (scan_z - z1) / (z2 - z1)
                xi = x1 + t * (x2 - x1)
                intersections.append(xi)
        if len(intersections) < 2:
            continue
        intersections.sort()
        # pair up intersections
        for i in range(0, len(intersections)-1, 2):
            xi1 = int(math.floor(intersections[i]))
            xi2 = int(math.ceil(intersections[i+1]))
            if xi1 <= xi2:
                F(xi1, y, scan_z, xi2, y, scan_z, block)

def draw_line(pts, y, block, width=1):
    """Draw a polyline of width w at height y."""
    for i in range(len(pts)-1):
        x1, z1 = pts[i]
        x2, z2 = pts[i+1]
        # Bresenham-ish: iterate along major axis
        dx = abs(x2 - x1)
        dz = abs(z2 - z1)
        steps = max(dx, dz, 1)
        for s in range(steps + 1):
            t = s / steps
            bx = int(round(x1 + t*(x2-x1)))
            bz = int(round(z1 + t*(z2-z1)))
            hw = width // 2
            F(bx - hw, y, bz - hw, bx + hw, y, bz + hw, block)

# ── PARSE OSM ─────────────────────────────────────────────────────────────────
def parse_osm(data):
    buildings = []
    roads     = []
    waters    = []
    landuses  = []
    railways  = []

    for el in data.get('elements', []):
        try:
            tags = el.get('tags', {})
            etype = el.get('type', '')

            if etype == 'way':
                pts = way_to_mc_points(el)
                if not pts:
                    continue

                if 'building' in tags:
                    buildings.append({'pts': pts, 'tags': tags})
                elif 'highway' in tags:
                    roads.append({'pts': pts, 'tags': tags})
                elif tags.get('natural') == 'water' or 'waterway' in tags:
                    waters.append({'pts': pts, 'tags': tags})
                elif 'landuse' in tags:
                    landuses.append({'pts': pts, 'tags': tags})
                elif 'railway' in tags:
                    railways.append({'pts': pts, 'tags': tags})

            elif etype == 'relation':
                # Handle multipolygon relations - use outer members
                members = el.get('members', [])
                for m in members:
                    if m.get('role') == 'outer' and m.get('type') == 'way':
                        geom = m.get('geometry', [])
                        pts = []
                        for nd in geom:
                            try:
                                x, z = geo_to_mc(nd['lat'], nd['lon'])
                                pts.append((x, z))
                            except Exception:
                                pass
                        if pts:
                            if tags.get('natural') == 'water' or 'waterway' in tags:
                                waters.append({'pts': pts, 'tags': tags})
                            elif 'landuse' in tags:
                                landuses.append({'pts': pts, 'tags': tags})

        except Exception as e:
            pass  # skip malformed elements

    print(f"Parsed: {len(buildings)} buildings, {len(roads)} roads, "
          f"{len(waters)} water bodies, {len(landuses)} landuse areas, "
          f"{len(railways)} railways")
    return buildings, roads, waters, landuses, railways

# ── CHUNK FORCELOAD ───────────────────────────────────────────────────────────

def forceload_area(load=True):
    """Forceload (or unload) the entire build area in 16×16 chunk batches."""
    action = "add" if load else "remove"
    verb = "Loading" if load else "Unloading"
    step = 256  # 256 blocks = 16 chunks per axis, 16×16 = 256 chunks (max)
    batches = 0
    for x1 in range(MC_MIN_X, MC_MAX_X, step):
        x2 = min(x1 + step - 1, MC_MAX_X)
        for z1 in range(MC_MIN_Z, MC_MAX_Z, step):
            z2 = min(z1 + step - 1, MC_MAX_Z)
            cmd(f"forceload {action} {x1} {z1} {x2} {z2}")
            batches += 1
    print(f"  {verb} done ({batches} batches)")

# ── BUILD STEPS ───────────────────────────────────────────────────────────────

def step_clear():
    print("\n=== STEP 1: Clearing build area ===")
    # Clear air from Y=65 to Y=100
    print("  Clearing Y=-60..100 to air...")
    F(MC_MIN_X, -60, MC_MIN_Z, MC_MAX_X, 100, MC_MAX_Z, "minecraft:air")
    # Flat ground at Y=64 with grass
    print("  Placing grass ground at Y=64...")
    F(MC_MIN_X, -61, MC_MIN_Z, MC_MAX_X, -61, MC_MAX_Z, "minecraft:grass_block")
    # Stone base below Y=64
    print("  Placing stone base Y=60..63...")
    F(MC_MIN_X, -65, MC_MIN_Z, MC_MAX_X, -62, MC_MAX_Z, "minecraft:stone")
    print("  Clear done.")


def step_water(waters):
    print(f"\n=== STEP 2: Water ({len(waters)} bodies) ===")
    for i, w in enumerate(waters):
        try:
            pts = w['pts']
            name = w['tags'].get('name', w['tags'].get('waterway', 'water'))
            print(f"  Water {i+1}/{len(waters)}: {name}")
            # Stone base at Y=60..63
            # Water 2 below ground: stone base then water
            scanline_fill(pts, -64, "minecraft:stone")
            scanline_fill(pts, -63, "minecraft:water")
        except Exception as e:
            print(f"    ERROR: {e}")


def step_landuse(landuses):
    print(f"\n=== STEP 3: Landuse ({len(landuses)} areas) ===")
    LANDUSE_MAP = {
        'park':            'minecraft:grass_block',
        'grass':           'minecraft:grass_block',
        'recreation_ground': 'minecraft:grass_block',
        'village_green':   'minecraft:grass_block',
        'meadow':          'minecraft:grass_block',
        'forest':          'minecraft:grass_block',   # base, trees added separately
        'wood':            'minecraft:grass_block',
        'residential':     'minecraft:smooth_stone',
        'farmland':        'minecraft:farmland',
        'allotments':      'minecraft:farmland',
        'commercial':      'minecraft:smooth_stone',
        'retail':          'minecraft:smooth_stone',
        'industrial':      'minecraft:gravel',
        'railway':         'minecraft:gravel',
        'cemetery':        'minecraft:grass_block',
        'construction':    'minecraft:dirt',
    }

    for i, lu in enumerate(landuses):
        try:
            pts = lu['pts']
            ltype = lu['tags'].get('landuse', '')
            name = lu['tags'].get('name', ltype)
            blk = LANDUSE_MAP.get(ltype, 'minecraft:dirt')
            print(f"  Landuse {i+1}/{len(landuses)}: {ltype} '{name}'")
            scanline_fill(pts, -60, blk)

            # Add trees for forest
            if ltype in ('forest', 'wood'):
                # Place leaf canopy at Y=69-71 and logs Y=65-68 every 5 blocks
                xs = [p[0] for p in pts]
                zs = [p[1] for p in pts]
                min_x, max_x = min(xs), max(xs)
                min_z, max_z = min(zs), max(zs)
                for tx in range(min_x + 2, max_x - 1, 5):
                    for tz in range(min_z + 2, max_z - 1, 5):
                        # Check if point inside polygon (simple bounding check)
                        try:
                            # Log
                            F(tx, -60, tz, tx, -57, tz, "minecraft:dark_oak_log")
                            # Leaves canopy
                            F(tx-2, -55, tz-2, tx+2, -53, tz+2, "minecraft:dark_oak_leaves[persistent=true]")
                        except Exception:
                            pass
        except Exception as e:
            print(f"    ERROR: {e}")


def step_buildings(buildings):
    print(f"\n=== STEP 4: Buildings ({len(buildings)}) ===")

    for i, b in enumerate(buildings):
        try:
            pts = b['pts']
            tags = b['tags']
            btype = tags.get('building', 'yes')
            name  = tags.get('name', btype)
            print(f"  Building {i+1}/{len(buildings)}: {btype} '{name}'")

            # Determine height
            try:
                levels = int(tags.get('building:levels', 0))
            except (ValueError, TypeError):
                levels = 0

            if btype in ('apartments', 'residential') and levels == 0:
                levels = 3
            if levels == 0:
                levels = 2

            height = levels * 4  # 4 blocks per floor
            height = max(3, min(height, 20))  # clamp

            if btype in ('shed', 'garage', 'hut', 'roof'):
                height = 3
            elif btype == 'industrial':
                height = 5
            elif btype in ('apartments',) or levels >= 3:
                height = max(height, 12)

            # Material
            if btype in ('industrial', 'warehouse', 'factory'):
                wall_blk = "minecraft:red_concrete"
            elif btype in ('commercial', 'retail', 'office', 'supermarket',
                           'civic', 'public', 'school', 'hospital', 'church'):
                wall_blk = "minecraft:smooth_stone"
            else:
                wall_blk = "minecraft:white_concrete"

            roof_blk = "minecraft:gray_concrete"

            y_base = -60
            y_top  = y_base + height - 1

            # Fill building volume
            scanline_fill(pts, y_base, wall_blk)
            for y in range(y_base + 1, y_top):
                scanline_fill(pts, y, wall_blk)
            # Roof
            scanline_fill(pts, y_top, roof_blk)

        except Exception as e:
            print(f"    ERROR: {e}")


def step_roads(roads):
    print(f"\n=== STEP 5: Roads ({len(roads)}) ===")

    ROAD_STYLES = {
        'motorway':        ('minecraft:gray_concrete',       3),
        'motorway_link':   ('minecraft:gray_concrete',       2),
        'trunk':           ('minecraft:gray_concrete',       3),
        'trunk_link':      ('minecraft:gray_concrete',       2),
        'primary':         ('minecraft:gray_concrete',       3),
        'primary_link':    ('minecraft:gray_concrete',       2),
        'secondary':       ('minecraft:smooth_stone',        2),
        'secondary_link':  ('minecraft:smooth_stone',        2),
        'tertiary':        ('minecraft:smooth_stone',        2),
        'tertiary_link':   ('minecraft:smooth_stone',        1),
        'residential':     ('minecraft:smooth_stone_slab',   1),
        'unclassified':    ('minecraft:smooth_stone_slab',   1),
        'living_street':   ('minecraft:smooth_stone_slab',   1),
        'service':         ('minecraft:smooth_stone_slab',   1),
        'footway':         ('minecraft:gravel',              1),
        'path':            ('minecraft:gravel',              1),
        'cycleway':        ('minecraft:gravel',              1),
        'pedestrian':      ('minecraft:gravel',              1),
        'track':           ('minecraft:dirt_path',           1),
        'steps':           ('minecraft:gravel',              1),
    }

    for i, r in enumerate(roads):
        try:
            pts = r['pts']
            tags = r['tags']
            htype = tags.get('highway', 'unclassified')
            name  = tags.get('name', htype)
            print(f"  Road {i+1}/{len(roads)}: {htype} '{name}'")

            blk, width = ROAD_STYLES.get(htype, ('minecraft:smooth_stone_slab', 1))
            draw_line(pts, -60, blk, width)

        except Exception as e:
            print(f"    ERROR: {e}")


def step_railways(railways):
    print(f"\n=== STEP 6: Railways ({len(railways)}) ===")
    for i, r in enumerate(railways):
        try:
            pts = r['pts']
            tags = r['tags']
            rtype = tags.get('railway', 'rail')
            name  = tags.get('name', rtype)
            print(f"  Railway {i+1}/{len(railways)}: {rtype} '{name}'")
            # Stone base
            draw_line(pts, -60, "minecraft:stone", width=1)
            # Rails on top
            draw_line(pts, -59, "minecraft:rail", width=1)
        except Exception as e:
            print(f"    ERROR: {e}")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print("=== OSM → Minecraft Builder: Hvidovre/Åmarken ===")
    print(f"Coordinate range: lat {BBOX_S}..{BBOX_N}, lon {BBOX_W}..{BBOX_E}")
    print(f"MC origin: X={MC_ORIGIN_X}, Z={MC_ORIGIN_Z} = SW corner ({BBOX_S}°N, {BBOX_W}°E)")
    print(f"METERS_PER_LON at {LAT_REF}°N = {METERS_PER_LON:.1f}")

    # Download / load OSM
    data = download_osm()

    # Parse
    buildings, roads, waters, landuses, railways = parse_osm(data)

    # Forceload all chunks so fill commands actually work
    print("\n=== Forceloading all chunks in build area ===")
    forceload_area(load=True)

    # Build
    step_clear()
    step_water(waters)
    step_landuse(landuses)
    step_buildings(buildings)
    step_roads(roads)
    step_railways(railways)

    # Unload chunks
    print("\n=== Unloading forceloaded chunks ===")
    forceload_area(load=False)

    # Teleport to overview
    cx = (MC_MIN_X + MC_MAX_X) // 2
    cz = (MC_MIN_Z + MC_MAX_Z) // 2
    print(f"\n=== Teleporting HomeboyDK to overview ({cx}, -30, {cz}) ===")
    cmd(f"tp HomeboyDK {cx} -30 {cz}")
    cmd(f"gamemode creative HomeboyDK")
    cmd(f"say OSM build complete! {cmd_count} commands sent.")

    print(f"\nDone! Total commands: {cmd_count}")

if __name__ == '__main__':
    main()
