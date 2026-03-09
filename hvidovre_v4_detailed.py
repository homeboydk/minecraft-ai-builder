#!/usr/bin/env python3
"""
Hvidovrehavn v4 — Super detaljeret natbyg:
- Hav og havnebassiner med vand
- Haver, træer, parkering, fortove
- Kystlinje og strand med bølgebrydere
- Mere variation i byggematerialer
- Yderligere OSM lag: træer, naturlige elementer, amenities

MC origin: X=11000, Z=11000 (frisk område, ingen overlap)
Bbox: 55.614,12.470,55.630,12.507
"""

import socket, struct, time, math, json, os, urllib.request, urllib.parse, sys

HOST, PORT, PASS = '127.0.0.1', 25575, 'NME21o3#'

BBOX_S, BBOX_W = 55.614, 12.470
BBOX_N, BBOX_E = 55.630, 12.507

ORIGIN_LAT, ORIGIN_LON = BBOX_S, BBOX_W
MC_ORIGIN_X, MC_ORIGIN_Z = 11000, 11000

LAT_REF      = 55.622
METERS_PER_LAT = 111320.0
METERS_PER_LON = 111320.0 * math.cos(math.radians(LAT_REF))  # ~62857

GROUND_Y = -61
BASE_Y   = -60
SEA_Y    = -63    # vandoverflade
SEA_BED  = -66    # bund under vand

STRIP_W = 128

CHECKPOINT = 'checkpoint_v4.json'

# ── RCON ─────────────────────────────────────────────────────────────────────
def connect():
    s = socket.socket(); s.settimeout(20); s.connect((HOST, PORT))
    def pkt(rid, rt, p):
        d = p.encode('utf-8') + b'\x00\x00'
        s.send(struct.pack('<iii', len(d)+8, rid, rt) + d)
        r = b''
        while len(r)<4 or len(r)<struct.unpack('<i',r[:4])[0]+4:
            c=s.recv(4096)
            if not c: break
            r+=c
        return r[12:-2].decode('utf-8','replace')
    pkt(1,3,PASS); return s, pkt

_s, _pkt = connect()
_cnt = [0]

def cmd(c):
    global _s, _pkt
    try:
        r=_pkt(2,2,c); _cnt[0]+=1
        if _cnt[0]%1000==0: print(f'  [{_cnt[0]}]',end='\r',flush=True)
        return r
    except:
        time.sleep(0.5)
        try: _s.close()
        except: pass
        try: _s,_pkt=connect(); return _pkt(2,2,c)
        except: return ''

def F(x1,y1,z1,x2,y2,z2,blk,mode=''):
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

# ── Koordinater ───────────────────────────────────────────────────────────────
def geo_to_mc(lat, lon):
    return (MC_ORIGIN_X + int(round((lon-ORIGIN_LON)*METERS_PER_LON)),
            MC_ORIGIN_Z - int(round((lat-ORIGIN_LAT)*METERS_PER_LAT)))

MC_SW = geo_to_mc(BBOX_S, BBOX_W)
MC_NE = geo_to_mc(BBOX_N, BBOX_E)
MC_MIN_X = min(MC_SW[0], MC_NE[0]); MC_MAX_X = max(MC_SW[0], MC_NE[0])
MC_MIN_Z = min(MC_SW[1], MC_NE[1]); MC_MAX_Z = max(MC_SW[1], MC_NE[1])
print(f'Byg-område: X={MC_MIN_X}..{MC_MAX_X}  Z={MC_MIN_Z}..{MC_MAX_Z}')

# Kystlinje: vest for ~lon=12.4735 er hav (Kalveboderne / Øresund)
# I MC-koordinater: X < 11164 er hav (lon 12.4735 → 11000+(12.4735-12.470)*62857≈164→11164)
COAST_X = MC_ORIGIN_X + int(round((12.4745 - ORIGIN_LON) * METERS_PER_LON))  # ~11289
print(f'Kystlinje estimat: X={COAST_X} (vest for dette er hav)')

# Hvidovrehavn (marina) MC-koordinater
HARBOR_MC = geo_to_mc(55.617, 12.477)   # centrum af havnebassinet
print(f'Havnecenter: X={HARBOR_MC[0]}, Z={HARBOR_MC[1]}')

