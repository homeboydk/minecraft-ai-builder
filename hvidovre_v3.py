#!/usr/bin/env python3
"""
Hvidovrehavn 1:1 scale builder v3 - Detailed with windows, sidewalks, trees.
MC origin: X=8000, Z=8000 (fresh area, away from v2)
"""

import socket, struct, time, math, json, os, urllib.request, urllib.parse

HOST, PORT, PASS = '127.0.0.1', 25575, 'NME21o3#'

BBOX_S, BBOX_W = 55.614, 12.470
BBOX_N, BBOX_E = 55.630, 12.507

ORIGIN_LAT, ORIGIN_LON = BBOX_S, BBOX_W
MC_ORIGIN_X, MC_ORIGIN_Z = 8000, 8000
LAT_REF = 55.622
METERS_PER_LAT = 111320.0
METERS_PER_LON = 111320.0 * math.cos(math.radians(LAT_REF))
SCALE = 1.0
OSM_CACHE = '/tmp/osm_havn_1to1.json'

GROUND_Y = -61
BASE_Y   = -60
WATER_Y  = -63
STRIP_W  = 128

# ── RCON ─────────────────────────────────────────────────────────────────────
def connect():
    s = socket.socket(); s.settimeout(20); s.connect((HOST, PORT))
    def pkt(rid, rt, p):
        d = p.encode('utf-8') + b'\x00\x00'
        s.send(struct.pack('<iii', len(d)+8, rid, rt) + d)
        r = b''
        while len(r) < 4 or len(r) < struct.unpack('<i', r[:4])[0]+4:
            c = s.recv(4096)
            if not c: break
            r += c
        return r[12:-2].decode('utf-8','replace')
    pkt(1, 3, PASS); return s, pkt

_s, _pkt = connect()
cmd_count = 0

def cmd(c):
    global _s, _pkt, cmd_count
    try:
        r = _pkt(2, 2, c); cmd_count += 1
        if cmd_count % 1000 == 0: print(f'  [{cmd_count}]', end='\r', flush=True)
        return r
    except:
        time.sleep(0.5)
        try: _s.close()
        except: pass
        try: _s, _pkt = connect(); return _pkt(2, 2, c)
        except: return ''

def F(x1, y1, z1, x2, y2, z2, blk, mode=''):
    if x1>x2: x1,x2=x2,x1
    if y1>y2: y1,y2=y2,y1
    if z1>z2: z1,z2=z2,z1
    vol=(x2-x1+1)*(y2-y1+1)*(z2-z1+1)
    if vol>32768:
        dx,dy,dz=x2-x1+1,y2-y1+1,z2-z1+1
        if dx>=dy and dx>=dz:
            m=x1+dx//2-1; F(x1,y1,z1,m,y2,z2,blk,mode); F(m+1,y1,z1,x2,y2,z2,blk,mode)
        elif dy>=dz:
            m=y1+dy//2-1; F(x1,y1,z1,x2,m,z2,blk,mode); F(x1,m+1,z1,x2,y2,z2,blk,mode)
        else:
            m=z1+dz//2-1; F(x1,y1,z1,x2,y2,m,blk,mode); F(x1,y1,m+1,x2,y2,z2,blk,mode)
        return
    cmd(f'fill {x1} {y1} {z1} {x2} {y2} {z2} {blk}' + (f' {mode}' if mode else ''))

def S(x,y,z,blk): cmd(f'setblock {x} {y} {z} {blk}')

def geo_to_mc(lat, lon):
    return (MC_ORIGIN_X + int(round((lon-ORIGIN_LON)*METERS_PER_LON*SCALE)),
            MC_ORIGIN_Z - int(round((lat-ORIGIN_LAT)*METERS_PER_LAT*SCALE)))

MC_SW = geo_to_mc(BBOX_S, BBOX_W)
MC_NE = geo_to_mc(BBOX_N, BBOX_E)
MC_MIN_X = min(MC_SW[0], MC_NE[0])
MC_MAX_X = max(MC_SW[0], MC_NE[0])
MC_MIN_Z = min(MC_SW[1], MC_NE[1])
MC_MAX_Z = max(MC_SW[1], MC_NE[1])
print(f'Build area: X={MC_MIN_X}..{MC_MAX_X}  Z={MC_MIN_Z}..{MC_MAX_Z}')
print(f'Size: {MC_MAX_X-MC_MIN_X} × {MC_MAX_Z-MC_MIN_Z} blocks')

