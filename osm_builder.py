#!/usr/bin/env python3
"""
Generisk OSM→Minecraft builder med checkpoint, verifikation og retry.

Usage:
    python3 osm_builder.py --bbox S,W,N,E --origin X,Z [options]

Options:
    --bbox S,W,N,E        Bounding box (decimal grader)
    --origin X,Z          Minecraft SW-hjørne koordinater (default: 0,0)
    --scale FLOAT         Meter pr. blok (default: 1.0)
    --strip-width INT     Z-strips bredde i blokke (default: 128)
    --resume FILE         Genoptag fra checkpoint-fil
    --dry-run             Print kommandoer uden at sende til server
    --no-windows          Byg uden vinduer (hurtigere)
    --no-trees            Byg uden gadetræer
    --name STR            Navn til checkpoint-fil (default: auto fra bbox)

Eksempler:
    python3 osm_builder.py --bbox 55.614,12.470,55.630,12.507 --origin 8000,8000
    python3 osm_builder.py --resume checkpoint_hvidovre.json
    nohup python3 osm_builder.py --bbox 55.60,12.44,55.65,12.55 --origin 11000,11000 --name hele_hvidovre > build.log 2>&1 &
"""

import argparse, json, math, os, socket, struct, time, urllib.request, urllib.parse
import sys

# ── CLI ───────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description='OSM→Minecraft builder')
    p.add_argument('--bbox',        help='S,W,N,E')
    p.add_argument('--origin',      default='0,0', help='X,Z MC origin (SW corner)')
    p.add_argument('--scale',       type=float, default=1.0)
    p.add_argument('--strip-width', type=int,   default=128)
    p.add_argument('--resume',      help='Checkpoint JSON-fil')
    p.add_argument('--dry-run',     action='store_true')
    p.add_argument('--no-windows',  action='store_true')
    p.add_argument('--no-trees',    action='store_true')
    p.add_argument('--name',        default='')
    return p.parse_args()

# ── RCON ──────────────────────────────────────────────────────────────────────
RCON_HOST, RCON_PORT, RCON_PASS = '127.0.0.1', 25575, 'NME21o3#'

class Rcon:
    def __init__(self, dry=False):
        self.dry = dry; self._s = None; self.count = 0; self._connect()

    def _connect(self):
        s = socket.socket(); s.settimeout(20); s.connect((RCON_HOST, RCON_PORT))
        def pkt(rid, rt, p):
            d = p.encode('utf-8') + b'\x00\x00'
            s.send(struct.pack('<iii', len(d)+8, rid, rt) + d)
            r = b''
            while len(r)<4 or len(r)<struct.unpack('<i',r[:4])[0]+4:
                c=s.recv(4096);
                if not c: break
                r+=c
            return r[12:-2].decode('utf-8','replace')
        pkt(1, 3, RCON_PASS); self._s = s; self._pkt = pkt

    def cmd(self, c):
        if self.dry: self.count += 1; return ''
        for _ in range(3):
            try:
                r = self._pkt(2, 2, c); self.count += 1
                if self.count % 1000 == 0: print(f'  [{self.count}]', end='\r', flush=True)
                return r
            except:
                time.sleep(0.5)
                try: self._s.close()
                except: pass
                try: self._connect()
                except: pass
        return ''

    def F(self, x1,y1,z1,x2,y2,z2,blk,mode=''):
        if x1>x2: x1,x2=x2,x1
        if y1>y2: y1,y2=y2,y1
        if z1>z2: z1,z2=z2,z1
        vol=(x2-x1+1)*(y2-y1+1)*(z2-z1+1)
        if vol>32768:
            dx,dy,dz=x2-x1+1,y2-y1+1,z2-z1+1
            if dx>=dy and dx>=dz:
                m=x1+dx//2-1; self.F(x1,y1,z1,m,y2,z2,blk,mode); self.F(m+1,y1,z1,x2,y2,z2,blk,mode)
            elif dy>=dz:
                m=y1+dy//2-1; self.F(x1,y1,z1,x2,m,z2,blk,mode); self.F(x1,m+1,z1,x2,y2,z2,blk,mode)
            else:
                m=z1+dz//2-1; self.F(x1,y1,z1,x2,y2,m,blk,mode); self.F(x1,y1,m+1,x2,y2,z2,blk,mode)
            return
        self.cmd(f'fill {x1} {y1} {z1} {x2} {y2} {z2} {blk}' + (f' {mode}' if mode else ''))

    def S(self, x,y,z,blk): self.cmd(f'setblock {x} {y} {z} {blk}')

    def verify_strip(self, xmin, xmax, z0, z1, sample=12):
        """Sample random points — returnér antal non-air blokke."""
        import random
        found = 0
        for _ in range(sample):
            x = random.randint(xmin, xmax)
            z = random.randint(z0, z1)
            r = self.cmd(f'execute if block {x} -60 {z} minecraft:air')
            if r and 'failed' in r.lower():
                found += 1
        return found