# ── OSM Download ──────────────────────────────────────────────────────────────
CACHE_MAIN   = '/tmp/osm_havn_1to1.json'      # eksisterende cache
CACHE_EXTRA  = '/tmp/osm_v4_extra.json'       # nye lag
CACHE_COAST  = '/tmp/osm_v4_coast.json'       # kystlinje

QUERY_EXTRA = f"""
[out:json][timeout:120];
(
  node["natural"="tree"]({BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E});
  way["natural"="tree_row"]({BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E});
  way["landuse"="grass"]({BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E});
  way["natural"="grassland"]({BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E});
  way["amenity"="parking"]({BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E});
  way["amenity"="school"]({BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E});
  way["leisure"="pitch"]({BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E});
  way["leisure"="playground"]({BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E});
  way["natural"="coastline"]({BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E});
  way["natural"="water"]({BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E});
  way["waterway"="dock"]({BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E});
  relation["natural"="water"]({BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E});
  way["harbour"="yes"]({BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E});
  way["landuse"="harbour"]({BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E});
  way["seamark:type"]({BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E});
);
out body geom;
""".strip()

# Udvidet bbox for kystdata (lidt udenfor for at fange kysten)
COAST_BBOX = (55.610, 12.460, 55.635, 12.510)
QUERY_COAST = f"""
[out:json][timeout:120];
(
  way["natural"="coastline"]({COAST_BBOX[0]},{COAST_BBOX[1]},{COAST_BBOX[2]},{COAST_BBOX[3]});
  way["natural"="water"]({COAST_BBOX[0]},{COAST_BBOX[1]},{COAST_BBOX[2]},{COAST_BBOX[3]});
  relation["natural"="water"]({COAST_BBOX[0]},{COAST_BBOX[1]},{COAST_BBOX[2]},{COAST_BBOX[3]});
  way["waterway"="dock"]({COAST_BBOX[0]},{COAST_BBOX[1]},{COAST_BBOX[2]},{COAST_BBOX[3]});
);
out body geom;
""".strip()

def download(cache, query, label):
    if os.path.exists(cache):
        print(f'  Cache: {cache}')
        with open(cache) as f: return json.load(f)
    print(f'  Downloader {label}...')
    time.sleep(2)  # Respekter Overpass rate limit
    data = urllib.parse.urlencode({'data': query}).encode()
    req = urllib.request.Request('https://overpass-api.de/api/interpreter', data=data)
    req.add_header('User-Agent', 'MinecraftOSMBuilderV4/1.0')
    with urllib.request.urlopen(req, timeout=150) as r:
        raw = r.read().decode()
    result = json.loads(raw)
    with open(cache, 'w') as f: json.dump(result, f)
    print(f'  → {len(result.get("elements",[]))} elementer')
    return result

# ── Polygon helpers ───────────────────────────────────────────────────────────
def way_pts(way):
    return [geo_to_mc(nd['lat'], nd['lon'])
            for nd in way.get('geometry', []) if 'lat' in nd]

def poly_bbox(pts):
    if not pts: return None
    return min(p[0] for p in pts),max(p[0] for p in pts),min(p[1] for p in pts),max(p[1] for p in pts)

def _xs(pts, sz):
    n=len(pts); xs=[]
    for i in range(n):
        x1,z1=pts[i]; x2,z2=pts[(i+1)%n]
        if z1==z2: continue
        lo,hi=(z1,z2) if z1<z2 else (z2,z1)
        if not (lo<=sz<hi): continue
        xs.append(x1+(sz-z1)/(z2-z1)*(x2-x1))
    return sorted(xs)

def sfill(pts, y, blk, z0, z1):
    if len(pts)<3: return
    zs=[p[1] for p in pts]
    for sz in range(max(min(zs),z0), min(max(zs),z1)+1):
        xs=_xs(pts,sz)
        for i in range(0,len(xs)-1,2):
            xi1,xi2=int(math.floor(xs[i])),int(math.ceil(xs[i+1]))
            if xi1<=xi2: F(xi1,y,sz,xi2,y,sz,blk)

def sfill_r(pts, y1, y2, blk, z0, z1):
    if len(pts)<3: return
    zs=[p[1] for p in pts]
    for sz in range(max(min(zs),z0), min(max(zs),z1)+1):
        xs=_xs(pts,sz)
        for i in range(0,len(xs)-1,2):
            xi1,xi2=int(math.floor(xs[i])),int(math.ceil(xs[i+1]))
            if xi1<=xi2: F(xi1,y1,sz,xi2,y2,sz,blk)