# ── POLYGON HELPERS ───────────────────────────────────────────────────────────
def way_pts(way):
    return [geo_to_mc(nd['lat'], nd['lon'])
            for nd in way.get('geometry', []) if 'lat' in nd]

def poly_bbox(pts):
    if not pts: return None
    return min(p[0] for p in pts), max(p[0] for p in pts), \
           min(p[1] for p in pts), max(p[1] for p in pts)

def _scanline_xs(pts, scan_z):
    n = len(pts)
    xs = []
    for i in range(n):
        x1,z1 = pts[i]; x2,z2 = pts[(i+1)%n]
        if z1 == z2: continue
        lo,hi = (z1,z2) if z1<z2 else (z2,z1)
        if not (lo <= scan_z < hi): continue
        t = (scan_z-z1)/(z2-z1)
        xs.append(x1+t*(x2-x1))
    return sorted(xs)

def scanline_fill(pts, y, blk, zmin=None, zmax=None):
    if len(pts) < 3: return
    zs = [p[1] for p in pts]
    z0 = max(min(zs), zmin) if zmin else min(zs)
    z1 = min(max(zs), zmax) if zmax else max(zs)
    for sz in range(z0, z1+1):
        xs = _scanline_xs(pts, sz)
        for i in range(0, len(xs)-1, 2):
            xi1,xi2 = int(math.floor(xs[i])), int(math.ceil(xs[i+1]))
            if xi1 <= xi2: F(xi1, y, sz, xi2, y, sz, blk)

def scanline_fill_range(pts, y1, y2, blk, zmin=None, zmax=None):
    if len(pts) < 3: return
    zs = [p[1] for p in pts]
    z0 = max(min(zs), zmin) if zmin else min(zs)
    z1 = min(max(zs), zmax) if zmax else max(zs)
    for sz in range(z0, z1+1):
        xs = _scanline_xs(pts, sz)
        for i in range(0, len(xs)-1, 2):
            xi1,xi2 = int(math.floor(xs[i])), int(math.ceil(xs[i+1]))
            if xi1 <= xi2: F(xi1, y1, sz, xi2, y2, sz, blk)

def scanline_with_windows(pts, bld_y, height, wall, zmin, zmax):
    """Fill building: solid walls + glass pane windows on facades."""
    if len(pts) < 3: return
    zs = [p[1] for p in pts]
    z0 = max(min(zs), zmin)
    z1 = min(max(zs), zmax)
    roof_y = bld_y + height - 1

    for sz in range(z0, z1+1):
        xs = _scanline_xs(pts, sz)
        for i in range(0, len(xs)-1, 2):
            xi1 = int(math.floor(xs[i]))
            xi2 = int(math.ceil(xs[i+1]))
            if xi1 > xi2: continue
            # Floor
            F(xi1, bld_y, sz, xi2, bld_y, sz, wall)
            # Roof
            if height > 1:
                F(xi1, roof_y, sz, xi2, roof_y, sz, 'minecraft:gray_concrete')
            # Walls (between floor and roof)
            if height > 2:
                for y in range(bld_y+1, roof_y):
                    # Decide: window row or not?
                    rel_y = y - bld_y
                    is_window_row = (rel_y % 3 == 1)  # window at rel_y 1,4,7...
                    if is_window_row:
                        # Left facade: glass with pillar every 3rd block
                        if xi2 > xi1:
                            # Fill interior wall
                            if xi2 > xi1+1:
                                F(xi1+1, y, sz, xi2-1, y, sz, wall)
                            # Facades: glass or wall pillar (every 3rd X = pillar)
                            lx = xi1 % 3; rx = xi2 % 3
                            S(xi1, y, sz, wall if lx == 0 else 'minecraft:glass_pane')
                            if xi2 != xi1:
                                S(xi2, y, sz, wall if rx == 0 else 'minecraft:glass_pane')
                        else:
                            S(xi1, y, sz, wall)
                    else:
                        F(xi1, y, sz, xi2, y, sz, wall)
    # Also add windows on Z-facing facades (top/bottom of polygon bbox)
    # Walk perimeter and add windows perpendicular to Z-direction edges
    n = len(pts)
    for i in range(n):
        x1,z1_ = pts[i]; x2,z2_ = pts[(i+1)%n]
        # Only process mostly-X-aligned edges (Z doesn't change much)
        dz = abs(z2_-z1_); dx = abs(x2-x1)
        if dz > dx or dz > 2: continue
        if not (max(z0,min(z1_,z2_)) <= min(z1,max(z1_,z2_))): continue
        sz_edge = int(round((z1_+z2_)/2))
        if sz_edge < zmin or sz_edge > zmax: continue
        steps = max(dx, 1)
        for s in range(steps+1):
            t = s/steps
            bx = int(round(x1+t*(x2-x1)))
            # Check if this is an outer face (one side air, other solid)
            for y in range(bld_y+1, roof_y):
                rel_y = y - bld_y
                is_window_row = (rel_y % 3 == 1)
                if is_window_row and bx % 3 != 0:
                    S(bx, y, sz_edge, 'minecraft:glass_pane')