# ── OSM ───────────────────────────────────────────────────────────────────────
def download_osm(bbox, cache_file):
    if os.path.exists(cache_file):
        print(f'Bruger cache: {cache_file}')
        with open(cache_file) as f: return json.load(f)
    S,W,N,E = bbox
    q = f"""[out:json][timeout:90];(
      way["building"]({S},{W},{N},{E});
      way["highway"]({S},{W},{N},{E});
      way["natural"="water"]({S},{W},{N},{E});
      way["waterway"]({S},{W},{N},{E});
      way["natural"="beach"]({S},{W},{N},{E});
      way["leisure"="beach"]({S},{W},{N},{E});
      way["landuse"]({S},{W},{N},{E});
      way["leisure"]({S},{W},{N},{E});
      way["man_made"]({S},{W},{N},{E});
      way["amenity"]({S},{W},{N},{E});
    );out body geom;""".strip()
    print('Downloader OSM data...')
    data = urllib.parse.urlencode({'data': q}).encode()
    req = urllib.request.Request('https://overpass-api.de/api/interpreter', data=data)
    req.add_header('User-Agent', 'MinecraftOSMBuilder/3.0')
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode()
    result = json.loads(raw)
    with open(cache_file, 'w') as f: json.dump(result, f)
    print(f'Downloadet {len(result.get("elements",[]))} elementer → {cache_file}')
    return result

# ── Koordinat-konvertering ────────────────────────────────────────────────────
class CoordConverter:
    def __init__(self, origin_lat, origin_lon, mc_x, mc_z, scale, lat_ref):
        self.olat, self.olon = origin_lat, origin_lon
        self.mx, self.mz = mc_x, mc_z
        self.scale = scale
        self.mpl = 111320.0
        self.mplon = 111320.0 * math.cos(math.radians(lat_ref))

    def to_mc(self, lat, lon):
        return (self.mx + int(round((lon-self.olon)*self.mplon*self.scale)),
                self.mz - int(round((lat-self.olat)*self.mpl*self.scale)))

# ── Polygon helpers ───────────────────────────────────────────────────────────
def _scanline_xs(pts, sz):
    n = len(pts); xs = []
    for i in range(n):
        x1,z1=pts[i]; x2,z2=pts[(i+1)%n]
        if z1==z2: continue
        lo,hi=(z1,z2) if z1<z2 else (z2,z1)
        if not (lo<=sz<hi): continue
        xs.append(x1+(sz-z1)/(z2-z1)*(x2-x1))
    return sorted(xs)

def scanfill(r, pts, y, blk, z0, z1):
    if len(pts)<3: return
    zs=[p[1] for p in pts]
    for sz in range(max(min(zs),z0), min(max(zs),z1)+1):
        xs=_scanline_xs(pts,sz)
        for i in range(0,len(xs)-1,2):
            xi1,xi2=int(math.floor(xs[i])),int(math.ceil(xs[i+1]))
            if xi1<=xi2: r.F(xi1,y,sz,xi2,y,sz,blk)

def scanfill_range(r, pts, y1, y2, blk, z0, z1):
    if len(pts)<3: return
    zs=[p[1] for p in pts]
    for sz in range(max(min(zs),z0), min(max(zs),z1)+1):
        xs=_scanline_xs(pts,sz)
        for i in range(0,len(xs)-1,2):
            xi1,xi2=int(math.floor(xs[i])),int(math.ceil(xs[i+1]))
            if xi1<=xi2: r.F(xi1,y1,sz,xi2,y2,sz,blk)

def poly_bbox(pts):
    if not pts: return None
    return min(p[0] for p in pts),max(p[0] for p in pts),min(p[1] for p in pts),max(p[1] for p in pts)