def pip(px, pz, poly):
    n=len(poly); inside=False; j=n-1
    for i in range(n):
        xi,zi=poly[i]; xj,zj=poly[j]
        if ((zi>pz)!=(zj>pz)) and (px<(xj-xi)*(pz-zi)/(zj-zi)+xi): inside=not inside
        j=i
    return inside

def draw_line(pts, y, blk, hw, z0, z1):
    for i in range(len(pts)-1):
        x1,z1_=pts[i]; x2,z2_=pts[i+1]
        steps=max(abs(x2-x1),abs(z2_-z1_),1)
        for s in range(steps+1):
            t=s/steps
            bx=int(round(x1+t*(x2-x1))); bz=int(round(z1_+t*(z2_-z1_)))
            if bz<z0-2 or bz>z1+2: continue
            F(bx-hw,y,bz-hw,bx+hw,y,bz+hw,blk)

# ── Bygningsmaterialer ────────────────────────────────────────────────────────
def bld_mat(tags):
    bt=tags.get('building','').lower(); am=tags.get('amenity','').lower()
    color=tags.get('building:colour','').lower()
    mat=tags.get('building:material','').lower()
    # Materiale overrides
    if mat in ('brick','red_brick'): return 'minecraft:red_concrete'
    if mat in ('glass','glazing'): return 'minecraft:light_blue_concrete'
    if mat in ('concrete','reinforced_concrete'): return 'minecraft:light_gray_concrete'
    if mat in ('wood','timber'): return 'minecraft:oak_planks'
    # Farve overrides
    if color in ('red','#b22222'): return 'minecraft:red_concrete'
    if color in ('yellow','#ffd700'): return 'minecraft:yellow_concrete'
    if color in ('white','#ffffff'): return 'minecraft:white_concrete'
    if color in ('gray','grey'): return 'minecraft:gray_concrete'
    # Type
    if bt in ('apartments','flat'): return 'minecraft:light_gray_concrete'
    if bt in ('commercial','retail','office','supermarket'): return 'minecraft:smooth_stone'
    if bt in ('industrial','warehouse','factory'): return 'minecraft:red_concrete'
    if bt in ('school','hospital','civic','public') or am in ('school','hospital'): return 'minecraft:yellow_concrete'
    if bt in ('church','chapel','cathedral'): return 'minecraft:stone_bricks'
    if bt in ('garage','garages','shed','hut','carport'): return 'minecraft:oak_planks'
    if bt in ('house','detached','semidetached_house','terrace','bungalow'): return 'minecraft:white_concrete'
    return 'minecraft:white_concrete'

def bld_height(tags):
    try: return max(3,int(float(tags['height'])))
    except: pass
    try: return max(3,int(float(tags['building:levels']))*3)
    except: pass
    bt=tags.get('building','').lower()
    if bt in ('garage','shed','carport','hut'): return 3
    if bt in ('apartments','flat'): return 12
    if bt in ('commercial','retail','office'): return 9
    if bt in ('industrial','warehouse'): return 6
    return 6

def bld_roof(tags):
    rt=tags.get('roof:shape','flat').lower()
    rc=tags.get('roof:colour','').lower()
    if 'tile' in tags.get('roof:material','').lower(): return 'minecraft:red_concrete'
    if rc in ('red','#cc0000'): return 'minecraft:red_concrete'
    if rc in ('black','#000'): return 'minecraft:black_concrete'
    if rc in ('green','#006400'): return 'minecraft:green_concrete'
    if rc in ('brown'): return 'minecraft:brown_concrete'
    return 'minecraft:gray_concrete'   # standard fladt tag

ROAD_SPECS = {
    'motorway':('minecraft:black_concrete',8),
    'trunk':('minecraft:black_concrete',7),
    'primary':('minecraft:black_concrete',6),
    'secondary':('minecraft:black_concrete',5),
    'tertiary':('minecraft:gray_concrete',4),
    'residential':('minecraft:gray_concrete',4),
    'unclassified':('minecraft:gray_concrete',3),
    'living_street':('minecraft:gray_concrete',3),
    'service':('minecraft:gray_concrete',3),
    'road':('minecraft:gray_concrete',4),
    'footway':('minecraft:gravel',2),
    'pedestrian':('minecraft:gravel',3),
    'path':('minecraft:gravel',2),
    'cycleway':('minecraft:lime_concrete',2),   # cykelsti = grøn
    'track':('minecraft:dirt_path',2),
    'steps':('minecraft:stone_bricks',2),
}
def road_spec(tags): return ROAD_SPECS.get(tags.get('highway','').lower(),('minecraft:gray_concrete',3))