def draw_road(pts, y, blk, width, zmin=None, zmax=None):
    hw = max(0, width//2)
    for i in range(len(pts)-1):
        x1,z1 = pts[i]; x2,z2 = pts[i+1]
        steps = max(abs(x2-x1), abs(z2-z1), 1)
        for s in range(steps+1):
            t = s/steps
            bx = int(round(x1+t*(x2-x1)))
            bz = int(round(z1+t*(z2-z1)))
            if zmin and bz < zmin: continue
            if zmax and bz > zmax: continue
            F(bx-hw, y, bz-hw, bx+hw, y, bz+hw, blk)

def draw_road_detailed(pts, y, road_blk, width, zmin=None, zmax=None):
    """Road with sidewalks and center line."""
    hw = max(0, width//2)
    sw = 1  # sidewalk width
    for i in range(len(pts)-1):
        x1,z1 = pts[i]; x2,z2 = pts[i+1]
        steps = max(abs(x2-x1), abs(z2-z1), 1)
        for s in range(steps+1):
            t = s/steps
            bx = int(round(x1+t*(x2-x1)))
            bz = int(round(z1+t*(z2-z1)))
            if zmin and bz < zmin-2: continue
            if zmax and bz > zmax+2: continue
            # Sidewalk (stone)
            if width >= 3:
                F(bx-hw-sw, y, bz-sw, bx-hw-1, y, bz+sw, 'minecraft:stone')
                F(bx+hw+1, y, bz-sw, bx+hw+sw, y, bz+sw, 'minecraft:stone')
            # Road surface
            F(bx-hw, y, bz-hw, bx+hw, y, bz+hw, road_blk)
            # Center line (dashed, only on wide roads)
            if width >= 6 and s % 8 < 4:
                S(bx, y, bz, 'minecraft:white_concrete')

def place_tree(x, y, z):
    """Oak tree: 4-block trunk + leaves crown."""
    for dy in range(4):
        S(x, y+dy, z, 'minecraft:oak_log')
    for dx in range(-2,3):
        for dz in range(-2,3):
            for dy in range(3,6):
                if abs(dx)+abs(dz)+abs(dy-4) <= 4:
                    cmd(f'setblock {x+dx} {y+dy} {z+dz} minecraft:oak_leaves[persistent=true] keep')

def draw_road_with_trees(pts, y, road_blk, width, zmin=None, zmax=None):
    draw_road_detailed(pts, y, road_blk, width, zmin, zmax)
    # Add trees every 14 blocks
    tree_interval = 14
    for i in range(len(pts)-1):
        x1,z1 = pts[i]; x2,z2 = pts[i+1]
        steps = max(abs(x2-x1), abs(z2-z1), 1)
        hw = max(0, width//2)
        for s in range(0, steps+1, tree_interval):
            t = s/steps
            bx = int(round(x1+t*(x2-x1)))
            bz = int(round(z1+t*(z2-z1)))
            if zmin and bz < zmin: continue
            if zmax and bz > zmax: continue
            # dx/dz = road direction; perp = sidewalk direction
            dx = x2-x1; dz_ = z2-z1
            ln = math.sqrt(dx*dx+dz_*dz_)+0.001
            px = int(round(-dz_/ln*(hw+2)))  # perpendicular offset
            pz = int(round(dx/ln*(hw+2)))
            place_tree(bx+px, y, bz+pz)

# ── FORCELOAD ─────────────────────────────────────────────────────────────────
def forceload_strip(z0, z1, load=True):
    act = 'add' if load else 'remove'
    for xa in range(MC_MIN_X, MC_MAX_X+1, 256):
        xb = min(xa+255, MC_MAX_X)
        cmd(f'forceload {act} {xa} {z0} {xb} {z1}')
    if load: time.sleep(0.2)

# ── MATERIALS ─────────────────────────────────────────────────────────────────
def bld_mat(tags):
    bt = tags.get('building','').lower()
    amenity = tags.get('amenity','').lower()
    if bt in ('apartments','flat'): return 'minecraft:light_gray_concrete'
    if bt in ('commercial','retail','office','supermarket'): return 'minecraft:smooth_stone'
    if bt in ('industrial','warehouse','factory'): return 'minecraft:red_concrete'
    if bt in ('school','hospital','civic','public') or amenity in ('school','hospital','university'): return 'minecraft:yellow_concrete'
    if bt in ('church','chapel','cathedral','place_of_worship'): return 'minecraft:stone_bricks'
    if bt in ('garage','garages','shed','hut','carport'): return 'minecraft:oak_planks'
    return 'minecraft:white_concrete'

def bld_height(tags):
    try: return max(3, int(float(tags['height'])))
    except: pass
    try: return max(3, int(float(tags['building:levels']))*3)
    except: pass
    bt = tags.get('building','').lower()
    if bt in ('garage','shed','carport','hut'): return 3
    if bt in ('apartments','flat'): return 12
    if bt in ('commercial','retail','office'): return 9
    if bt in ('industrial','warehouse'): return 6
    return 6

ROAD_SPECS = {
    'motorway':      ('minecraft:black_concrete', 8),
    'trunk':         ('minecraft:black_concrete', 7),
    'primary':       ('minecraft:black_concrete', 6),
    'secondary':     ('minecraft:black_concrete', 5),
    'tertiary':      ('minecraft:gray_concrete',  4),
    'residential':   ('minecraft:gray_concrete',  4),
    'unclassified':  ('minecraft:gray_concrete',  3),
    'living_street': ('minecraft:gray_concrete',  3),
    'service':       ('minecraft:gray_concrete',  3),
    'road':          ('minecraft:gray_concrete',  4),
    'footway':       ('minecraft:gravel',          2),
    'pedestrian':    ('minecraft:gravel',          3),
    'path':          ('minecraft:gravel',          2),
    'cycleway':      ('minecraft:gravel',          2),
    'track':         ('minecraft:dirt_path',       2),
    'steps':         ('minecraft:stone_bricks',    2),
}
def road_spec(tags): return ROAD_SPECS.get(tags.get('highway','').lower(), ('minecraft:gray_concrete',3))

def landuse_mat(tags):
    lu = tags.get('landuse','').lower()
    lei = tags.get('leisure','').lower()
    nat = tags.get('natural','').lower()
    if lu in ('park','garden','grass','recreation_ground') or lei in ('park','garden','pitch','playground'): return 'minecraft:moss_block'
    if lu in ('forest','wood') or nat in ('wood','scrub'): return 'FOREST'
    if lu == 'residential': return 'minecraft:dirt_path'
    if lu in ('commercial','retail','industrial'): return 'minecraft:smooth_stone'
    if lu in ('harbour','port') or lei == 'marina': return 'minecraft:stone_bricks'
    if lu in ('farmland','allotments','meadow'): return 'minecraft:farmland'
    return None

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    with open(OSM_CACHE) as f: osm = json.load(f)
    elements = osm.get('elements', [])
    buildings, roads, waters, beaches, landuses, piers = [], [], [], [], [], []
    for el in elements:
        if el.get('type') != 'way' or not el.get('geometry'): continue
        tags = el.get('tags', {})
        if tags.get('building'): buildings.append(el)
        elif tags.get('highway'): roads.append(el)
        elif tags.get('natural') == 'beach' or tags.get('leisure') == 'beach': beaches.append(el)
        elif tags.get('natural') in ('water',) or tags.get('waterway'): waters.append(el)
        elif tags.get('man_made') in ('pier','breakwater','jetty','groyne','seawall','quay'): piers.append(el)
        elif tags.get('landuse') or tags.get('leisure') or tags.get('natural'): landuses.append(el)

    print(f'Buildings:{len(buildings)} Roads:{len(roads)} Water:{len(waters)} Beach:{len(beaches)} Piers:{len(piers)}')

    # Verify marker
    cmd(f'forceload add {MC_MIN_X} {MC_MIN_Z} {MC_MIN_X+32} {MC_MIN_Z+32}')
    time.sleep(0.3)
    for i in range(8): S(MC_MIN_X, BASE_Y+i, MC_MIN_Z, 'minecraft:red_concrete')
    r = cmd(f'execute if block {MC_MIN_X} {BASE_Y} {MC_MIN_Z} minecraft:red_concrete')
    print(f'Verify: {r}')

    total_strips = math.ceil((MC_MAX_Z - MC_MIN_Z + 1) / STRIP_W)
    print(f'\nBuilding {total_strips} strips...')

    for strip_num, strip_z0 in enumerate(range(MC_MIN_Z, MC_MAX_Z+1, STRIP_W), 1):
        strip_z1 = min(strip_z0 + STRIP_W - 1, MC_MAX_Z)
        print(f'\nStrip {strip_num}/{total_strips}: Z={strip_z0}..{strip_z1}')

        forceload_strip(strip_z0, strip_z1, True)

        # Clear
        F(MC_MIN_X, BASE_Y, strip_z0, MC_MAX_X, 80, strip_z1, 'minecraft:air')

        # 1) Water bodies
        for el in waters:
            pts = way_pts(el)
            if not pts: continue
            bb = poly_bbox(pts)
            if not bb or bb[3] < strip_z0 or bb[2] > strip_z1: continue
            if len(pts) >= 3:
                scanline_fill(pts, -65, 'minecraft:stone', strip_z0, strip_z1)
                scanline_fill(pts, -64, 'minecraft:stone', strip_z0, strip_z1)
                scanline_fill(pts, WATER_Y, 'minecraft:water', strip_z0, strip_z1)
                scanline_fill(pts, GROUND_Y, 'minecraft:air', strip_z0, strip_z1)
                scanline_fill(pts, BASE_Y, 'minecraft:air', strip_z0, strip_z1)
            else:
                draw_road(pts, WATER_Y, 'minecraft:water', 4, strip_z0, strip_z1)

        # 2) Landuse (before beach so beach overwrites parks)
        for el in landuses:
            pts = way_pts(el)
            if not pts or len(pts) < 3: continue
            bb = poly_bbox(pts)
            if not bb or bb[3] < strip_z0 or bb[2] > strip_z1: continue
            mat = landuse_mat(el.get('tags', {}))
            if mat is None: continue
            if mat == 'FOREST':
                scanline_fill(pts, BASE_Y, 'minecraft:moss_block', strip_z0, strip_z1)
                # Trees every 8 blocks
                bb2 = poly_bbox(pts)
                if bb2:
                    for tx in range(bb2[0], bb2[1]+1, 8):
                        for tz in range(max(bb2[2], strip_z0), min(bb2[3], strip_z1)+1, 8):
                            if _point_in_poly(tx, tz, pts):
                                place_tree(tx, BASE_Y, tz)
            else:
                scanline_fill(pts, BASE_Y, mat, strip_z0, strip_z1)

        # 3) Beach (overwrites landuse)
        for el in beaches:
            pts = way_pts(el)
            if not pts or len(pts) < 3: continue
            bb = poly_bbox(pts)
            if not bb or bb[3] < strip_z0 or bb[2] > strip_z1: continue
            scanline_fill(pts, GROUND_Y, 'minecraft:sand', strip_z0, strip_z1)
            scanline_fill(pts, BASE_Y, 'minecraft:sand', strip_z0, strip_z1)

        # 4) Buildings with windows
        for el in buildings:
            pts = way_pts(el)
            if not pts or len(pts) < 3: continue
            bb = poly_bbox(pts)
            if not bb or bb[3] < strip_z0 or bb[2] > strip_z1: continue
            tags = el.get('tags', {})
            wall = bld_mat(tags)
            height = bld_height(tags)
            scanline_with_windows(pts, BASE_Y, height, wall, strip_z0, strip_z1)

        # 5) Piers / breakwaters
        for el in piers:
            pts = way_pts(el)
            if not pts: continue
            zvals = [p[1] for p in pts]
            if min(zvals) > strip_z1 or max(zvals) < strip_z0: continue
            mm = el.get('tags', {}).get('man_made', '')
            if len(pts) >= 3:
                bb = poly_bbox(pts)
                if bb and not (bb[3] < strip_z0 or bb[2] > strip_z1):
                    for dy in range(3):
                        scanline_fill(pts, BASE_Y+dy, 'minecraft:stone_bricks', strip_z0, strip_z1)
            else:
                for dy in range(3):
                    draw_road(pts, BASE_Y+dy, 'minecraft:stone_bricks', 5, strip_z0, strip_z1)

        # 6) Roads (last, on top)
        for el in roads:
            pts = way_pts(el)
            if not pts: continue
            zvals = [p[1] for p in pts]
            if min(zvals) > strip_z1+4 or max(zvals) < strip_z0-4: continue
            tags = el.get('tags', {})
            mat, width = road_spec(tags)
            hw_type = tags.get('highway','')
            # Street trees on residential roads
            if hw_type in ('residential', 'living_street'):
                draw_road_with_trees(pts, BASE_Y, mat, width, strip_z0, strip_z1)
            else:
                draw_road_detailed(pts, BASE_Y, mat, width, strip_z0, strip_z1)

        forceload_strip(strip_z0, strip_z1, False)
        print(f'  done [{cmd_count} total]')

    # Teleport to harbor
    cmd(f'forceload add {MC_MIN_X} {MC_MIN_Z} {MC_MAX_X} {MC_MAX_Z}')
    # Harbor center in new coordinates
    harbor_x = MC_ORIGIN_X + int(round((12.477 - ORIGIN_LON) * METERS_PER_LON))
    harbor_z = MC_ORIGIN_Z - int(round((55.617 - ORIGIN_LAT) * METERS_PER_LAT))
    print(f'\nHarbor center: X={harbor_x}, Z={harbor_z}')
    cmd(f'tp HomeboyDK {harbor_x} -30 {harbor_z}')
    print(f'Teleported to harbor overview (Y=-30)')

    cx = (MC_MIN_X+MC_MAX_X)//2
    cz = (MC_MIN_Z+MC_MAX_Z)//2
    print(f'\nDone! {cmd_count} RCON commands.')
    print(f'Overview: /tp {cx} 60 {cz}')
    print(f'Harbor:   /tp {harbor_x} -30 {harbor_z}')
    print(f'Beach:    /tp {MC_ORIGIN_X+int(round((12.494-ORIGIN_LON)*METERS_PER_LON))} -40 {MC_ORIGIN_Z-int(round((55.615-ORIGIN_LAT)*METERS_PER_LAT))}')

def _point_in_poly(px, pz, poly):
    n = len(poly); inside = False; j = n-1
    for i in range(n):
        xi,zi = poly[i]; xj,zj = poly[j]
        if ((zi>pz) != (zj>pz)) and (px < (xj-xi)*(pz-zi)/(zj-zi)+xi): inside = not inside
        j = i
    return inside

if __name__ == '__main__': main()