def point_in_poly(px,pz,poly):
    n=len(poly); inside=False; j=n-1
    for i in range(n):
        xi,zi=poly[i]; xj,zj=poly[j]
        if ((zi>pz)!=(zj>pz)) and (px<(xj-xi)*(pz-zi)/(zj-zi)+xi): inside=not inside
        j=i
    return inside

# ── Materials ─────────────────────────────────────────────────────────────────
def bld_mat(tags):
    bt=tags.get('building','').lower(); am=tags.get('amenity','').lower()
    if bt in ('apartments','flat'): return 'minecraft:light_gray_concrete'
    if bt in ('commercial','retail','office','supermarket'): return 'minecraft:smooth_stone'
    if bt in ('industrial','warehouse','factory'): return 'minecraft:red_concrete'
    if bt in ('school','hospital','civic','public') or am in ('school','hospital','university'): return 'minecraft:yellow_concrete'
    if bt in ('church','chapel','cathedral','place_of_worship'): return 'minecraft:stone_bricks'
    if bt in ('garage','garages','shed','hut','carport'): return 'minecraft:oak_planks'
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

ROAD_SPECS = {
    'motorway':('minecraft:black_concrete',8), 'trunk':('minecraft:black_concrete',7),
    'primary':('minecraft:black_concrete',6),  'secondary':('minecraft:black_concrete',5),
    'tertiary':('minecraft:gray_concrete',4),  'residential':('minecraft:gray_concrete',4),
    'unclassified':('minecraft:gray_concrete',3), 'living_street':('minecraft:gray_concrete',3),
    'service':('minecraft:gray_concrete',3),   'road':('minecraft:gray_concrete',4),
    'footway':('minecraft:gravel',2),          'pedestrian':('minecraft:gravel',3),
    'path':('minecraft:gravel',2),             'cycleway':('minecraft:gravel',2),
    'track':('minecraft:dirt_path',2),         'steps':('minecraft:stone_bricks',2),
}
def road_spec(tags): return ROAD_SPECS.get(tags.get('highway','').lower(),('minecraft:gray_concrete',3))

def landuse_mat(tags):
    lu=tags.get('landuse','').lower(); lei=tags.get('leisure','').lower(); nat=tags.get('natural','').lower()
    if lu in ('park','garden','grass','recreation_ground') or lei in ('park','garden','pitch','playground'): return 'minecraft:moss_block'
    if lu in ('forest','wood') or nat in ('wood','scrub'): return 'FOREST'
    if lu=='residential': return 'minecraft:dirt_path'
    if lu in ('commercial','retail','industrial'): return 'minecraft:smooth_stone'
    if lu in ('harbour','port') or lei=='marina': return 'minecraft:stone_bricks'
    if lu in ('farmland','allotments','meadow'): return 'minecraft:farmland'
    return None