# ── Træer ─────────────────────────────────────────────────────────────────────
TREE_TYPES = {
    'oak':    ('minecraft:oak_log',    'minecraft:oak_leaves'),
    'birch':  ('minecraft:birch_log',  'minecraft:birch_leaves'),
    'pine':   ('minecraft:spruce_log', 'minecraft:spruce_leaves'),
    'lime':   ('minecraft:oak_log',    'minecraft:oak_leaves'),
    'maple':  ('minecraft:oak_log',    'minecraft:oak_leaves'),
    'linden': ('minecraft:oak_log',    'minecraft:oak_leaves'),
    'cherry': ('minecraft:cherry_log', 'minecraft:cherry_leaves'),
}

def place_tree(x, y, z, trunk='minecraft:oak_log', leaves='minecraft:oak_leaves'):
    for dy in range(4): S(x,y+dy,z,trunk)
    for dx in range(-2,3):
        for dz in range(-2,3):
            for ddy in range(2,6):
                if abs(dx)+abs(dz)<=3-abs(ddy-3):
                    cmd(f'setblock {x+dx} {y+ddy} {z+dz} {leaves}[persistent=true] keep')

def place_tree_from_tags(x, y, z, tags):
    sp=tags.get('species:en',tags.get('species',tags.get('genus','oak'))).lower().split()[0]
    tk,lv=TREE_TYPES.get(sp,('minecraft:oak_log','minecraft:oak_leaves'))
    place_tree(x, y, z, tk, lv)

# ── Forceload ─────────────────────────────────────────────────────────────────
def forceload_strip(z0, z1, load=True):
    act='add' if load else 'remove'
    for xa in range(MC_MIN_X, MC_MAX_X+1, 256):
        xb=min(xa+255,MC_MAX_X)
        cmd(f'forceload {act} {xa} {z0} {xb} {z1}')
    if load: time.sleep(0.2)

# ── Checkpoint ────────────────────────────────────────────────────────────────
def load_checkpoint():
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT) as f: d=json.load(f)
        print(f'Genoptager: {len(d["done"])} strips færdige')
        return d
    return {'done':[], 'cmds':0}

def save_checkpoint(cp, strip_num):
    cp['done'].append(strip_num)
    cp['cmds']=_cnt[0]
    cp['ts']=time.strftime('%Y-%m-%dT%H:%M:%S')
    with open(CHECKPOINT,'w') as f: json.dump(cp,f,indent=2)

# ── Kystlinje og hav ──────────────────────────────────────────────────────────
def build_sea(strip_z0, strip_z1, coast_polys):
    """
    Fyld havet vest for kystlinjen.
    Strategi: For hvert X < COAST_X (hav-siden), fyld Y=-66..-62 med sten og Y=-63 med vand.
    Kystlinjepolygoner definerer præcis grænse.
    """
    # Simpel approach: vest for COAST_X er hav
    # Mere præcis: brug kystlinjepolygoner hvis de findes
    if coast_polys:
        for pts in coast_polys:
            if len(pts) < 3: continue
            bb = poly_bbox(pts)
            if not bb or bb[3] < strip_z0 or bb[2] > strip_z1: continue
            # Fyld hav-polygon med vand
            sfill(pts, SEA_BED,   'minecraft:stone', strip_z0, strip_z1)
            sfill(pts, SEA_BED+1, 'minecraft:stone', strip_z0, strip_z1)
            sfill(pts, SEA_BED+2, 'minecraft:stone', strip_z0, strip_z1)
            sfill(pts, SEA_Y,     'minecraft:water', strip_z0, strip_z1)
            sfill(pts, GROUND_Y,  'minecraft:air',   strip_z0, strip_z1)
            sfill(pts, BASE_Y,    'minecraft:air',   strip_z0, strip_z1)
    else:
        # Fallback: fyld alting vest for COAST_X med hav
        if MC_MIN_X < COAST_X:
            x_end = min(COAST_X, MC_MAX_X)
            F(MC_MIN_X, SEA_BED,   strip_z0, x_end, SEA_BED+2, strip_z1, 'minecraft:stone')
            F(MC_MIN_X, SEA_Y,     strip_z0, x_end, SEA_Y,     strip_z1, 'minecraft:water')
            F(MC_MIN_X, GROUND_Y,  strip_z0, x_end, GROUND_Y,  strip_z1, 'minecraft:air')
            F(MC_MIN_X, BASE_Y,    strip_z0, x_end, BASE_Y,    strip_z1, 'minecraft:air')

def build_harbor_water(marina_pts_list, strip_z0, strip_z1):
    """Fyld havnebassiner og dokker med vand."""
    for pts in marina_pts_list:
        if len(pts) < 3: continue
        bb = poly_bbox(pts)
        if not bb or bb[3] < strip_z0 or bb[2] > strip_z1: continue
        sfill(pts, SEA_BED,   'minecraft:stone', strip_z0, strip_z1)
        sfill(pts, SEA_BED+1, 'minecraft:stone', strip_z0, strip_z1)
        sfill(pts, SEA_Y,     'minecraft:water', strip_z0, strip_z1)
        sfill(pts, GROUND_Y,  'minecraft:air',   strip_z0, strip_z1)
        sfill(pts, BASE_Y,    'minecraft:air',   strip_z0, strip_z1)

# ── Detaljerede bygninger ──────────────────────────────────────────────────────
def build_detailed(pts, base_y, height, wall, roof_mat, z0, z1):
    if len(pts)<3: return
    zs=[p[1] for p in pts]
    roof_y=base_y+height-1
    for sz in range(max(min(zs),z0), min(max(zs),z1)+1):
        xs=_xs(pts,sz)
        for i in range(0,len(xs)-1,2):
            xi1=int(math.floor(xs[i])); xi2=int(math.ceil(xs[i+1]))
            if xi1>xi2: continue
            F(xi1,base_y,sz,xi2,base_y,sz,wall)            # gulv
            F(xi1,roof_y,sz,xi2,roof_y,sz,roof_mat)        # tag
            if height>2:
                for y in range(base_y+1, roof_y):
                    rel=y-base_y; win=(rel%3==1)
                    if win:
                        if xi2>xi1+1: F(xi1+1,y,sz,xi2-1,y,sz,wall)
                        # Facader med glasruder
                        lx=xi1%3; rx=xi2%3
                        S(xi1,y,sz, wall if lx==0 else 'minecraft:glass_pane')
                        if xi2!=xi1: S(xi2,y,sz, wall if rx==0 else 'minecraft:glass_pane')
                    else:
                        F(xi1,y,sz,xi2,y,sz,wall)
    # Z-facade vinduer
    n=len(pts)
    for i in range(n):
        x1,z1_=pts[i]; x2,z2_=pts[(i+1)%n]
        if abs(z2_-z1_)>2 or abs(x2-x1)<2: continue
        sz_e=int(round((z1_+z2_)/2))
        if sz_e<z0 or sz_e>z1: continue
        for bx in range(min(x1,x2), max(x1,x2)+1):
            for y in range(base_y+1, roof_y):
                if (y-base_y)%3==1 and bx%3!=0:
                    S(bx,y,sz_e,'minecraft:glass_pane')