# ── Build helpers ─────────────────────────────────────────────────────────────
def draw_road(r, pts, y, blk, width, z0, z1, sidewalk=True, centerline=True):
    hw=max(0,width//2); sw=1
    for i in range(len(pts)-1):
        x1,z1_=pts[i]; x2,z2_=pts[i+1]
        steps=max(abs(x2-x1),abs(z2_-z1_),1)
        for s in range(steps+1):
            t=s/steps
            bx=int(round(x1+t*(x2-x1))); bz=int(round(z1_+t*(z2_-z1_)))
            if bz<z0-2 or bz>z1+2: continue
            if sidewalk and width>=3:
                r.F(bx-hw-sw,y,bz-sw,bx-hw-1,y,bz+sw,'minecraft:stone')
                r.F(bx+hw+1,y,bz-sw,bx+hw+sw,y,bz+sw,'minecraft:stone')
            r.F(bx-hw,y,bz-hw,bx+hw,y,bz+hw,blk)
            if centerline and width>=6 and s%8<4:
                r.S(bx,y,bz,'minecraft:white_concrete')

def draw_road_trees(r, pts, y, blk, width, z0, z1):
    draw_road(r, pts, y, blk, width, z0, z1)
    hw=max(0,width//2)
    for i in range(len(pts)-1):
        x1,z1_=pts[i]; x2,z2_=pts[i+1]
        steps=max(abs(x2-x1),abs(z2_-z1_),1)
        for s in range(0,steps+1,14):
            t=s/steps
            bx=int(round(x1+t*(x2-x1))); bz=int(round(z1_+t*(z2_-z1_)))
            if bz<z0 or bz>z1: continue
            dx=x2-x1; dz=z2_-z1_; ln=math.sqrt(dx*dx+dz*dz)+0.001
            px=int(round(-dz/ln*(hw+2))); pz=int(round(dx/ln*(hw+2)))
            tx,tz=bx+px,bz+pz
            for dy in range(4): r.S(tx,y+dy,tz,'minecraft:oak_log')
            for ddx in range(-2,3):
                for ddz in range(-2,3):
                    for ddy in range(3,6):
                        if abs(ddx)+abs(ddz)+abs(ddy-4)<=4:
                            r.cmd(f'setblock {tx+ddx} {y+ddy} {tz+ddz} minecraft:oak_leaves[persistent=true] keep')

def build_with_windows(r, pts, base_y, height, wall, z0, z1):
    if len(pts)<3: return
    zs=[p[1] for p in pts]
    roof_y=base_y+height-1
    for sz in range(max(min(zs),z0), min(max(zs),z1)+1):
        xs=_scanline_xs(pts,sz)
        for i in range(0,len(xs)-1,2):
            xi1=int(math.floor(xs[i])); xi2=int(math.ceil(xs[i+1]))
            if xi1>xi2: continue
            r.F(xi1,base_y,sz,xi2,base_y,sz,wall)   # floor
            if height>1: r.F(xi1,roof_y,sz,xi2,roof_y,sz,'minecraft:gray_concrete')  # roof
            for y in range(base_y+1,roof_y):
                rel_y=y-base_y; is_win=(rel_y%3==1)
                if is_win:
                    if xi2>xi1+1: r.F(xi1+1,y,sz,xi2-1,y,sz,wall)
                    lx=xi1%3; rx=xi2%3
                    r.S(xi1,y,sz,wall if lx==0 else 'minecraft:glass_pane')
                    if xi2!=xi1: r.S(xi2,y,sz,wall if rx==0 else 'minecraft:glass_pane')
                else:
                    r.F(xi1,y,sz,xi2,y,sz,wall)

# ── Checkpoint ────────────────────────────────────────────────────────────────
class Checkpoint:
    def __init__(self, path):
        self.path = path
        self.data = {'completed_strips': [], 'cmd_count': 0}
        if path and os.path.exists(path):
            with open(path) as f: self.data = json.load(f)
            print(f'Genoptager fra {path}: {len(self.data["completed_strips"])} strips færdige')

    def is_done(self, strip_num): return strip_num in self.data['completed_strips']

    def mark_done(self, strip_num, cmd_count):
        self.data['completed_strips'].append(strip_num)
        self.data['cmd_count'] = cmd_count
        self.data['updated'] = time.strftime('%Y-%m-%dT%H:%M:%S')
        if self.path:
            with open(self.path, 'w') as f: json.dump(self.data, f, indent=2)

# ── Forceload ─────────────────────────────────────────────────────────────────
def forceload(r, xmin, xmax, z0, z1, load=True):
    act='add' if load else 'remove'
    for xa in range(xmin, xmax+1, 256):
        xb=min(xa+255,xmax)
        r.cmd(f'forceload {act} {xa} {z0} {xb} {z1}')
    if load: time.sleep(0.2)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()

    # Load checkpoint or parse args
    cp_path = args.resume
    if args.resume and os.path.exists(args.resume):
        with open(args.resume) as f: saved = json.load(f)
        bbox   = tuple(saved['bbox'])
        origin = tuple(saved['origin'])
        scale  = saved.get('scale', 1.0)
        name   = saved.get('name', '')
        strip_w = saved.get('strip_width', 128)
    else:
        if not args.bbox:
            print('FEJL: Angiv --bbox S,W,N,E eller --resume checkpoint.json')
            sys.exit(1)
        bbox   = tuple(float(x) for x in args.bbox.split(','))
        origin = tuple(int(x) for x in args.origin.split(','))
        scale  = args.scale
        strip_w = args.strip_width
        name   = args.name or f'osm_{bbox[0]:.3f}_{bbox[2]:.3f}'

    S,W,N,E = bbox
    mc_x, mc_z = origin

    if not cp_path:
        cp_path = f'checkpoint_{name.replace(" ","_")}.json'

    r = Rcon(dry=args.dry_run)
    cp = Checkpoint(cp_path)

    # Save config to checkpoint
    cp.data.update({'bbox': list(bbox), 'origin': list(origin),
                    'scale': scale, 'name': name, 'strip_width': strip_w})

    lat_ref = (S+N)/2
    conv = CoordConverter(S, W, mc_x, mc_z, scale, lat_ref)

    mc_sw = conv.to_mc(S, W)
    mc_ne = conv.to_mc(N, E)
    mc_min_x = min(mc_sw[0], mc_ne[0]); mc_max_x = max(mc_sw[0], mc_ne[0])
    mc_min_z = min(mc_sw[1], mc_ne[1]); mc_max_z = max(mc_sw[1], mc_ne[1])

    print(f'Byg-område: X={mc_min_x}..{mc_max_x}  Z={mc_min_z}..{mc_max_z}')
    print(f'Størrelse: {mc_max_x-mc_min_x} × {mc_max_z-mc_min_z} blokke, scale={scale}')

    cache = f'/tmp/osm_{name.replace(" ","_")}.json'
    osm = download_osm(bbox, cache)
    elements = osm.get('elements', [])

    buildings,roads,waters,beaches,landuses,piers=[],[],[],[],[],[]
    for el in elements:
        if el.get('type')!='way' or not el.get('geometry'): continue
        tags=el.get('tags',{})
        pts=[conv.to_mc(nd['lat'],nd['lon']) for nd in el['geometry'] if 'lat' in nd]
        el['_pts']=pts  # cache converted points
        if tags.get('building'): buildings.append(el)
        elif tags.get('highway'): roads.append(el)
        elif tags.get('natural')=='beach' or tags.get('leisure')=='beach': beaches.append(el)
        elif tags.get('natural') in ('water',) or tags.get('waterway'): waters.append(el)
        elif tags.get('man_made') in ('pier','breakwater','jetty','groyne','seawall','quay'): piers.append(el)
        elif tags.get('landuse') or tags.get('leisure') or tags.get('natural'): landuses.append(el)

    print(f'Elementer: {len(buildings)} bygninger, {len(roads)} veje, {len(waters)} vand, {len(beaches)} strande, {len(piers)} kajer')

    total_strips = math.ceil((mc_max_z-mc_min_z+1)/strip_w)

    for strip_num, strip_z0 in enumerate(range(mc_min_z, mc_max_z+1, strip_w), 1):
        strip_z1 = min(strip_z0+strip_w-1, mc_max_z)

        if cp.is_done(strip_num):
            print(f'Strip {strip_num}/{total_strips}: springer over (allerede færdig)')
            continue

        print(f'\nStrip {strip_num}/{total_strips}: Z={strip_z0}..{strip_z1}')

        forceload(r, mc_min_x, mc_max_x, strip_z0, strip_z1, True)

        # Clear
        r.F(mc_min_x,-60,strip_z0,mc_max_x,80,strip_z1,'minecraft:air')

        # 1) Vand
        for el in waters:
            pts=el['_pts']
            if not pts: continue
            bb=poly_bbox(pts)
            if not bb or bb[3]<strip_z0 or bb[2]>strip_z1: continue
            if len(pts)>=3:
                scanfill(r,pts,-65,'minecraft:stone',strip_z0,strip_z1)
                scanfill(r,pts,-64,'minecraft:stone',strip_z0,strip_z1)
                scanfill(r,pts,-63,'minecraft:water',strip_z0,strip_z1)
                scanfill(r,pts,-61,'minecraft:air',strip_z0,strip_z1)
                scanfill(r,pts,-60,'minecraft:air',strip_z0,strip_z1)
            else:
                draw_road(r,pts,-63,'minecraft:water',4,strip_z0,strip_z1,False,False)

        # 2) Landuse
        for el in landuses:
            pts=el['_pts']
            if not pts or len(pts)<3: continue
            bb=poly_bbox(pts)
            if not bb or bb[3]<strip_z0 or bb[2]>strip_z1: continue
            mat=landuse_mat(el.get('tags',{}))
            if not mat: continue
            if mat=='FOREST':
                scanfill(r,pts,-60,'minecraft:moss_block',strip_z0,strip_z1)
                if not args.no_trees:
                    for tx in range(bb[0],bb[1]+1,8):
                        for tz in range(max(bb[2],strip_z0),min(bb[3],strip_z1)+1,8):
                            if point_in_poly(tx,tz,pts):
                                for dy in range(4): r.S(tx,-60+dy,tz,'minecraft:oak_log')
                                for dx in range(-2,3):
                                    for dz in range(-2,3):
                                        for ddy in range(3,6):
                                            if abs(dx)+abs(dz)+abs(ddy-4)<=4:
                                                r.cmd(f'setblock {tx+dx} {-60+ddy} {tz+dz} minecraft:oak_leaves[persistent=true] keep')
            else:
                scanfill(r,pts,-60,mat,strip_z0,strip_z1)

        # 3) Strand (overskriver landuse)
        for el in beaches:
            pts=el['_pts']
            if not pts or len(pts)<3: continue
            bb=poly_bbox(pts)
            if not bb or bb[3]<strip_z0 or bb[2]>strip_z1: continue
            scanfill(r,pts,-61,'minecraft:sand',strip_z0,strip_z1)
            scanfill(r,pts,-60,'minecraft:sand',strip_z0,strip_z1)

        # 4) Bygninger
        for el in buildings:
            pts=el['_pts']
            if not pts or len(pts)<3: continue
            bb=poly_bbox(pts)
            if not bb or bb[3]<strip_z0 or bb[2]>strip_z1: continue
            tags=el.get('tags',{})
            wall=bld_mat(tags); height=bld_height(tags)
            if args.no_windows:
                scanfill(r,pts,-60,wall,strip_z0,strip_z1)
                if height>1: scanfill_range(r,pts,-59,-60+height-2,wall,strip_z0,strip_z1)
                scanfill(r,pts,-60+height-1,'minecraft:gray_concrete',strip_z0,strip_z1)
            else:
                build_with_windows(r,pts,-60,height,wall,strip_z0,strip_z1)

        # 5) Kajer / moler
        for el in piers:
            pts=el['_pts']
            if not pts: continue
            zvals=[p[1] for p in pts]
            if min(zvals)>strip_z1 or max(zvals)<strip_z0: continue
            if len(pts)>=3:
                bb=poly_bbox(pts)
                if bb and not(bb[3]<strip_z0 or bb[2]>strip_z1):
                    for dy in range(3): scanfill(r,pts,-60+dy,'minecraft:stone_bricks',strip_z0,strip_z1)
            else:
                for dy in range(3): draw_road(r,pts,-60+dy,'minecraft:stone_bricks',5,strip_z0,strip_z1,False,False)

        # 6) Veje (øverst)
        for el in roads:
            pts=el['_pts']
            if not pts: continue
            zvals=[p[1] for p in pts]
            if min(zvals)>strip_z1+4 or max(zvals)<strip_z0-4: continue
            tags=el.get('tags',{})
            mat,width=road_spec(tags)
            hw_type=tags.get('highway','')
            if not args.no_trees and hw_type in ('residential','living_street'):
                draw_road_trees(r,pts,-60,mat,width,strip_z0,strip_z1)
            else:
                draw_road(r,pts,-60,mat,width,strip_z0,strip_z1)

        # Gem → disk
        r.cmd('save-all flush')
        time.sleep(0.5)
        forceload(r,mc_min_x,mc_max_x,strip_z0,strip_z1,False)

        # Verificer
        found=r.verify_strip(mc_min_x,mc_max_x,strip_z0,strip_z1)
        if found==0 and not args.dry_run:
            print(f'  ⚠️  ADVARSEL: Strip {strip_num} verificering fandt 0 blokke — overspring check')
        else:
            print(f'  ✓ Verificeret: {found} sample-blokke fundet')

        cp.mark_done(strip_num, r.count)
        print(f'  Checkpoint gemt → {cp_path} [{r.count} total]')

    # Færdig
    cx=(mc_min_x+mc_max_x)//2; cz=(mc_min_z+mc_max_z)//2
    r.cmd(f'forceload add {cx-64} {cz-64} {cx+64} {cz+64}')
    time.sleep(0.5)
    r.cmd(f'tp HomeboyDK {cx} 80 {cz}')
    r.cmd(f'forceload remove {cx-64} {cz-64} {cx+64} {cz+64}')

    print(f'\n✅ Færdig! {r.count} RCON-kommandoer')
    print(f'Overblik: /tp {cx} 80 {cz}')
    print(f'Checkpoint: {cp_path}')

if __name__ == '__main__':
    main()