def build_road_full(pts, y, mat, width, z0, z1, trees=False, cycleway_side=False):
    hw=max(0,width//2); sw=1
    for i in range(len(pts)-1):
        x1,z1_=pts[i]; x2,z2_=pts[i+1]
        steps=max(abs(x2-x1),abs(z2_-z1_),1)
        dx=x2-x1; dz=z2_-z1_; ln=math.sqrt(dx*dx+dz*dz)+0.001
        for s in range(steps+1):
            t=s/steps
            bx=int(round(x1+t*(x2-x1))); bz=int(round(z1_+t*(z2_-z1_)))
            if bz<z0-2 or bz>z1+2: continue
            # Fortov
            if width>=3:
                F(bx-hw-sw,y,bz-sw,bx-hw-1,y,bz+sw,'minecraft:stone')
                F(bx+hw+1, y,bz-sw,bx+hw+sw,y,bz+sw,'minecraft:stone')
            # Cykelsti
            if cycleway_side and width>=5:
                F(bx-hw-sw-1,y,bz,bx-hw-sw-1,y,bz,'minecraft:lime_concrete')
                F(bx+hw+sw+1,y,bz,bx+hw+sw+1,y,bz,'minecraft:lime_concrete')
            # Vej
            F(bx-hw,y,bz-hw,bx+hw,y,bz+hw,mat)
            # Midterlinje
            if width>=6 and s%8<4:
                S(bx,y,bz,'minecraft:white_concrete')
            # Gadetræer
            if trees and s%14==0:
                px=int(round(-dz/ln*(hw+2))); pz=int(round(dx/ln*(hw+2)))
                if z0<=bz+pz<=z1:
                    place_tree(bx+px,y,bz+pz)

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print('\n=== Hvidovrehavn v4 Super Detaljeret ===')
    print(f'MC: X={MC_MIN_X}..{MC_MAX_X}, Z={MC_MIN_Z}..{MC_MAX_Z}')
    print(f'Kystlinje ved X≈{COAST_X}')

    # Download OSM
    print('\nDownloader OSM data...')
    with open(CACHE_MAIN) as f: main_data=json.load(f)
    extra_data = download(CACHE_EXTRA, QUERY_EXTRA, 'ekstra lag (træer, parkering mv.)')
    coast_data = download(CACHE_COAST, QUERY_COAST, 'kystdata (udvidet bbox)')

    all_elements = main_data.get('elements',[]) + extra_data.get('elements',[])
    coast_elements = coast_data.get('elements',[])

    # Sorter elementer
    buildings,roads,waters,beaches,landuses,piers=[],[],[],[],[],[]
    trees_nodes=[]; parkings=[]; pitches=[]; playgrounds=[]
    marina_polys=[]; coast_polys=[]

    for el in all_elements:
        if el.get('type') not in ('way','node'): continue
        tags=el.get('tags',{})
        geom=el.get('geometry',[])

        if el.get('type')=='node' and tags.get('natural')=='tree':
            lat=el.get('lat'); lon=el.get('lon')
            if lat and lon: trees_nodes.append((geo_to_mc(lat,lon), tags))
            continue

        if not geom: continue
        pts=[geo_to_mc(nd['lat'],nd['lon']) for nd in geom if 'lat' in nd]

        if tags.get('building'): buildings.append((el,pts))
        elif tags.get('highway'): roads.append((el,pts))
        elif tags.get('natural')=='beach' or tags.get('leisure')=='beach': beaches.append((el,pts))
        elif tags.get('natural')=='water' or tags.get('waterway'): waters.append((el,pts))
        elif tags.get('leisure')=='marina' or tags.get('landuse')=='harbour':
            marina_polys.append(pts)
            landuses.append((el,pts))
        elif tags.get('man_made') in ('pier','breakwater','jetty','groyne','seawall','quay'): piers.append((el,pts))
        elif tags.get('amenity')=='parking': parkings.append((el,pts))
        elif tags.get('leisure')=='pitch': pitches.append((el,pts))
        elif tags.get('leisure')=='playground': playgrounds.append((el,pts))
        elif tags.get('landuse') or tags.get('leisure') or tags.get('natural'): landuses.append((el,pts))

    for el in coast_elements:
        if el.get('type')!='way': continue
        tags=el.get('tags',{})
        geom=el.get('geometry',[])
        if not geom: continue
        pts=[geo_to_mc(nd['lat'],nd['lon']) for nd in geom if 'lat' in nd]
        if tags.get('natural') in ('coastline','water') or tags.get('waterway')=='dock':
            if len(pts)>=3: coast_polys.append(pts)

    print(f'Bygninger:{len(buildings)} Veje:{len(roads)} Vand:{len(waters)}')
    print(f'Strand:{len(beaches)} Marina:{len(marina_polys)} Kyst:{len(coast_polys)}')
    print(f'Parkering:{len(parkings)} Boldbaner:{len(pitches)} Træer:{len(trees_nodes)}')

    cp=load_checkpoint()
    total_strips=math.ceil((MC_MAX_Z-MC_MIN_Z+1)/STRIP_W)
    print(f'\nBygger {total_strips} strips...')

    for sn, sz0 in enumerate(range(MC_MIN_Z, MC_MAX_Z+1, STRIP_W), 1):
        sz1=min(sz0+STRIP_W-1, MC_MAX_Z)
        if sn in cp['done']:
            print(f'Strip {sn}/{total_strips}: springer over (færdig)')
            continue
        print(f'\nStrip {sn}/{total_strips}: Z={sz0}..{sz1}')

        forceload_strip(sz0, sz1, True)
        F(MC_MIN_X, BASE_Y, sz0, MC_MAX_X, 80, sz1, 'minecraft:air')

        # 1) Hav (vest for kystlinje)
        build_sea(sz0, sz1, coast_polys)

        # 2) Havnebassiner (vand i havnen)
        build_harbor_water(marina_polys, sz0, sz1)

        # 3) Vand (søer, kanaler mv.)
        for el,pts in waters:
            bb=poly_bbox(pts)
            if not bb or bb[3]<sz0 or bb[2]>sz1: continue
            if len(pts)>=3:
                sfill(pts,SEA_BED,'minecraft:stone',sz0,sz1)
                sfill(pts,SEA_Y,'minecraft:water',sz0,sz1)
                sfill(pts,GROUND_Y,'minecraft:air',sz0,sz1)
                sfill(pts,BASE_Y,'minecraft:air',sz0,sz1)
            else: draw_line(pts,SEA_Y,'minecraft:water',3,sz0,sz1)

        # 4) Strand (sand overskriver)
        for el,pts in beaches:
            bb=poly_bbox(pts)
            if not bb or bb[3]<sz0 or bb[2]>sz1: continue
            sfill(pts,GROUND_Y,'minecraft:sand',sz0,sz1)
            sfill(pts,BASE_Y,'minecraft:sand',sz0,sz1)
            # Strandsand ned til vandkanten
            sfill(pts,BASE_Y+1,'minecraft:sand',sz0,sz1)

        # 5) Landuse
        for el,pts in landuses:
            tags=el.get('tags',{})
            bb=poly_bbox(pts)
            if not bb or bb[3]<sz0 or bb[2]>sz1: continue
            lu=tags.get('landuse','').lower(); lei=tags.get('leisure','').lower()
            nat=tags.get('natural','').lower()
            if lei=='marina' or lu=='harbour':
                # Kajen rundt om havnen = brosten
                draw_line(pts,BASE_Y,'minecraft:stone_bricks',3,sz0,sz1)
            elif lu in ('park','garden','grass','recreation_ground') or lei in ('park','garden'):
                sfill(pts,BASE_Y,'minecraft:moss_block',sz0,sz1)
                # Blomster/buske tilfældigt
                for bx in range(bb[0],bb[1]+1,6):
                    for bz in range(max(bb[2],sz0),min(bb[3],sz1)+1,6):
                        if pip(bx,bz,pts):
                            if (bx+bz)%12==0: S(bx,BASE_Y+1,bz,'minecraft:dandelion')
                            elif (bx+bz)%12==6: S(bx,BASE_Y+1,bz,'minecraft:poppy')
            elif lu in ('forest','wood') or nat in ('wood','scrub'):
                sfill(pts,BASE_Y,'minecraft:moss_block',sz0,sz1)
                for bx in range(bb[0],bb[1]+1,7):
                    for bz in range(max(bb[2],sz0),min(bb[3],sz1)+1,7):
                        if pip(bx,bz,pts): place_tree(bx,BASE_Y,bz)
            elif lu=='residential':
                sfill(pts,BASE_Y,'minecraft:dirt_path',sz0,sz1)
            elif lu in ('commercial','retail','industrial'):
                sfill(pts,BASE_Y,'minecraft:smooth_stone',sz0,sz1)
            elif lu in ('farmland','allotments','meadow'):
                sfill(pts,BASE_Y,'minecraft:farmland',sz0,sz1)

        # 6) Parkering
        for el,pts in parkings:
            bb=poly_bbox(pts)
            if not bb or bb[3]<sz0 or bb[2]>sz1: continue
            sfill(pts,BASE_Y,'minecraft:gray_concrete',sz0,sz1)
            # Parkeringsstriber
            for bx in range(bb[0],bb[1]+1,4):
                for bz in range(max(bb[2],sz0),min(bb[3],sz1)+1):
                    if pip(bx,bz,pts): S(bx,BASE_Y,bz,'minecraft:white_concrete')

        # 7) Boldbaner
        for el,pts in pitches:
            bb=poly_bbox(pts)
            if not bb or bb[3]<sz0 or bb[2]>sz1: continue
            tags=el.get('tags',{})
            sport=tags.get('sport','').lower()
            mat='minecraft:green_concrete' if sport in ('soccer','football','') else 'minecraft:lime_concrete'
            sfill(pts,BASE_Y,mat,sz0,sz1)
            # Banestriber
            if bb[1]-bb[0]>10:
                draw_line(pts,BASE_Y,'minecraft:white_concrete',0,sz0,sz1)

        # 8) Legepladser
        for el,pts in playgrounds:
            bb=poly_bbox(pts)
            if not bb or bb[3]<sz0 or bb[2]>sz1: continue
            sfill(pts,BASE_Y,'minecraft:sand',sz0,sz1)
            # Gynge-/klatrestativer
            cx_=(bb[0]+bb[1])//2; cz_=(bb[2]+bb[3])//2
            if sz0<=cz_<=sz1:
                S(cx_,BASE_Y,'minecraft:chiseled_stone_bricks')
                S(cx_+2,BASE_Y,'minecraft:chiseled_stone_bricks')
                S(cx_,BASE_Y+2,cz_,'minecraft:oak_fence')

        # 9) Bygninger (detaljeret)
        for el,pts in buildings:
            tags=el.get('tags',{})
            bb=poly_bbox(pts)
            if not bb or bb[3]<sz0 or bb[2]>sz1: continue
            wall=bld_mat(tags); height=bld_height(tags); roof=bld_roof(tags)
            build_detailed(pts, BASE_Y, height, wall, roof, sz0, sz1)
            # Hæk / have rundt om enfamiliehuse
            bt=tags.get('building','').lower()
            if bt in ('house','detached','semidetached_house','terrace','bungalow') and height<=6:
                # Lille hæk 1 blok udenfor bygning
                hbb=poly_bbox(pts)
                if hbb:
                    hx0,hx1,hz0,hz1=hbb
                    for hx in range(hx0-2,hx1+3,1):
                        for hz in range(max(hz0-2,sz0),min(hz1+3,sz1)+1):
                            if not pip(hx,hz,pts) and (hx==hx0-2 or hx==hx1+2 or hz==hz0-2 or hz==hz1+2):
                                # Tjek det ikke er på en vej (bare sæt hvis BASE_Y er dirpath eller grass)
                                cmd(f'setblock {hx} {BASE_Y+1} {hz} minecraft:oak_leaves[persistent=true] keep')

        # 10) Kajer og moler
        for el,pts in piers:
            zvals=[p[1] for p in pts]
            if min(zvals)>sz1 or max(zvals)<sz0: continue
            if len(pts)>=3:
                bb=poly_bbox(pts)
                if bb and not(bb[3]<sz0 or bb[2]>sz1):
                    for dy in range(3): sfill(pts,BASE_Y+dy,'minecraft:stone_bricks',sz0,sz1)
            else:
                for dy in range(3): draw_line(pts,BASE_Y+dy,'minecraft:stone_bricks',5,sz0,sz1)

        # 11) Veje (øverst)
        for el,pts in roads:
            zvals=[p[1] for p in pts]
            if min(zvals)>sz1+4 or max(zvals)<sz0-4: continue
            tags=el.get('tags',{})
            mat,width=road_spec(tags)
            hw=tags.get('highway','')
            has_cycle='cycleway' in tags.get('bicycle','') or tags.get('cycleway') in ('lane','track')
            build_road_full(pts,BASE_Y,mat,width,sz0,sz1,
                          trees=hw in ('residential','living_street'),
                          cycleway_side=has_cycle or hw in ('primary','secondary'))

        # 12) Individuelle træer (OSM-noder)
        for (tx,tz),ttags in trees_nodes:
            if sz0<=tz<=sz1:
                place_tree_from_tags(tx,BASE_Y,tz,ttags)

        cmd('save-all flush')
        time.sleep(0.5)
        forceload_strip(sz0, sz1, False)
        save_checkpoint(cp, sn)
        print(f'  ✓ Strip {sn} gemt [{_cnt[0]} total cmds]')

    # Teleporter
    hx,hz=geo_to_mc(55.617,12.477)
    cmd(f'forceload add {hx-64} {hz-64} {hx+64} {hz+64}')
    time.sleep(0.5)
    cmd(f'tp HomeboyDK {hx} -30 {hz}')
    cmd(f'forceload remove {hx-64} {hz-64} {hx+64} {hz+64}')

    print(f'\n✅ FÆRDIG! {_cnt[0]} RCON-kommandoer')
    print(f'Havn: /tp {hx} -30 {hz}')
    print(f'Overblik: /tp {(MC_MIN_X+MC_MAX_X)//2} 80 {(MC_MIN_Z+MC_MAX_Z)//2}')

if __name__=='__main__': main()
